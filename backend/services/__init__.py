"""Services module for MultiFetch v2 backend."""

from services.cache import (
    get_cache_key,
    load_from_cache,
    save_to_cache,
    delete_from_cache,
    clear_expired_cache,
    get_cache_stats,
)
from services.job_manager import Job, JobItem, JobManager, JobStatus, JobType, job_manager
from services.platform_detector import (
    detect_platform,
    detect_tiktok_collection,
    validate_url,
    validate_urls_batch,
)

__all__ = [
    # Cache
    "get_cache_key",
    "load_from_cache",
    "save_to_cache",
    "delete_from_cache",
    "clear_expired_cache",
    "get_cache_stats",
    # Job Manager
    "Job",
    "JobItem",
    "JobManager",
    "JobStatus",
    "JobType",
    "job_manager",
    # Platform Detector
    "detect_platform",
    "detect_tiktok_collection",
    "validate_url",
    "validate_urls_batch",
]
