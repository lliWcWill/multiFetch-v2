"""
Disk caching service for MultiFetch v2.
Provides JSON-based caching with TTL support.

Uses JSON serialization for security (safe deserialization).
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Cache configuration from environment
CACHE_DIR = Path(os.getenv("CACHE_DIR", Path.home() / ".multifetch_cache"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", 86400))  # 24 hours default


def _ensure_cache_dir() -> Path:
    """Ensure cache directory exists and return path."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def get_cache_key(url: str, operation: str) -> str:
    """
    Generate a unique cache key for URL and operation combination.

    Args:
        url: The URL being processed
        operation: The operation type (e.g., 'download', 'transcription')

    Returns:
        SHA256 hash string for use as cache filename
    """
    return hashlib.sha256(f"{url}:{operation}".encode()).hexdigest()


def load_from_cache(cache_key: str, ttl_seconds: Optional[int] = None) -> Optional[dict]:
    """
    Load data from disk cache with TTL check.

    Args:
        cache_key: The cache key to load
        ttl_seconds: TTL override in seconds (uses CACHE_TTL_SECONDS if None)

    Returns:
        Cached data dict or None if not found/expired/corrupted
    """
    cache_dir = _ensure_cache_dir()
    cache_file = cache_dir / f"{cache_key}.json"

    if not cache_file.exists():
        return None

    # Check TTL
    ttl = ttl_seconds if ttl_seconds is not None else CACHE_TTL_SECONDS
    try:
        file_age = time.time() - cache_file.stat().st_mtime
        if file_age > ttl:
            logger.debug(f"Cache expired for {cache_key} (age: {file_age:.0f}s, ttl: {ttl}s)")
            cache_file.unlink()
            return None
    except OSError as e:
        logger.warning(f"Error checking cache file age: {e}")
        return None

    # Load and validate JSON
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        logger.debug(f"Cache hit for {cache_key}")
        return data
    except json.JSONDecodeError as e:
        logger.warning(f"Corrupted cache file {cache_key}: {e}")
        try:
            cache_file.unlink()
        except OSError:
            pass
        return None
    except OSError as e:
        logger.warning(f"Error reading cache file: {e}")
        return None


def save_to_cache(cache_key: str, data: dict) -> bool:
    """
    Save JSON-serializable data to disk cache.

    Args:
        cache_key: The cache key to save under
        data: Dictionary of data to cache (must be JSON-serializable)

    Returns:
        True if saved successfully, False otherwise
    """
    cache_dir = _ensure_cache_dir()
    cache_file = cache_dir / f"{cache_key}.json"

    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug(f"Cached data for {cache_key}")
        return True
    except (TypeError, ValueError):
        logger.exception(f"Data not JSON-serializable for {cache_key}")
        return False
    except OSError:
        logger.exception("Error writing cache file")
        return False


def delete_from_cache(cache_key: str) -> bool:
    """
    Delete a cache entry.

    Args:
        cache_key: The cache key to delete

    Returns:
        True if deleted, False if not found or error
    """
    cache_dir = _ensure_cache_dir()
    cache_file = cache_dir / f"{cache_key}.json"

    try:
        if cache_file.exists():
            cache_file.unlink()
            logger.debug(f"Deleted cache for {cache_key}")
            return True
        return False
    except OSError as e:
        logger.warning(f"Error deleting cache file: {e}")
        return False


def clear_expired_cache() -> int:
    """
    Clear all expired cache entries.

    Returns:
        Number of entries cleared
    """
    cache_dir = _ensure_cache_dir()
    cleared = 0
    now = time.time()

    try:
        for cache_file in cache_dir.glob("*.json"):
            try:
                file_age = now - cache_file.stat().st_mtime
                if file_age > CACHE_TTL_SECONDS:
                    cache_file.unlink()
                    cleared += 1
            except OSError:
                pass
    except OSError as e:
        logger.warning(f"Error clearing cache: {e}")

    if cleared > 0:
        logger.info(f"Cleared {cleared} expired cache entries")
    return cleared


def get_cache_stats() -> dict:
    """
    Get cache statistics.

    Returns:
        Dict with cache stats (total_entries, total_size_mb, oldest_entry_age)
    """
    cache_dir = _ensure_cache_dir()
    total_entries = 0
    total_size = 0
    oldest_age = 0
    now = time.time()

    try:
        for cache_file in cache_dir.glob("*.json"):
            try:
                stat = cache_file.stat()
                total_entries += 1
                total_size += stat.st_size
                age = now - stat.st_mtime
                if age > oldest_age:
                    oldest_age = age
            except OSError:
                pass
    except OSError:
        pass

    return {
        "total_entries": total_entries,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "oldest_entry_age_hours": round(oldest_age / 3600, 1),
        "cache_dir": str(cache_dir),
        "ttl_hours": CACHE_TTL_SECONDS / 3600,
    }
