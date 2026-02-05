"""
Audio download service for MultiFetch v2.
Ported from original app.py lines 459-791.

Removes all Streamlit dependencies and integrates with Flask job system.
"""

import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import yt_dlp
from pydub import AudioSegment

from api.sse import notify_item_progress
from services.cache import get_cache_key, load_from_cache, save_to_cache
from services.platform_detector import detect_platform

logger = logging.getLogger(__name__)


def sanitize_filename(title: str) -> str:
    """Sanitize a string for use as a filename."""
    # Remove invalid characters
    safe = re.sub(r'[<>:"/\\|?*]', "", title)
    # Replace spaces with underscores
    safe = re.sub(r"\s+", "_", safe)
    # Limit length
    return safe[:100] if len(safe) > 100 else safe


def get_video_info_yt(url: str, cookies_path: Optional[str] = None) -> dict:
    """Fetch video metadata using yt-dlp."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = cookies_path

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False) or {}
    except Exception as e:
        logger.warning(f"Error fetching video info: {e}")
        return {}


def download_audio(
    url: str,
    job_id: Optional[str] = None,
    cookies_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[dict]]:
    """
    Download audio from URL with multiple fallback strategies.

    Args:
        url: The video URL to download audio from
        job_id: Optional job ID for SSE progress updates
        cookies_path: Optional path to cookies file
        output_dir: Optional output directory (creates temp dir if not provided)

    Returns:
        (audio_path, title, info_dict) or (None, None, error_dict)
    """
    # Check cache first (only for metadata, not file paths)
    cache_key = get_cache_key(url, "download_meta")
    cached_meta = load_from_cache(cache_key)

    platform, video_id = detect_platform(url)

    # Create output directory
    if output_dir:
        temp_dir = output_dir
        cleanup_on_error = False
    else:
        temp_dir = tempfile.mkdtemp(prefix="multifetch_")
        cleanup_on_error = True

    def cleanup():
        """Clean up temp directory on error."""
        if cleanup_on_error and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp dir: {e}")

    # Get video info
    video_info = get_video_info_yt(url, cookies_path) if platform == "youtube" else {}
    video_title = video_info.get("title", f"video_{video_id or 'unknown'}")
    safe_title = sanitize_filename(video_title)

    # Check for cookie file
    cookie_file = None
    if cookies_path and os.path.exists(cookies_path):
        cookie_file = cookies_path
        logger.info("Using provided cookies file")
    elif os.path.exists("cookies.txt"):
        cookie_file = "cookies.txt"
        logger.info("Found default cookies.txt file")

    # Base options for all platforms
    base_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "ignoreerrors": True,
        "no_color": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "skip_unavailable_fragments": True,
    }

    # Progress tracking
    download_progress = {"percent": 0}

    def progress_hook(d):
        """Handle download progress updates."""
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)

            if total and downloaded and total > 0:
                progress = int((downloaded / total) * 50)  # Download is 0-50%
                download_progress["percent"] = progress

                if job_id:
                    notify_item_progress(job_id, url, progress, "downloading")

        elif d["status"] == "finished":
            download_progress["percent"] = 50
            if job_id:
                notify_item_progress(job_id, url, 50, "processing")

    # Platform-specific options
    if platform == "instagram":
        base_opts.update({
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "*/*",
                "Accept-Language": "en-us,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "X-Ig-App-Id": "936619743392459",
                "X-Asbd-Id": "198387",
                "X-Ig-Www-Claim": "0",
                "Origin": "https://www.instagram.com",
                "Referer": "https://www.instagram.com/",
            },
            "extractor_args": {"instagram": {"skip": ["dash"]}},
            "source_address": "0.0.0.0",
        })

    # Build strategy list based on platform
    strategies = _build_download_strategies(
        platform, base_opts, cookie_file, video_info, progress_hook
    )

    # Try all strategies
    last_error = None
    for strategy_name, opts in strategies:
        try:
            logger.info(f"Trying {strategy_name} strategy for {url}")

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

                if info is None:
                    logger.debug(f"Strategy {strategy_name}: No info returned")
                    continue

                title = info.get("title", "Unknown")

                # Find the audio file
                for file in os.listdir(temp_dir):
                    if file.endswith(".mp3"):
                        file_path = os.path.join(temp_dir, file)
                        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        logger.info(f"Downloaded with {strategy_name}: {file_size_mb:.1f}MB")

                        # Cache metadata (not file path)
                        save_to_cache(cache_key, {
                            "title": title,
                            "duration": info.get("duration"),
                            "platform": platform,
                        })

                        return file_path, title, info

                # If no MP3, try to convert
                for file in os.listdir(temp_dir):
                    if file.endswith((".mp4", ".webm", ".m4a", ".opus")):
                        logger.info(f"Converting {file} to MP3")
                        input_path = os.path.join(temp_dir, file)
                        output_path = os.path.join(temp_dir, f"{Path(file).stem}.mp3")

                        try:
                            audio = AudioSegment.from_file(input_path)
                            audio.export(output_path, format="mp3", bitrate="192k")

                            save_to_cache(cache_key, {
                                "title": title,
                                "duration": info.get("duration"),
                                "platform": platform,
                            })

                            logger.info(f"Converted with {strategy_name}")
                            return output_path, title, info
                        except Exception as conv_error:
                            logger.warning(f"Conversion error: {conv_error}")
                            continue

        except Exception as e:
            last_error = e
            error_str = str(e)
            logger.warning(f"{strategy_name} strategy failed: {error_str[:100]}")

            if "Sign in to confirm you're not a bot" in error_str:
                logger.info("Bot detection triggered, trying next strategy")
            elif "429" in error_str:
                logger.info("Rate limited, waiting before next attempt")
                time.sleep(2)

            continue

    # All strategies failed
    cleanup()
    error_msg = f"All download strategies failed. Last error: {str(last_error)[:200]}"
    logger.error(error_msg)
    return None, None, {"error": error_msg}


def _build_download_strategies(
    platform: str,
    base_opts: dict,
    cookie_file: Optional[str],
    video_info: dict,
    progress_hook: Callable,
) -> list[Tuple[str, dict]]:
    """Build list of download strategies based on platform."""
    strategies = []

    if platform == "youtube":
        is_live = video_info.get("is_live", False)
        live_status = video_info.get("live_status", "none")

        # Strategy 1: Android client
        strategy1 = {**base_opts}
        strategy1.update({
            "extractor_args": {"youtube": {"player_client": ["android"]}},
            "user_agent": "Mozilla/5.0 (Linux; Android 11; SM-G973F) AppleWebKit/537.36",
            "progress_hooks": [progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
        strategies.append(("Android Client", strategy1))

        # Strategy 2: iOS client
        strategy2 = {**base_opts}
        strategy2.update({
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android_creator"],
                    "player_skip": ["webpage", "configs"],
                    "include_dash_manifest": False,
                }
            },
            "user_agent": "com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)",
            "http_headers": {
                "Accept": "*/*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
                "X-YouTube-Client-Name": "5",
                "X-YouTube-Client-Version": "19.29.1",
            },
            "progress_hooks": [progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
        if cookie_file:
            strategy2["cookiefile"] = cookie_file
        strategies.append(("iOS Client", strategy2))

        # Strategy 3: TV client
        strategy3 = {**base_opts}
        strategy3.update({
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv_embedded"],
                    "player_skip": ["webpage"],
                }
            },
            "user_agent": "Mozilla/5.0 (ChromiumStylePlatform) Cobalt/40.13031-qa",
            "progress_hooks": [progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
        if cookie_file:
            strategy3["cookiefile"] = cookie_file
        strategies.append(("TV Client", strategy3))

        # Strategy 4: Cookie authentication
        if cookie_file:
            strategy4 = {**base_opts}
            strategy4.update({
                "cookiefile": cookie_file,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0",
                "progress_hooks": [progress_hook],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
            strategies.append(("Cookie Authentication", strategy4))

        # Strategy 5: Web embedded
        strategy5 = {**base_opts}
        strategy5.update({
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_embedded"],
                    "player_skip": ["webpage"],
                }
            },
            "progress_hooks": [progress_hook],
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
        if cookie_file:
            strategy5["cookiefile"] = cookie_file
        strategies.append(("Web Embedded", strategy5))

        # Strategy 6: Live stream optimized
        if is_live or live_status == "was_live":
            strategy6 = {**base_opts}
            strategy6.update({
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "live_from_start": True,
                "hls_use_mpegts": True,
                "wait_for_video": 5,
                "progress_hooks": [progress_hook],
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
            if is_live:
                strategy6["fixup"] = "never"
            strategies.append(("Live Optimized", strategy6))

    else:
        # Standard strategy for other platforms
        standard_strategy = {**base_opts}
        standard_strategy["progress_hooks"] = [progress_hook]
        standard_strategy["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
        strategies = [("Standard", standard_strategy)]

    return strategies
