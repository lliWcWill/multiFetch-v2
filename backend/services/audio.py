"""
Audio processing service for MultiFetch v2.
Ported from original app.py lines 1054-1185.

Handles audio chunking for Groq API file size limits.
"""

import contextlib
import logging
import os
import tempfile
from typing import Any, Generator

from pydub import AudioSegment

logger = logging.getLogger(__name__)

# Constants
FREE_TIER_MAX_MB = 25
DEV_TIER_MAX_MB = 100
MIN_CHUNK_DURATION_MS = 30000  # 30 seconds minimum
MAX_CHUNK_DURATION_FREE_MS = 600000  # 10 minutes max for free tier
MAX_CHUNK_DURATION_DEV_MS = 900000  # 15 minutes max for dev tier
OVERLAP_MS = 500  # 0.5 seconds overlap between chunks


def chunk_audio(
    audio_path: str,
    max_chunk_size_mb: int = 24,
    is_dev_tier: bool = False,
) -> list[dict[str, Any]]:
    """
    Split audio into chunks that fit within Groq's size limits.

    Args:
        audio_path: Path to the audio file (MP3)
        max_chunk_size_mb: Maximum chunk size in MB (default 24 for safety margin)
        is_dev_tier: Whether user has dev tier (allows larger chunks)

    Returns:
        List of chunk dictionaries with keys:
        - path: Path to chunk file
        - start_ms: Start time in milliseconds
        - end_ms: End time in milliseconds
        - index: Chunk index
        - duration_ms: Chunk duration
        - size_mb: Chunk file size in MB
    """
    try:
        logger.info(f"Loading audio file for chunking: {audio_path}")
        audio = AudioSegment.from_mp3(audio_path)

        total_length_ms = len(audio)
        total_length_min = total_length_ms / 1000 / 60
        logger.info(f"Audio length: {total_length_min:.1f} minutes")

        # Calculate chunk duration based on file size
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)

        # Guard against empty/zero-size files
        if file_size_mb <= 0:
            logger.warning(f"File size is 0 or negative ({file_size_mb}MB), returning as single chunk")
            return [{
                "path": audio_path,
                "start_ms": 0,
                "end_ms": total_length_ms,
                "index": 0,
                "duration_ms": total_length_ms,
                "size_mb": file_size_mb,
            }]

        # Use 50% of max size for safety margin
        target_chunk_size_mb = max_chunk_size_mb * 0.5

        # Estimate chunk duration to stay under size limit
        minutes_per_chunk = (target_chunk_size_mb / file_size_mb) * total_length_min
        chunk_duration_ms = int(minutes_per_chunk * 60 * 1000)

        # Adjust for tier
        if is_dev_tier:
            # For dev tier, aim for chunks safely under 25MB
            mb_per_minute = 1.44  # 192kbps
            safe_chunk_size_mb = 20.0
            optimal_minutes = safe_chunk_size_mb / mb_per_minute
            chunk_duration_ms = min(int(optimal_minutes * 60 * 1000), MAX_CHUNK_DURATION_DEV_MS)
            logger.info(
                f"Using dev tier settings: target {safe_chunk_size_mb:.1f}MB, "
                f"~{optimal_minutes:.1f} minutes per chunk"
            )
        else:
            chunk_duration_ms = min(chunk_duration_ms, MAX_CHUNK_DURATION_FREE_MS)

        # Ensure minimum chunk duration
        chunk_duration_ms = max(chunk_duration_ms, MIN_CHUNK_DURATION_MS)

        logger.info(
            f"File size: {file_size_mb:.1f}MB, chunking into ~{minutes_per_chunk:.1f} minute segments"
        )

        chunks = []
        start_ms = 0
        chunk_index = 0
        max_iterations = 1000

        while start_ms < total_length_ms and chunk_index < max_iterations:
            end_ms = min(start_ms + chunk_duration_ms, total_length_ms)

            # Extract chunk
            chunk = audio[start_ms:end_ms]

            # Create temporary file for chunk
            chunk_file = tempfile.NamedTemporaryFile(
                suffix=".mp3",
                delete=False,
                prefix=f"chunk_{chunk_index}_",
            )

            # Export chunk with appropriate bitrate
            if is_dev_tier:
                chunk.export(
                    chunk_file.name,
                    format="mp3",
                    parameters=["-b:a", "192k"],
                )
            else:
                chunk.export(
                    chunk_file.name,
                    format="mp3",
                    parameters=["-b:a", "64k"],
                )

            chunk_size_mb = os.path.getsize(chunk_file.name) / (1024 * 1024)
            logger.debug(
                f"Chunk {chunk_index}: {start_ms/1000:.1f}s - {end_ms/1000:.1f}s "
                f"({chunk_size_mb:.1f}MB)"
            )

            chunks.append({
                "path": chunk_file.name,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "index": chunk_index,
                "duration_ms": end_ms - start_ms,
                "size_mb": chunk_size_mb,
            })

            # Check if we've reached the end
            if end_ms >= total_length_ms:
                logger.debug(f"Reached end of audio at {end_ms}ms")
                break

            # Warn if chunk is still too large (before incrementing index)
            if chunk_size_mb > max_chunk_size_mb:
                logger.warning(f"Chunk {chunk_index} is {chunk_size_mb:.1f}MB, exceeds target!")

            # Move to next chunk (with overlap except for final chunk)
            if end_ms + chunk_duration_ms >= total_length_ms:
                start_ms = end_ms  # No overlap for final chunk
            else:
                start_ms = end_ms - OVERLAP_MS

            chunk_index += 1

        if chunk_index >= max_iterations:
            logger.warning(f"Reached maximum iterations ({max_iterations})")

        logger.info(f"Created {len(chunks)} chunks")
        return chunks

    except Exception as e:
        logger.error(f"Error in chunk_audio: {type(e).__name__}: {e}")

        # Return original file as single chunk on error
        return [{
            "path": audio_path,
            "start_ms": 0,
            "end_ms": 0,
            "index": 0,
            "duration_ms": 0,
            "size_mb": os.path.getsize(audio_path) / (1024 * 1024),
        }]


