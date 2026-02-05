"""
Transcription service for MultiFetch v2.
Ported from original app.py lines 1187-1573.

Handles Groq Whisper transcription with rate limiting and parallel processing.
"""

import hashlib
import logging
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from groq import Groq

from api.sse import notify_item_progress
from services.audio import chunk_audio_context, get_audio_info, should_chunk_audio
from services.cache import get_cache_key, load_from_cache, save_to_cache
from services.job_manager import JobStatus, job_manager

logger = logging.getLogger(__name__)

# Constants
FREE_TIER_MAX_MB = 25
DEV_TIER_MAX_MB = 100
DEFAULT_RPM = 400  # Groq's rate limit for whisper-large-v3-turbo


class RateLimiter:
    """
    Rate limiter for API requests with per-API-key instance management.

    Implements token bucket algorithm with sliding window.
    """

    _instances: dict[str, "RateLimiter"] = {}
    _instances_lock = threading.Lock()

    def __init__(self, rpm: int = DEFAULT_RPM):
        """
        Initialize rate limiter.

        Args:
            rpm: Requests per minute limit
        """
        self.rpm = rpm
        self.lock = threading.Lock()
        self.requests: list[float] = []
        self.min_interval = 60.0 / rpm

    @classmethod
    def for_api_key(cls, api_key: str, rpm: int = DEFAULT_RPM) -> "RateLimiter":
        """
        Get or create a rate limiter for a specific API key.

        Args:
            api_key: The Groq API key
            rpm: Requests per minute limit

        Returns:
            RateLimiter instance for this API key
        """
        key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
        with cls._instances_lock:
            if key_hash not in cls._instances:
                cls._instances[key_hash] = cls(rpm)
            return cls._instances[key_hash]

    def wait_if_needed(self) -> None:
        """Wait if necessary to maintain rate limit."""
        with self.lock:
            now = time.time()
            # Remove requests older than 1 minute
            self.requests = [t for t in self.requests if now - t < 60]

            if len(self.requests) >= self.rpm:
                # Calculate wait time to next available slot
                oldest_request = self.requests[0]
                wait_time = 60.0 - (now - oldest_request) + 0.1
                if wait_time > 0:
                    logger.debug(f"Rate limit wait: {wait_time:.2f}s")
                    time.sleep(wait_time)
                    return self.wait_if_needed()

            # Enforce minimum interval between requests
            if self.requests:
                time_since_last = now - self.requests[-1]
                if time_since_last < self.min_interval:
                    wait_time = self.min_interval - time_since_last
                    time.sleep(wait_time)

            self.requests.append(time.time())


