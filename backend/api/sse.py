"""
Server-Sent Events (SSE) endpoint for real-time job progress streaming.
"""

import json
import queue
import threading
from flask import Blueprint, Response, request

from services.job_manager import job_manager, JobStatus

sse_bp = Blueprint("sse", __name__)

# Store SSE subscribers per job
_subscribers: dict[str, list[queue.Queue]] = {}
_subscribers_lock = threading.Lock()


def subscribe_to_job(job_id: str) -> queue.Queue:
    """Subscribe to updates for a specific job."""
    q = queue.Queue()
    with _subscribers_lock:
        if job_id not in _subscribers:
            _subscribers[job_id] = []
        _subscribers[job_id].append(q)
    return q


def unsubscribe_from_job(job_id: str, q: queue.Queue):
    """Unsubscribe from job updates."""
    with _subscribers_lock:
        if job_id in _subscribers:
            try:
                _subscribers[job_id].remove(q)
            except ValueError:
                pass
            if not _subscribers[job_id]:
                del _subscribers[job_id]


def publish_job_update(job_id: str, event_type: str = "update", data: dict = None):
    """
    Publish an update to all subscribers of a job.

    Args:
        job_id: The job ID
        event_type: Event type (update, item_update, complete, error)
        data: The data to send
    """
    with _subscribers_lock:
        if job_id not in _subscribers:
            return
        for q in _subscribers[job_id]:
            try:
                q.put_nowait({
                    "event": event_type,
                    "data": data or {},
                })
            except queue.Full:
                pass


def format_sse(data: dict, event: str = None) -> str:
    """Format data as SSE message."""
    msg = ""
    if event:
        msg += f"event: {event}\n"
    msg += f"data: {json.dumps(data)}\n\n"
    return msg


@sse_bp.route("/jobs/<job_id>/stream")
def stream_job(job_id: str):
    """
    Stream real-time updates for a specific job via SSE.

    The client should connect to this endpoint and listen for events:
    - update: General job status update
    - item_update: Progress update for a specific item
    - complete: Job completed (all items done)
    - error: Job failed

    Example client code:
        const source = new EventSource('/api/sse/jobs/abc123/stream');
        source.onmessage = (e) => console.log(JSON.parse(e.data));
        source.addEventListener('complete', (e) => source.close());
    """
    job = job_manager.get_job(job_id)
    if not job:
        return Response(
            format_sse({"error": "Job not found"}, event="error"),
            mimetype="text/event-stream",
            status=404,
        )

    def generate():
        # Send initial job state
        yield format_sse(job.to_dict(), event="update")

        # If job is already complete, send complete event and close
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            yield format_sse(job.to_dict(), event="complete")
            return

        # Subscribe to updates
        q = subscribe_to_job(job_id)

        try:
            while True:
                try:
                    # Wait for update with timeout (for keepalive)
                    msg = q.get(timeout=30)
                    yield format_sse(msg["data"], event=msg["event"])

                    # If complete, stop streaming
                    if msg["event"] in ("complete", "error"):
                        break
                except queue.Empty:
                    # Send keepalive comment
                    yield ": keepalive\n\n"

                    # Check if job is still active
                    current_job = job_manager.get_job(job_id)
                    if not current_job:
                        break
                    if current_job.status in (
                        JobStatus.COMPLETED,
                        JobStatus.FAILED,
                        JobStatus.CANCELLED,
                    ):
                        yield format_sse(current_job.to_dict(), event="complete")
                        break
        finally:
            unsubscribe_from_job(job_id, q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# Helper functions to be called from job processing code
def notify_job_started(job_id: str):
    """Notify subscribers that a job has started."""
    job = job_manager.get_job(job_id)
    if job:
        publish_job_update(job_id, "update", job.to_dict())


def notify_item_progress(job_id: str, url: str, progress: int, status: str = None):
    """Notify subscribers of item progress update."""
    job = job_manager.get_job(job_id)
    if job:
        publish_job_update(job_id, "item_update", {
            "url": url,
            "progress": progress,
            "status": status,
            "job_progress": job.progress,
        })


def notify_item_complete(job_id: str, url: str, title: str = None, transcript: str = None):
    """Notify subscribers that an item completed."""
    job = job_manager.get_job(job_id)
    if job:
        publish_job_update(job_id, "item_update", {
            "url": url,
            "progress": 100,
            "status": "completed",
            "title": title,
            "transcript": transcript,
            "job_progress": job.progress,
            "completed_count": job.completed_count,
        })


def notify_item_failed(job_id: str, url: str, error: str):
    """Notify subscribers that an item failed."""
    job = job_manager.get_job(job_id)
    if job:
        publish_job_update(job_id, "item_update", {
            "url": url,
            "progress": 0,
            "status": "failed",
            "error": error,
            "job_progress": job.progress,
            "failed_count": job.failed_count,
        })


def notify_job_complete(job_id: str):
    """Notify subscribers that the job is complete."""
    job = job_manager.get_job(job_id)
    if job:
        publish_job_update(job_id, "complete", job.to_dict())
