"""
Platform detection service for MultiFetch v2.
Ported from original app.py lines 323-399.
"""

from typing import Optional, Tuple
import os

import validators
import yt_dlp

from utils.constants import SUPPORTED_PLATFORMS, TIKTOK_COLLECTION_PATTERNS


def detect_platform(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect platform and extract video ID from a single video URL.

    Args:
        url: The URL to analyze

    Returns:
        (platform, video_id) or (None, None) if not recognized
    """
    url = url.strip()
    for platform, regex in SUPPORTED_PLATFORMS.items():
        match = regex.search(url)
        if match:
            return platform, match.group("id")
    return None, None


def detect_tiktok_collection(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect if URL is a TikTok collection (profile, hashtag, sound, or collection).

    Args:
        url: The URL to analyze

    Returns:
        (collection_type, identifier) or (None, None) if not a collection
    """
    url = url.strip()
    for collection_type, regex in TIKTOK_COLLECTION_PATTERNS.items():
        match = regex.match(url)
        if match:
            groups = match.groupdict()
            identifier = next(iter(groups.values()), None)
            return collection_type, identifier
    return None, None


def resolve_tiktok_short_url(
    url: str, cookies_path: Optional[str] = None
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Resolve a TikTok short URL (/t/) to determine if it's a collection.

    Args:
        url: The short TikTok URL to resolve
        cookies_path: Optional path to cookies file

    Returns:
        (is_collection, resolved_url, title)
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "skip_download": True,
        "socket_timeout": 30,
    }

    if cookies_path and os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = cookies_path
    elif os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                is_playlist = info.get("_type") == "playlist" or "entries" in info
                resolved_url = info.get("webpage_url", url)
                title = info.get("title", "")
                return is_playlist, resolved_url, title
    except Exception as e:
        print(f"Error resolving short URL: {e}")

    return False, url, None


def validate_url(url: str) -> dict:
    """
    Validate if URL is supported and return detailed information.

    Args:
        url: The URL to validate

    Returns:
        dict with validation results:
        {
            "valid": bool,
            "url": str,
            "platform": str | None,
            "video_id": str | None,
            "is_collection": bool,
            "collection_type": str | None,
            "error": str | None
        }
    """
    result = {
        "valid": False,
        "url": url,
        "platform": None,
        "video_id": None,
        "is_collection": False,
        "collection_type": None,
        "error": None,
    }

    # Basic URL validation
    if not validators.url(url):
        result["error"] = "Invalid URL format"
        return result

    # Check for single video URL
    platform, video_id = detect_platform(url)
    if platform is not None and video_id is not None:
        result["valid"] = True
        result["platform"] = platform
        result["video_id"] = video_id
        return result

    # Check for TikTok collection URL
    collection_type, identifier = detect_tiktok_collection(url)
    if collection_type is not None and identifier is not None:
        result["valid"] = True
        result["platform"] = "tiktok"
        result["is_collection"] = True
        result["collection_type"] = collection_type
        result["video_id"] = identifier
        return result

    result["error"] = "Unsupported platform or URL format"
    return result


def validate_urls_batch(urls: list[str]) -> list[dict]:
    """
    Validate multiple URLs and return results for each.

    Args:
        urls: List of URLs to validate

    Returns:
        List of validation result dicts
    """
    return [validate_url(url) for url in urls]