@contextlib.contextmanager
def chunk_audio_context(
    audio_path: str,
    max_chunk_size_mb: int = 24,
    is_dev_tier: bool = False,
) -> Generator[list[dict[str, Any]], None, None]:
    """
    Context manager for audio chunking with automatic cleanup.

    Usage:
        with chunk_audio_context(audio_path) as chunks:
            for chunk in chunks:
                process(chunk['path'])
        # Chunk files are automatically deleted after context exits

    Args:
        audio_path: Path to the audio file
        max_chunk_size_mb: Maximum chunk size in MB
        is_dev_tier: Whether user has dev tier

    Yields:
        List of chunk dictionaries
    """
    chunks = []
    try:
        chunks = chunk_audio(audio_path, max_chunk_size_mb, is_dev_tier)
        yield chunks
    finally:
        # Cleanup all chunk files (except original audio)
        for chunk in chunks:
            if chunk["path"] != audio_path:
                try:
                    os.unlink(chunk["path"])
                    logger.debug(f"Cleaned up chunk: {chunk['path']}")
                except OSError:
                    pass


def get_audio_info(audio_path: str) -> dict[str, Any]:
    """
    Get information about an audio file.

    Args:
        audio_path: Path to the audio file

    Returns:
        Dictionary with duration_ms, duration_min, size_mb
    """
    try:
        audio = AudioSegment.from_mp3(audio_path)
        duration_ms = len(audio)
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)

        return {
            "duration_ms": duration_ms,
            "duration_min": duration_ms / 1000 / 60,
            "size_mb": size_mb,
        }
    except Exception as e:
        logger.error(f"Error getting audio info: {e}")
        return {
            "duration_ms": 0,
            "duration_min": 0,
            "size_mb": os.path.getsize(audio_path) / (1024 * 1024) if os.path.exists(audio_path) else 0,
        }


def should_chunk_audio(audio_path: str, is_dev_tier: bool = False) -> bool:
    """
    Determine if audio needs to be chunked based on size and duration.

    Args:
        audio_path: Path to the audio file
        is_dev_tier: Whether user has dev tier

    Returns:
        True if audio should be chunked
    """
    info = get_audio_info(audio_path)
    size_mb = info["size_mb"]
    duration_min = info["duration_min"]

    # Always chunk if over limits
    max_direct_size = DEV_TIER_MAX_MB * 0.95 if is_dev_tier else FREE_TIER_MAX_MB * 0.92

    return size_mb > 25 or duration_min > 30 or size_mb > max_direct_size
