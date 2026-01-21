"""
Job management API endpoints for MultiFetch v2.
"""

from flask import Blueprint, request, jsonify

from services.job_manager import job_manager, JobType, JobStatus
from services.platform_detector import validate_urls_batch

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("", methods=["POST"])
def create_job():
    """
    Create a new processing job.

    Request body:
        {
            "urls": ["https://...", ...],
            "job_type": "full",  // "download", "transcribe", or "full"
            "language": "en"
        }

    Response:
        Job object with id and initial status
    """
    data = request.get_json()

    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    urls = data.get("urls", [])
    if not urls:
        return jsonify({"error": "urls is required"}), 400

    if not isinstance(urls, list):
        return jsonify({"error": "urls must be an array"}), 400

    if len(urls) > 100:
        return jsonify({"error": "Maximum 100 URLs per job"}), 400

    # Validate URLs first
    validation_results = validate_urls_batch(urls)
    valid_urls = []
    platform_info = []
    invalid_urls = []

    for result in validation_results:
        if result["valid"]:
            valid_urls.append(result["url"])
            platform_info.append({
                "platform": result["platform"],
                "video_id": result["video_id"],
            })
        else:
            invalid_urls.append({
                "url": result["url"],
                "error": result["error"],
            })

    if not valid_urls:
        return jsonify({
            "error": "No valid URLs provided",
            "invalid_urls": invalid_urls,
        }), 400

    # Parse job type
    job_type_str = data.get("job_type", "full")
    try:
        job_type = JobType(job_type_str)
    except ValueError:
        return jsonify({"error": f"Invalid job_type: {job_type_str}"}), 400

    language = data.get("language", "en")

    # Create the job
    job = job_manager.create_job(
        urls=valid_urls,
        job_type=job_type,
        language=language,
        platform_info=platform_info,
    )

    response = job.to_dict()
    if invalid_urls:
        response["invalid_urls"] = invalid_urls

    return jsonify(response), 201


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    """
    List recent jobs.

    Query params:
        limit: Maximum number of jobs to return (default 50)

    Response:
        {"jobs": [job objects]}
    """
    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 100)  # Cap at 100

    jobs = job_manager.list_jobs(limit=limit)
    return jsonify({"jobs": [job.to_dict() for job in jobs]})


@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """
    Get a specific job by ID.

    Response:
        Job object or 404
    """
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify(job.to_dict())


@jobs_bp.route("/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    """
    Delete a job.

    Response:
        {"deleted": true} or 404
    """
    if job_manager.delete_job(job_id):
        return jsonify({"deleted": True})
    return jsonify({"error": "Job not found"}), 404


@jobs_bp.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """
    Cancel a running or pending job.

    Response:
        Updated job object or error
    """
    if job_manager.cancel_job(job_id):
        job = job_manager.get_job(job_id)
        return jsonify(job.to_dict())

    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({"error": f"Cannot cancel job with status: {job.status.value}"}), 400


@jobs_bp.route("/<job_id>/start", methods=["POST"])
def start_job(job_id: str):
    """
    Start processing a pending job.
    This endpoint will be expanded in Phase 4 to actually process the URLs.

    Response:
        Updated job object or error
    """
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.status != JobStatus.PENDING:
        return jsonify({"error": f"Job is not pending (status: {job.status.value})"}), 400

    # Mark job as running (actual processing will be added in Phase 4)
    job_manager.update_job_status(job_id, JobStatus.RUNNING)

    # TODO: In Phase 4, spawn background task to process URLs
    # For now, just mark it as running

    job = job_manager.get_job(job_id)
    return jsonify(job.to_dict())
