"""
Job management service for MultiFetch v2.
Handles job creation, status tracking, and results storage.
"""

import uuid
import threading
from datetime import datetime
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    FULL = "full"  # Download + transcribe


@dataclass
class JobItem:
    """Individual item within a job (one URL)."""

    url: str
    platform: Optional[str] = None
    video_id: Optional[str] = None
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    title: Optional[str] = None
    audio_path: Optional[str] = None
    transcript: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class Job:
    """A batch job containing one or more URLs to process."""

    id: str
    job_type: JobType
    status: JobStatus = JobStatus.PENDING
    items: list[JobItem] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    language: str = "en"
    error: Optional[str] = None

    @property
    def progress(self) -> int:
        """Overall job progress (0-100)."""
        if not self.items:
            return 0
        total_progress = sum(item.progress for item in self.items)
        return total_progress // len(self.items)

    @property
    def completed_count(self) -> int:
        return sum(1 for item in self.items if item.status == JobStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for item in self.items if item.status == JobStatus.FAILED)

    def to_dict(self) -> dict:
        """Convert job to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "job_type": self.job_type.value,
            "status": self.status.value,
            "progress": self.progress,
            "item_count": len(self.items),
            "completed_count": self.completed_count,
            "failed_count": self.failed_count,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
            "items": [
                {
                    "url": item.url,
                    "platform": item.platform,
                    "video_id": item.video_id,
                    "status": item.status.value,
                    "progress": item.progress,
                    "title": item.title,
                    "transcript": item.transcript,
                    "error": item.error,
                }
                for item in self.items
            ],
        }


class JobManager:
    """
    Thread-safe job manager with in-memory storage.
    Can be extended to use Redis or database for persistence.
    """

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._subscribers: dict[str, list] = {}  # job_id -> list of SSE queues

    def create_job(
        self,
        urls: list[str],
        job_type: JobType = JobType.FULL,
        language: str = "en",
        platform_info: Optional[list[dict]] = None,
    ) -> Job:
        """
        Create a new job for processing URLs.

        Args:
            urls: List of URLs to process
            job_type: Type of job (download, transcribe, or full)
            language: Language for transcription
            platform_info: Optional pre-validated platform info for each URL

        Returns:
            The created Job instance
        """
        job_id = str(uuid.uuid4())[:8]

        items = []
        for i, url in enumerate(urls):
            item = JobItem(url=url)
            if platform_info and i < len(platform_info):
                info = platform_info[i]
                item.platform = info.get("platform")
                item.video_id = info.get("video_id")
            items.append(item)

        job = Job(
            id=job_id,
            job_type=job_type,
            items=items,
            language=language,
        )

        with self._lock:
            self._jobs[job_id] = job

        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[Job]:
        """List recent jobs, newest first."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(), key=lambda j: j.created_at, reverse=True
            )
            return jobs[:limit]

    def update_job_status(self, job_id: str, status: JobStatus, error: str = None):
        """Update job status."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                job.error = error
                if status == JobStatus.RUNNING and not job.started_at:
                    job.started_at = datetime.utcnow()
                elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                    job.completed_at = datetime.utcnow()

    def update_item_status(
        self,
        job_id: str,
        url: str,
        status: JobStatus,
        progress: int = None,
        title: str = None,
        audio_path: str = None,
        transcript: str = None,
        error: str = None,
    ):
        """Update status of a specific item within a job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return

            for item in job.items:
                if item.url == url:
                    item.status = status
                    if progress is not None:
                        item.progress = progress
                    if title is not None:
                        item.title = title
                    if audio_path is not None:
                        item.audio_path = audio_path
                    if transcript is not None:
                        item.transcript = transcript
                    if error is not None:
                        item.error = error
                    if status == JobStatus.RUNNING and not item.started_at:
                        item.started_at = datetime.utcnow()
                    elif status in (JobStatus.COMPLETED, JobStatus.FAILED):
                        item.completed_at = datetime.utcnow()
                    break

            # Check if all items are done
            all_done = all(
                item.status in (JobStatus.COMPLETED, JobStatus.FAILED)
                for item in job.items
            )
            if all_done:
                all_failed = all(item.status == JobStatus.FAILED for item in job.items)
                job.status = JobStatus.FAILED if all_failed else JobStatus.COMPLETED
                job.completed_at = datetime.utcnow()

    def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        with self._lock:
            if job_id in self._jobs:
                del self._jobs[job_id]
                return True
            return False

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.PENDING, JobStatus.RUNNING):
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.utcnow()
                return True
            return False


# Global job manager instance
job_manager = JobManager()