def transcribe_with_retry(
    client: Groq,
    audio_path: str,
    language: str = "en",
    max_retries: int = 5,
    rate_limiter: Optional[RateLimiter] = None,
    is_dev_tier: bool = False,
) -> Optional[str]:
    """
    Transcribe audio with exponential backoff retry.

    Args:
        client: Groq client instance
        audio_path: Path to audio file
        language: Language code for transcription
        max_retries: Maximum retry attempts
        rate_limiter: Optional rate limiter instance
        is_dev_tier: Whether user has dev tier

    Returns:
        Transcribed text or None on failure

    Raises:
        Exception: If file too large or all retries exhausted
    """
    # Check file size
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    max_allowed = DEV_TIER_MAX_MB if is_dev_tier else FREE_TIER_MAX_MB

    if file_size_mb > max_allowed:
        tier_name = "dev tier" if is_dev_tier else "free tier"
        raise Exception(
            f"File is {file_size_mb:.1f}MB, exceeds Groq's {tier_name} maximum of {max_allowed}MB"
        )

    base_delay = 5
    max_delay = 120

    for attempt in range(max_retries):
        # Apply rate limiting
        if rate_limiter:
            rate_limiter.wait_if_needed()

        try:
            with open(audio_path, "rb") as audio_file:
                logger.info(
                    f"Sending {file_size_mb:.1f}MB file to Groq API "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

                response = client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language=language,
                    temperature=0.0,
                    prompt="Transcribe this audio accurately, including any technical terms.",
                )
                return response.strip()

        except Exception as e:
            error_str = str(e)

            if "413" in error_str or "too large" in error_str.lower():
                tier_msg = f"{'dev' if is_dev_tier else 'free'} tier ({max_allowed}MB)"
                raise Exception(f"File too large for Groq API {tier_msg}: {file_size_mb:.1f}MB")

            elif "503" in error_str or "Service Unavailable" in error_str:
                wait_time = min(base_delay * (2 ** attempt) + random.uniform(0, 5), max_delay)
                if attempt < max_retries - 1:
                    logger.warning(f"Service unavailable (503), waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    if attempt >= 2:
                        logger.info("Adding cooldown after multiple 503s")
                        time.sleep(30)
                    continue
                else:
                    logger.error(f"Failed after {max_retries} retries: {error_str}")

            elif "429" in error_str or "rate" in error_str.lower():
                wait_time = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                if attempt < max_retries - 1:
                    logger.warning(f"Rate limited, waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue

            # For other errors, retry with shorter wait
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed: {error_str[:100]}")
                time.sleep(base_delay)
                continue
            else:
                raise e

    return None


def transcribe_audio(
    audio_path: str,
    api_key: str,
    job_id: Optional[str] = None,
    url: Optional[str] = None,
    language: str = "en",
    is_dev_tier: bool = False,
) -> Optional[str]:
    """
    Transcribe audio with chunking and parallel processing for large files.

    Args:
        audio_path: Path to audio file
        api_key: Groq API key
        job_id: Optional job ID for SSE updates and cancellation checking
        url: Optional URL for SSE updates
        language: Language code for transcription
        is_dev_tier: Whether user has dev tier

    Returns:
        Full transcription text or None on failure
    """
    # Check cache
    cache_key = get_cache_key(audio_path, "transcription")
    cached_transcription = load_from_cache(cache_key)
    if cached_transcription and isinstance(cached_transcription, dict):
        cached_text = cached_transcription.get("text")
        if cached_text:
            logger.info("Using cached transcription")
            return cached_text

    # Create Groq client for this job
    client = Groq(api_key=api_key)
    rate_limiter = RateLimiter.for_api_key(api_key)

    # Get audio info
    info = get_audio_info(audio_path)
    file_size_mb = info["size_mb"]
    duration_minutes = info["duration_min"]

    logger.info(f"Transcribing: {file_size_mb:.1f}MB, {duration_minutes:.1f} minutes")

    # Determine if we need chunking
    needs_chunking = should_chunk_audio(audio_path, is_dev_tier)

    if not needs_chunking:
        # Direct transcription for small files
        logger.info("File small enough for direct transcription")
        try:
            transcription = transcribe_with_retry(
                client, audio_path, language,
                rate_limiter=rate_limiter,
                is_dev_tier=is_dev_tier,
            )
            if transcription:
                save_to_cache(cache_key, {"text": transcription})
                if job_id and url:
                    notify_item_progress(job_id, url, 90, "completed_transcription")
            return transcription
        except Exception as e:
            logger.error(f"Direct transcription failed: {e}")
            return None

    # Need chunking - use context manager for cleanup
    logger.info(f"File requires chunking (size: {file_size_mb:.1f}MB, duration: {duration_minutes:.1f}min)")

    with chunk_audio_context(audio_path, max_chunk_size_mb=20, is_dev_tier=is_dev_tier) as chunks:
        # Check if chunking produced viable chunks
        if len(chunks) == 1 and chunks[0]["size_mb"] > 25:
            logger.error("Chunking failed - chunks still too large")
            return None

        # Determine parallel vs sequential
        use_parallel = duration_minutes >= 30
        num_chunks = len(chunks)

        if use_parallel:
            transcription = _transcribe_parallel(
                client, chunks, language, rate_limiter, is_dev_tier,
                job_id, url, duration_minutes,
            )
        else:
            transcription = _transcribe_sequential(
                client, chunks, language, rate_limiter, is_dev_tier,
                job_id, url,
            )

        if transcription:
            save_to_cache(cache_key, {"text": transcription})
            logger.info("Transcription complete and cached")

        return transcription


def _transcribe_parallel(
    client: Groq,
    chunks: list[dict],
    language: str,
    rate_limiter: RateLimiter,
    is_dev_tier: bool,
    job_id: Optional[str],
    url: Optional[str],
    duration_minutes: float,
) -> Optional[str]:
    """Transcribe chunks in parallel using ThreadPoolExecutor."""
    logger.info(f"Using parallel transcription for {duration_minutes:.1f} minute video")

    # Calculate optimal workers
    num_chunks = len(chunks)
    if duration_minutes < 30:
        num_workers = 1
    elif duration_minutes < 120:
        num_workers = min(10 if is_dev_tier else 5, max(5 if is_dev_tier else 3, num_chunks // 5))
    else:
        num_workers = min(8 if is_dev_tier else 3, max(4 if is_dev_tier else 2, num_chunks // 10))

    logger.info(f"Using {num_workers} parallel workers for {num_chunks} chunks")

    transcriptions: dict[int, str] = {}
    failed_chunks: list[int] = []

    def transcribe_chunk(chunk_info: dict) -> tuple[int, Optional[str]]:
        """Transcribe a single chunk."""
        # Check for job cancellation
        if job_id:
            job = job_manager.get_job(job_id)
            if job and job.status == JobStatus.CANCELLED:
                logger.info(f"Job {job_id} cancelled, stopping chunk {chunk_info['index']}")
                return chunk_info["index"], None

        try:
            chunk_text = transcribe_with_retry(
                client,
                chunk_info["path"],
                language,
                max_retries=5,
                rate_limiter=rate_limiter,
                is_dev_tier=is_dev_tier,
            )
            return chunk_info["index"], chunk_text
        except Exception as e:
            logger.error(f"Error transcribing chunk {chunk_info['index']}: {e}")
            return chunk_info["index"], None

    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        future_to_chunk = {
            executor.submit(transcribe_chunk, chunk): chunk
            for chunk in chunks
        }

        for i, future in enumerate(as_completed(future_to_chunk)):
            # Check for cancellation
            if job_id:
                job = job_manager.get_job(job_id)
                if job and job.status == JobStatus.CANCELLED:
                    logger.info(f"Job {job_id} cancelled, stopping parallel processing")
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

            chunk_index, chunk_text = future.result()

            if chunk_text:
                transcriptions[chunk_index] = chunk_text
                words = len(chunk_text.split())
                logger.info(f"Chunk {chunk_index} transcribed: {words} words")
            else:
                failed_chunks.append(chunk_index)
                logger.warning(f"Chunk {chunk_index} failed")

            # Send progress update
            if job_id and url:
                progress = 50 + int((i + 1) / num_chunks * 40)  # 50-90%
                notify_item_progress(job_id, url, progress, "transcribing")

    # Retry failed chunks sequentially
    if failed_chunks:
        logger.info(f"Retrying {len(failed_chunks)} failed chunks sequentially")
        time.sleep(30)  # Cooldown

        for chunk_index in failed_chunks:
            if job_id:
                job = job_manager.get_job(job_id)
                if job and job.status == JobStatus.CANCELLED:
                    break

            chunk = next(c for c in chunks if c["index"] == chunk_index)
            try:
                chunk_text = transcribe_with_retry(
                    client,
                    chunk["path"],
                    language,
                    max_retries=3,
                    rate_limiter=rate_limiter,
                    is_dev_tier=is_dev_tier,
                )
                if chunk_text:
                    transcriptions[chunk_index] = chunk_text
                    logger.info(f"Chunk {chunk_index} transcribed on retry")
            except Exception as e:
                logger.error(f"Chunk {chunk_index} failed on retry: {e}")

    # Combine transcriptions in order
    full_text = " ".join(
        transcriptions.get(i, "") for i in range(num_chunks)
    ).strip()

    return full_text if full_text else None


def _transcribe_sequential(
    client: Groq,
    chunks: list[dict],
    language: str,
    rate_limiter: RateLimiter,
    is_dev_tier: bool,
    job_id: Optional[str],
    url: Optional[str],
) -> Optional[str]:
    """Transcribe chunks sequentially."""
    logger.info("Using sequential transcription")

    transcriptions: list[dict] = []
    num_chunks = len(chunks)

    for i, chunk in enumerate(chunks):
        # Check for cancellation
        if job_id:
            job = job_manager.get_job(job_id)
            if job and job.status == JobStatus.CANCELLED:
                logger.info(f"Job {job_id} cancelled, stopping transcription")
                break

        # Send progress update
        if job_id and url:
            progress = 50 + int((i + 1) / num_chunks * 40)  # 50-90%
            notify_item_progress(job_id, url, progress, "transcribing")

        logger.info(f"Transcribing chunk {i + 1}/{num_chunks}")

        try:
            chunk_text = transcribe_with_retry(
                client,
                chunk["path"],
                language,
                rate_limiter=rate_limiter,
                is_dev_tier=is_dev_tier,
            )
            if chunk_text:
                transcriptions.append({
                    "text": chunk_text,
                    "start_ms": chunk["start_ms"],
                    "end_ms": chunk["end_ms"],
                })
                words = len(chunk_text.split())
                logger.info(f"Chunk {i + 1} transcribed: {words} words")
            else:
                logger.warning(f"Chunk {i + 1} returned empty transcription")
        except Exception as e:
            logger.error(f"Error transcribing chunk {i + 1}: {e}")

    if not transcriptions:
        return None

    full_text = " ".join(t["text"] for t in transcriptions)
    return full_text.strip() if full_text else None
