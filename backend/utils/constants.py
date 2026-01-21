"""
Platform patterns and constants for MultiFetch v2.
Ported from original app.py lines 83-122.
"""

import re

# Supported platforms for single video URLs
SUPPORTED_PLATFORMS = {
    "youtube": re.compile(
        r"^((?:https?:)?\/\/)?((?:www|m)\.)?(youtube(?:-nocookie)?\.com|youtu\.be)"
        r"\/(?:watch\?v=|embed\/|live\/|v\/|shorts\/)?(?P<id>[\w\-]{11})(\S+)?$",
        re.IGNORECASE,
    ),
    "instagram": re.compile(
        r"^(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:p|reel)\/(?P<id>[^/?#&]+)",
        re.IGNORECASE,
    ),
    "tiktok": re.compile(
        r"^https?:\/\/(?:www\.|m\.|vm\.)?tiktok\.com\/(?:@[\w\.-]+\/video\/|t\/|(?:@[\w\.-]+\/)?(?:video\/)?)?(?P<id>\d+|\w{7,})",
        re.IGNORECASE,
    ),
}

# TikTok collection URL patterns (profiles, hashtags, sounds, collections)
TIKTOK_COLLECTION_PATTERNS = {
    "user_profile": re.compile(
        r"^https?:\/\/(?:www\.|m\.)?tiktok\.com\/@(?P<username>[\w\.-]+)\/?$",
        re.IGNORECASE,
    ),
    "hashtag": re.compile(
        r"^https?:\/\/(?:www\.|m\.)?tiktok\.com\/tag\/(?P<tag>[\w\.-]+)",
        re.IGNORECASE,
    ),
    "sound": re.compile(
        r"^https?:\/\/(?:www\.|m\.)?tiktok\.com\/music\/(?P<sound>[^/?]+)",
        re.IGNORECASE,
    ),
    "collection": re.compile(
        r"^https?:\/\/(?:www\.|m\.)?tiktok\.com\/@[\w\.-]+\/collection\/(?P<id>[\w-]+)",
        re.IGNORECASE,
    ),
    "short_url": re.compile(
        r"^https?:\/\/(?:www\.|m\.|vm\.)?tiktok\.com\/t\/(?P<code>[\w-]+)",
        re.IGNORECASE,
    ),
}

# Audio processing limits
MAX_FILE_SIZE_MB = 25  # Groq free tier limit
MAX_FILE_SIZE_DEV_MB = 100  # Groq dev tier limit
CHUNK_LENGTH_MS = 600000  # 10 minutes
OVERLAP_MS = 10000  # 10 seconds
