"""
Job processing API for MultiFetch v2.
Handles job execution (download -> transcribe pipeline).
"""

import logging
import os
import shutil
import tempfile
import threading
from typing import Optional

from flask import Blueprint, jsonify, request

from api.sse import (
    notify_item_complete,
    notify_item_failed,
    notify_item_progress,
    notify_job_complete,
    notify_job_started,
)
from services.downloader import download_audio
from services.job_manager import Job, JobItem, JobStatus, JobType, job_manager
from services.transcriber import transcribe_audio

logger = logging.getLogger(__name__)

process_bp = Blueprint("process", __name__)


@process_bp.route("/jobs/<job_id>/start", methods=["POST"])
def start_job(job_id: str):
    """
    Start processing a job.

    Expects JSON body:
    {
        "api_key": "gsk_...",           # Required: Groq API key
        "cookies_path": "/path/to/...",  # Optional: Path to cookies file
        "is_dev_tier": false             # Optional: Groq dev tier flag
    }

    Returns:
        Job status JSON
    """
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status != JobStatus.PENDING:
        return jsonify({
            "error": f"Job already {job.status.value}",
            "job": job.to_dict(),
        }), 400

    # Get configuration from request
    data = request.get_json() or {}
    api_key = data.get("api_key")
    cookies_path = data.get("cookies_path")
    is_dev_tier = data.get("is_dev_tier", False)

    if not api_key:
        return jsonify({"error": "api_key is required"}), 400

    # Start job in background thread
    thread = threading.Thread(
        target=_process_job,
        args=(job_id, api_key, cookies_path, is_dev_tier),
        name=f"job-{job_id}",
        daemon=True,
    )
    thread.start()

    # Update job status
    job_manager.update_job_status(job_id, JobStatus.RUNNING)
    notify_job_started(job_id)

    return jsonify({
        "message": "Job started",
        "job": job_manager.get_job(job_id).to_dict(),
    })


def _process_single_item(
    job: Job,
    item: JobItem,
    job_id: str,
    api_key: str,
    cookies_path: Optional[str],
    is_dev_tier: bool,
    item_temp_dir: str,
    status_prefix: str = "starting",
) -> bool:
    """
    Process a single item (download -> transcribe).

    Args:
        job: The job object
        item: The item to process
        job_id: Job ID for updates
        api_key: Groq API key
        cookies_path: Optional cookies file path
        is_dev_tier: Whether user has dev tier
        item_temp_dir: Temp directory for this item
        status_prefix: Status message prefix (e.g., "starting" or "retrying")

    Returns:
        True if processing succeeded, False otherwise
    """
    url = item.url

    # Update item status
    job_manager.update_item_status(job_id, url, JobStatus.RUNNING, progress=0)
    notify_item_progress(job_id, url, 0, status_prefix)

    try:
        # Download audio
        audio_path, title, info = download_audio(
            url=url,
            job_id=job_id,
            cookies_path=cookies_path,
            output_dir=item_temp_dir,
        )

        if not audio_path:
            error = info.get("error", "Download failed") if info else "Download failed"
            logger.error(f"Download failed for {url}: {error}")
            job_manager.update_item_status(job_id, url, JobStatus.FAILED, error=error)
            notify_item_failed(job_id, url, error)
            return False

        logger.info(f"Downloaded: {title}")
        job_manager.update_item_status(
            job_id, url, JobStatus.RUNNING,
            progress=50,
            title=title,
            audio_path=audio_path,
        )
        notify_item_progress(job_id, url, 50, "downloaded")

        # Transcribe (skip if download-only job)
        if job.job_type in (JobType.TRANSCRIBE, JobType.FULL):
            # Check for cancellation before transcription
            current_job = job_manager.get_job(job_id)
            if not current_job or current_job.status == JobStatus.CANCELLED:
                logger.info(f"Job {job_id} cancelled before transcription")
                return False

            transcript = transcribe_audio(
                audio_path=audio_path,
                api_key=api_key,
                job_id=job_id,
                url=url,
                language=job.language,
                is_dev_tier=is_dev_tier,
            )

            if transcript:
                job_manager.update_item_status(
                    job_id, url, JobStatus.COMPLETED,
                    progress=100,
                    transcript=transcript,
                )
                notify_item_complete(job_id, url, title=title, transcript=transcript)
                logger.info(f"Transcription complete for {url}")
                return True
            else:
                job_manager.update_item_status(
                    job_id, url, JobStatus.FAILED,
                    error="Transcription failed",
                )
                notify_item_failed(job_id, url, "Transcription failed")
                logger.error(f"Transcription failed for {url}")
                return False
        else:
            # Download-only job
            job_manager.update_item_status(
                job_id, url, JobStatus.COMPLETED,
                progress=100,
            )
            notify_item_complete(job_id, url, title=title)
            logger.info(f"Download complete for {url}")
            return True

    except Exception as e:
        logger.exception(f"Error processing {url}")
        job_manager.update_item_status(job_id, url, JobStatus.FAILED, error=str(e))
        notify_item_failed(job_id, url, str(e))
        return False


def _finalize_job(job_id: str, job_temp_dir: str) -> None:
    """Cleanup temp directory and finalize job status."""
    # Cleanup temp directory
    try:
        shutil.rmtree(job_temp_dir)
        logger.debug(f"Cleaned up temp dir: {job_temp_dir}")
    except Exception:
        logger.exception(f"Failed to cleanup temp dir: {job_temp_dir}")

    # Finalize job status
    job = job_manager.get_job(job_id)
    if job and job.status == JobStatus.RUNNING:
        all_done = all(
            i.status in (JobStatus.COMPLETED, JobStatus.FAILED)
            for i in job.items
        )
        if all_done:
            all_failed = all(i.status == JobStatus.FAILED for i in job.items)
            final_status = JobStatus.FAILED if all_failed else JobStatus.COMPLETED
            job_manager.update_job_status(job_id, final_status)

    notify_job_complete(job_id)
    logger.info(f"Job {job_id} finished")


def _process_job(
    job_id: str,
    api_key: str,
    cookies_path: Optional[str],
    is_dev_tier: bool,
) -> None:
    """
    Process a job in a background thread.

    Pipeline: download -> transcribe for each URL.
    """
    job = job_manager.get_job(job_id)
    if not job:
        logger.error(f"Job {job_id} not found")
        return

    logger.info(f"Starting job {job_id} with {len(job.items)} items")

    # Create temp directory for this job
    job_temp_dir = tempfile.mkdtemp(prefix=f"multifetch_job_{job_id}_")

    try:
        for item in job.items:
            # Check for cancellation
            job = job_manager.get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                logger.info(f"Job {job_id} cancelled, stopping processing")
                break

            logger.info(f"Processing URL: {item.url}")

            # Create item-specific temp directory
            item_temp_dir = os.path.join(job_temp_dir, f"item_{item.video_id or 'unknown'}")
            os.makedirs(item_temp_dir, exist_ok=True)

            _process_single_item(
                job, item, job_id, api_key, cookies_path, is_dev_tier,
                item_temp_dir, status_prefix="starting",
            )

    finally:
        _finalize_job(job_id, job_temp_dir)


@process_bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """
    Cancel a running job.

    Returns:
        Updated job status
    """
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        return jsonify({
            "error": f"Cannot cancel job with status {job.status.value}",
            "job": job.to_dict(),
        }), 400

    success = job_manager.cancel_job(job_id)
    if success:
        notify_job_complete(job_id)
        return jsonify({
            "message": "Job cancelled",
            "job": job_manager.get_job(job_id).to_dict(),
        })
    else:
        return jsonify({"error": "Failed to cancel job"}), 500


@process_bp.route("/jobs/<job_id>/retry", methods=["POST"])
def retry_failed_items(job_id: str):
    """
    Retry failed items in a completed job.

    Expects JSON body:
    {
        "api_key": "gsk_...",           # Required: Groq API key
        "cookies_path": "/path/to/...",  # Optional: Path to cookies file
        "is_dev_tier": false             # Optional: Groq dev tier flag
    }

    Returns:
        Job status JSON
    """
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED):
        return jsonify({
            "error": f"Can only retry completed/failed jobs, current status: {job.status.value}",
        }), 400

    # Get failed items
    failed_urls = [item.url for item in job.items if item.status == JobStatus.FAILED]
    if not failed_urls:
        return jsonify({"message": "No failed items to retry", "job": job.to_dict()})

    # Get configuration from request
    data = request.get_json() or {}
    api_key = data.get("api_key")
    cookies_path = data.get("cookies_path")
    is_dev_tier = data.get("is_dev_tier", False)

    if not api_key:
        return jsonify({"error": "api_key is required"}), 400

    # Reset failed items to pending
    for url in failed_urls:
        job_manager.update_item_status(job_id, url, JobStatus.PENDING, progress=0, error=None)

    # Update job status and restart
    job_manager.update_job_status(job_id, JobStatus.RUNNING)

    # Start processing in background
    thread = threading.Thread(
        target=_retry_failed_items,
        args=(job_id, failed_urls, api_key, cookies_path, is_dev_tier),
        name=f"job-{job_id}-retry",
        daemon=True,
    )
    thread.start()

    notify_job_started(job_id)

    return jsonify({
        "message": f"Retrying {len(failed_urls)} failed items",
        "job": job_manager.get_job(job_id).to_dict(),
    })


def _retry_failed_items(
    job_id: str,
    failed_urls: list[str],
    api_key: str,
    cookies_path: Optional[str],
    is_dev_tier: bool,
) -> None:
    """Retry failed items in a background thread."""
    job = job_manager.get_job(job_id)
    if not job:
        return

    job_temp_dir = tempfile.mkdtemp(prefix=f"multifetch_retry_{job_id}_")

    try:
        for url in failed_urls:
            # Check for cancellation
            job = job_manager.get_job(job_id)
            if not job or job.status == JobStatus.CANCELLED:
                break

            # Find item
            item = next((i for i in job.items if i.url == url), None)
            if not item:
                continue

            logger.info(f"Retrying URL: {url}")

            item_temp_dir = os.path.join(job_temp_dir, f"item_{item.video_id or 'unknown'}")
            os.makedirs(item_temp_dir, exist_ok=True)

            _process_single_item(
                job, item, job_id, api_key, cookies_path, is_dev_tier,
                item_temp_dir, status_prefix="retrying",
            )

    finally:
        _finalize_job(job_id, job_temp_dir)
