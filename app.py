import streamlit as st
import yt_dlp
import os
import tempfile
import time
import re
import json
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import concurrent.futures
import validators
from pytube import YouTube
from groq import Groq
from pydub import AudioSegment
import hashlib
import pickle
import random
import zipfile
import pandas as pd
import signal
import sys
import atexit
import warnings
import locale

# Set UTF-8 encoding for console output
if sys.stdout.encoding != 'utf-8':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Suppress Streamlit ScriptRunContext warnings
# Using multiple approaches for maximum compatibility
import logging

# 1. Filter warnings at the warnings module level (kept as fallback)
warnings.filterwarnings("ignore", message=".*missing ScriptRunContext.*")
warnings.filterwarnings("ignore", message=".*Thread.*missing ScriptRunContext.*")

# 2. Also suppress at the logging level for Streamlit's logger
streamlit_logger = logging.getLogger('streamlit.runtime.scriptrunner')
streamlit_logger.setLevel(logging.ERROR)  # Only show errors, not warnings

# Additional loggers that might emit these warnings
for logger_name in ['streamlit.scriptrunner', 'streamlit.report_thread']:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.ERROR)

# Import Streamlit context handling - CRITICAL FIX
try:
    from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx as _get_script_run_ctx
except ImportError:
    try:
        from streamlit.scriptrunner import add_script_run_ctx, get_script_run_ctx as _get_script_run_ctx
    except ImportError:
        # Fallback for older versions
        from streamlit.report_thread import add_report_ctx as add_script_run_ctx
        from streamlit.report_thread import get_report_ctx as _get_script_run_ctx

# Wrapper to handle suppress_warning parameter for compatibility
def get_script_run_ctx(suppress_warning=False):
    """Get script run context with optional warning suppression"""
    try:
        # Try calling with suppress_warning parameter (newer versions)
        return _get_script_run_ctx(suppress_warning=suppress_warning)
    except TypeError:
        # Fallback for older versions that don't support suppress_warning
        return _get_script_run_ctx()

# Page configuration
st.set_page_config(
    page_title="Universal Media Transcription Tool",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
SUPPORTED_PLATFORMS = {
    'youtube': re.compile(
        r'^((?:https?:)?\/\/)?((?:www|m)\.)?(youtube(?:-nocookie)?\.com|youtu\.be)'
        r'\/(?:watch\?v=|embed\/|live\/|v\/|shorts\/)?(?P<id>[\w\-]{11})(\S+)?$',
        re.IGNORECASE
    ),
    'instagram': re.compile(
        r'^(?:https?:\/\/)?(?:www\.)?instagram\.com\/(?:p|reel)\/(?P<id>[^/?#&]+)',
        re.IGNORECASE
    ),
    'tiktok': re.compile(
        r'^https?:\/\/(?:www\.|m\.|vm\.)?tiktok\.com\/(?:@[\w\.-]+\/video\/|t\/|(?:@[\w\.-]+\/)?(?:video\/)?)?(?P<id>\d+|\w{7,})',
        re.IGNORECASE
    )
}

# TikTok collection URL patterns (profiles, hashtags, sounds, collections)
TIKTOK_COLLECTION_PATTERNS = {
    'user_profile': re.compile(
        r'^https?:\/\/(?:www\.|m\.)?tiktok\.com\/@(?P<username>[\w\.-]+)\/?$',
        re.IGNORECASE
    ),
    'hashtag': re.compile(
        r'^https?:\/\/(?:www\.|m\.)?tiktok\.com\/tag\/(?P<tag>[\w\.-]+)',
        re.IGNORECASE
    ),
    'sound': re.compile(
        r'^https?:\/\/(?:www\.|m\.)?tiktok\.com\/music\/(?P<sound>[^/?]+)',
        re.IGNORECASE
    ),
    'collection': re.compile(
        r'^https?:\/\/(?:www\.|m\.)?tiktok\.com\/@[\w\.-]+\/collection\/(?P<id>[\w-]+)',
        re.IGNORECASE
    ),
    # Short URLs (/t/) that may redirect to collections - need dynamic resolution
    'short_url': re.compile(
        r'^https?:\/\/(?:www\.|m\.|vm\.)?tiktok\.com\/t\/(?P<code>[\w-]+)',
        re.IGNORECASE
    ),
}

MAX_FILE_SIZE_MB = 25
CHUNK_LENGTH_MS = 600000  # 10 minutes
OVERLAP_MS = 10000  # 10 seconds
CACHE_DIR = Path.home() / '.media_transcriber_cache'
CACHE_DIR.mkdir(exist_ok=True)

# Initialize session state
if 'downloads' not in st.session_state:
    st.session_state.downloads = {}
if 'transcriptions' not in st.session_state:
    st.session_state.transcriptions = {}
if 'progress' not in st.session_state:
    st.session_state.progress = {}
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = None
if 'processing_queue' not in st.session_state:
    st.session_state.processing_queue = queue.Queue()
if 'active_threads' not in st.session_state:
    st.session_state.active_threads = []
if 'cleanup_handlers' not in st.session_state:
    st.session_state.cleanup_handlers = []
if 'urls_input' not in st.session_state:
    st.session_state.urls_input = ""
if 'displayed_results' not in st.session_state:
    st.session_state.displayed_results = {}
if 'current_batch' not in st.session_state:
    st.session_state.current_batch = []

# TikTok collection session state
if 'tiktok_collections' not in st.session_state:
    st.session_state.tiktok_collections = {}  # {collection_hash: {videos: [], expanded: bool, selected_urls: set()}}

# Global flag for graceful shutdown
shutdown_requested = False

# Track temp files for cleanup
if 'temp_files_to_cleanup' not in st.session_state:
    st.session_state.temp_files_to_cleanup = set()

def register_temp_file(filepath):
    """Register a temporary file for cleanup"""
    if hasattr(st.session_state, 'temp_files_to_cleanup'):
        st.session_state.temp_files_to_cleanup.add(filepath)

def cleanup_temp_files():
    """Clean up temporary files on exit"""
    try:
        print("\n🧹 Cleaning up temporary files...")
        temp_dir = tempfile.gettempdir()
        
        # Clean up registered files
        if hasattr(st.session_state, 'temp_files_to_cleanup'):
            for filepath in list(st.session_state.temp_files_to_cleanup):
                try:
                    if os.path.exists(filepath):
                        os.unlink(filepath)
                        print(f"  ✓ Removed {os.path.basename(filepath)}")
                        st.session_state.temp_files_to_cleanup.remove(filepath)
                except:
                    pass
        
        # Clean up chunk files
        for file in Path(temp_dir).glob("*_chunk*.mp3"):
            try:
                file.unlink()
                print(f"  ✓ Removed {file.name}")
            except:
                pass
                
        # Clean up temporary audio files
        for file in Path(temp_dir).glob("*_groq_optimized.flac"):
            try:
                file.unlink()
                print(f"  ✓ Removed {file.name}")
            except:
                pass
                
        print("✅ Cleanup complete")
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_requested
    shutdown_requested = True
    
    print("\n\n🛑 Shutdown requested - cleaning up...")
    
    # Cancel any active threads
    if hasattr(st.session_state, 'active_threads'):
        for thread in st.session_state.active_threads:
            if thread.is_alive():
                print(f"  ⏹️ Stopping thread: {thread.name}")
    
    # Run cleanup handlers
    if hasattr(st.session_state, 'cleanup_handlers'):
        for handler in st.session_state.cleanup_handlers:
            try:
                handler()
            except:
                pass
    
    # Clean up temp files
    cleanup_temp_files()
    
    print("👋 Goodbye!")
    sys.exit(0)

# Register signal handlers only if we're in the main thread
try:
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        # Register cleanup on normal exit
        atexit.register(cleanup_temp_files)
except Exception as e:
    # Signal handling not available in this environment
    print(f"Note: Signal handlers not available in this environment: {e}")
    pass

# Thread-safe progress update
def update_progress(url_key: str, progress: float, status: str):

    """Thread-safe progress update"""
    st.session_state.progress[url_key] = {
        'progress': progress,
        'status': status
    }
# Caching decorators
@st.cache_data(ttl=3600)
def get_video_info(url: str) -> Dict[str, Any]:
    """Fetch video metadata with caching"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)

@st.cache_resource
def get_groq_client(api_key: str) -> Groq:
    """Cache Groq client instance"""
    return Groq(api_key=api_key)

def debug_instagram_download(url: str, cookies_path: Optional[str] = None):
    """Debug Instagram download issues"""
    print("=== Instagram Download Debug ===")
    print(f"URL: {url}")
    print(f"Cookies path: {cookies_path}")
    
    if cookies_path and os.path.exists(cookies_path):
        print(f"Cookies file exists: Yes")
        with open(cookies_path, 'r') as f:
            lines = f.readlines()
            cookie_lines = [l for l in lines if l.strip() and not l.startswith('#')]
            print(f"Number of cookies: {len(cookie_lines)}")
            
            # Check for essential Instagram cookies
            essential_cookies = ['sessionid', 'csrftoken', 'ds_user_id']
            found_cookies = {}
            for line in cookie_lines:
                parts = line.strip().split('\t')
                if len(parts) >= 7:
                    cookie_name = parts[5]
                    if cookie_name in essential_cookies:
                        found_cookies[cookie_name] = parts[6][:20] + '...'  # Show partial value
            
            print("Essential cookies found:")
            for cookie in essential_cookies:
                if cookie in found_cookies:
                    print(f"  ✓ {cookie}: {found_cookies[cookie]}")
                else:
                    print(f"  ✗ {cookie}: NOT FOUND")
    else:
        print("Cookies file exists: No")
    
    # Try download with verbose output
    ydl_opts = {
        'verbose': True,
        'cookiefile': cookies_path if cookies_path else None,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.54 Safari/537.36',
            'X-Ig-App-Id': '936619743392459',
            'X-Asbd-Id': '198387',
            'X-Ig-Www-Claim': '0',
            'Origin': 'https://www.instagram.com',
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            print("✓ Successfully extracted info")
            print(f"Title: {info.get('title', 'Unknown')}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")

# Utility functions
def detect_platform(url: str) -> Tuple[Optional[str], Optional[str]]:
    """Detect platform and extract video ID"""
    url = url.strip()
    for platform, regex in SUPPORTED_PLATFORMS.items():
        match = regex.search(url)
        if match:
            return platform, match.group('id')
    return None, None

def detect_tiktok_collection(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Detect if URL is a TikTok collection (profile, hashtag, sound, or collection).
    Returns (collection_type, identifier) or (None, None) if not a collection.
    """
    url = url.strip()
    for collection_type, regex in TIKTOK_COLLECTION_PATTERNS.items():
        match = regex.match(url)
        if match:
            # Get the first captured group (username, tag, sound, or id)
            groups = match.groupdict()
            identifier = next(iter(groups.values()), None)
            return collection_type, identifier
    return None, None

def resolve_tiktok_short_url(url: str, cookies_path: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Resolve a TikTok short URL (/t/) to determine if it's a collection.

    Args:
        url: The short TikTok URL to resolve
        cookies_path: Optional path to cookies file

    Returns:
        (is_collection, resolved_url, title)
        - is_collection: True if URL resolves to a collection/playlist
        - resolved_url: The full resolved URL
        - title: The collection/video title if available
    """
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'skip_download': True,
        'socket_timeout': 30,
    }

    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    elif os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                is_playlist = info.get('_type') == 'playlist' or 'entries' in info
                resolved_url = info.get('webpage_url', url)
                title = info.get('title', '')
                return is_playlist, resolved_url, title
    except Exception as e:
        print(f"Error resolving short URL: {e}")

    return False, url, None

def validate_url(url: str) -> bool:
    """Validate if URL is supported (single video or TikTok collection)"""
    if not validators.url(url):
        return False
    # Check for single video URL
    platform, video_id = detect_platform(url)
    if platform is not None and video_id is not None:
        return True
    # Check for TikTok collection URL
    collection_type, identifier = detect_tiktok_collection(url)
    if collection_type is not None and identifier is not None:
        return True
    return False

def get_cache_key(url: str, operation: str) -> str:
    """Generate cache key for URL and operation"""
    return hashlib.md5(f"{url}:{operation}".encode()).hexdigest()

def load_from_cache(cache_key: str) -> Optional[Any]:
    """Load data from disk cache"""
    cache_file = CACHE_DIR / f"{cache_key}.pkl"
    if cache_file.exists():
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except:
            pass
    return None

def save_to_cache(cache_key: str, data: Any):
    """Save data to disk cache"""
    cache_file = CACHE_DIR / f"{cache_key}.pkl"
    try:
        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
    except:
        pass

class DownloadProgressHook:
    """Handle download progress updates with thread safety"""
    def __init__(self, url_key: str, progress_callback=None):
        self.url_key = url_key
        self.progress_callback = progress_callback
        
    def __call__(self, d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            
            # Ensure values are not None before comparison
            if total is not None and downloaded is not None and total > 0:
                progress = downloaded / total
                speed = d.get('speed', 0)
                eta = d.get('eta', 0)
                
                status = f"Downloading: {progress*100:.1f}%"
                if speed is not None and speed > 0:
                    status += f" | Speed: {speed/1024/1024:.1f} MB/s"
                if eta is not None and eta > 0:
                    status += f" | ETA: {eta}s"
                
                update_progress(self.url_key, progress, status)
                
                if self.progress_callback:
                    self.progress_callback(progress)
            else:
                # Fallback when we don't have proper progress info
                update_progress(self.url_key, 0.5, "Downloading...")
                    
        elif d['status'] == 'finished':
            update_progress(self.url_key, 1.0, "Processing audio...")

def download_audio_enhanced(url: str, cookies_path: Optional[str] = None,
                          progress_callback=None) -> Tuple[Optional[str], Optional[str], Optional[Dict]]:
    """Enhanced audio download with multiple fallback strategies and thread context"""
    
    # Get current thread context for Streamlit (suppress warning)
    ctx = get_script_run_ctx(suppress_warning=True)
    if ctx and threading.current_thread() != threading.main_thread():
        add_script_run_ctx(threading.current_thread(), ctx)
    
    # Check cache first
    cache_key = get_cache_key(url, 'download')
    cached_data = load_from_cache(cache_key)
    if cached_data and Path(cached_data['path']).exists():
        return cached_data['path'], cached_data['title'], cached_data['info']
    
    temp_dir = tempfile.mkdtemp()
    
    # Register cleanup handler for this temp directory
    def cleanup_download():
        try:
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass
    
    if hasattr(st.session_state, 'cleanup_handlers'):
        st.session_state.cleanup_handlers.append(cleanup_download)
    
    platform, video_id = detect_platform(url)
    
    # Get video info first
    video_info = get_video_info_yt(url) if platform == 'youtube' else {}
    video_title = video_info.get('title', f'video_{video_id}')
    safe_title = sanitize_filename(video_title)
    
    # Check for cookie file
    cookie_file = None
    if os.path.exists("cookies.txt"):
        cookie_file = "cookies.txt"
        print("🍪 Found cookie file for authentication")
    elif cookies_path and os.path.exists(cookies_path):
        cookie_file = cookies_path
    
    # Base options for all platforms
    base_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'ignoreerrors': True,
        'no_color': True,
        'socket_timeout': 30,
        'retries': 5,
        'fragment_retries': 5,
        'skip_unavailable_fragments': True,
    }
    
    # Track download progress
    download_info = {'downloaded_bytes': 0, 'total_bytes': 0, 'speed': 0, 'eta': 0}
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            download_info['downloaded_bytes'] = d.get('downloaded_bytes', 0)
            download_info['total_bytes'] = d.get('total_bytes', 1)
            download_info['speed'] = d.get('speed', 0)
            download_info['eta'] = d.get('eta', 0)
            
            if progress_callback and download_info['total_bytes'] > 0:
                progress = download_info['downloaded_bytes'] / download_info['total_bytes']
                progress_callback(progress)
                update_progress(url, progress, f"Downloading: {progress*100:.1f}%")
                
        elif d['status'] == 'finished':
            update_progress(url, 1.0, "Processing audio...")
            if progress_callback:
                progress_callback(1.0)
    
    # Platform-specific options
    if platform == 'instagram':
        base_opts.update({
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.54 Safari/537.36',
                'Accept': '*/*',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'X-Ig-App-Id': '936619743392459',
                'X-Asbd-Id': '198387',
                'X-Ig-Www-Claim': '0',
                'Origin': 'https://www.instagram.com',
                'Referer': 'https://www.instagram.com/',
            },
            'extractor_args': {'instagram': {'skip': ['dash']}},
            'source_address': '0.0.0.0',
        })
    
    elif platform == 'youtube':
        # Check if it's a live stream
        is_live = video_info.get('is_live', False)
        live_status = video_info.get('live_status', 'none')
        
        if is_live:
            print("🔴 LIVE NOW - Downloading from live stream...")
        elif live_status == 'was_live':
            print("📺 RECORDED LIVE - Downloading completed live stream...")
    
    # Define YouTube-specific strategies
    youtube_strategies = []
    
    if platform == 'youtube':
        # Strategy 1: Android client (works most reliably)
        strategy1 = {**base_opts}
        strategy1.update({
            'extractor_args': {'youtube': {'player_client': ['android']}},
            'user_agent': 'Mozilla/5.0 (Linux; Android 11; SM-G973F) AppleWebKit/537.36',
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        youtube_strategies.append(("Android Client", strategy1))
        
        # Strategy 2: iOS client with anti-bot headers
        strategy2 = {**base_opts}
        strategy2.update({
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android_creator'],
                    'player_skip': ['webpage', 'configs'],
                    'include_dash_manifest': False,
                }
            },
            'user_agent': 'com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X;)',
            'http_headers': {
                'Accept': '*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Origin': 'https://www.youtube.com',
                'Referer': 'https://www.youtube.com/',
                'X-YouTube-Client-Name': '5',
                'X-YouTube-Client-Version': '19.29.1',
            },
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        if cookie_file:
            strategy2['cookiefile'] = cookie_file
        youtube_strategies.append(("iOS Client", strategy2))
        
        # Strategy 3: TV client (often bypasses restrictions)
        strategy3 = {**base_opts}
        strategy3.update({
            'extractor_args': {
                'youtube': {
                    'player_client': ['tv_embedded'],
                    'player_skip': ['webpage'],
                }
            },
            'user_agent': 'Mozilla/5.0 (ChromiumStylePlatform) Cobalt/40.13031-qa (unlike Gecko) v8/8.8.278.8-jit gles Starboard/12',
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        if cookie_file:
            strategy3['cookiefile'] = cookie_file
        youtube_strategies.append(("TV Client", strategy3))
        
        # Strategy 4: Standard with cookie authentication (if available)
        if cookie_file:
            strategy4 = {**base_opts}
            strategy4.update({
                'cookiefile': cookie_file,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                'progress_hooks': [progress_hook],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            youtube_strategies.append(("Cookie Authentication", strategy4))
        
        # Strategy 5: Web embedded client
        strategy5 = {**base_opts}
        strategy5.update({
            'extractor_args': {
                'youtube': {
                    'player_client': ['web_embedded'],
                    'player_skip': ['webpage'],
                }
            },
            'progress_hooks': [progress_hook],
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
        if cookie_file:
            strategy5['cookiefile'] = cookie_file
        youtube_strategies.append(("Web Embedded", strategy5))
        
        # Strategy 6: Live stream optimized (if applicable)
        if is_live or live_status == 'was_live':
            strategy6 = {**base_opts}
            strategy6.update({
                'format': 'bestaudio[ext=m4a]/bestaudio/best',
                'live_from_start': True,
                'hls_use_mpegts': True,
                'wait_for_video': 5,
                'progress_hooks': [progress_hook],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
            if is_live:
                strategy6['fixup'] = 'never'
            youtube_strategies.append(("Live Optimized", strategy6))
    
    # For other platforms, use standard strategy
    else:
        standard_strategy = {**base_opts}
        standard_strategy['progress_hooks'] = [progress_hook]
        standard_strategy['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        youtube_strategies = [("Standard", standard_strategy)]
    
    # Try all strategies
    last_error = None
    for strategy_name, opts in youtube_strategies:
        try:
            print(f"🔄 Trying {strategy_name} strategy for {url}")
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    print(f"Strategy {strategy_name}: No info returned")
                    continue
                
                title = info.get('title', 'Unknown')
                print(f"Strategy {strategy_name}: Got title: {title}")
                
                # Find the audio file
                for file in os.listdir(temp_dir):
                    if file.endswith('.mp3'):
                        file_path = os.path.join(temp_dir, file)
                        cache_data = {'path': file_path, 'title': title, 'info': info}
                        save_to_cache(cache_key, cache_data)
                        print(f"✅ Downloaded with {strategy_name} strategy!")
                        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                        print(f"📊 File size: {file_size_mb:.1f}MB")
                        return file_path, title, info
                
                # If no MP3, convert the downloaded file
                for file in os.listdir(temp_dir):
                    if file.endswith(('.mp4', '.webm', '.m4a', '.opus')):
                        print(f"Converting {file} to MP3")
                        input_path = os.path.join(temp_dir, file)
                        output_path = os.path.join(temp_dir, f"{Path(file).stem}.mp3")
                        
                        try:
                            audio = AudioSegment.from_file(input_path)
                            audio.export(output_path, format='mp3', bitrate='192k')
                            
                            cache_data = {'path': output_path, 'title': title, 'info': info}
                            save_to_cache(cache_key, cache_data)
                            print(f"✅ Downloaded and converted with {strategy_name} strategy!")
                            return output_path, title, info
                        except Exception as conv_error:
                            print(f"Conversion error: {conv_error}")
                            continue
                
        except Exception as e:
            last_error = e
            print(f"❌ {strategy_name} strategy failed: {str(e)[:100]}...")
            
            # Check for specific errors
            if "Sign in to confirm you're not a bot" in str(e):
                print("🤖 YouTube thinks we're a bot, trying next strategy...")
            elif "429" in str(e):
                print("⏳ Rate limited, waiting before next attempt...")
                time.sleep(2)
            
            continue
    
    # If YouTube strategies failed and we have pytube, try it
    if platform == 'youtube':
        try:
            print("🔄 Trying pytube as final fallback...")
            from pytube import YouTube
            
            yt = YouTube(url)
            audio_stream = yt.streams.filter(only_audio=True, file_extension='mp4').first()
            
            if audio_stream:
                temp_path = audio_stream.download(output_path=temp_dir, filename=f"{safe_title}_temp.mp4")
                
                # Convert to MP3
                audio = AudioSegment.from_file(temp_path, format="mp4")
                output_path = os.path.join(temp_dir, f"{safe_title}.mp3")
                audio.export(output_path, format="mp3", bitrate="192k")
                
                # Cleanup temp file
                os.remove(temp_path)
                
                cache_data = {'path': output_path, 'title': video_title, 'info': video_info}
                save_to_cache(cache_key, cache_data)
                print("✅ Downloaded with pytube!")
                return output_path, video_title, video_info
                
        except Exception as e:
            print(f"❌ Pytube also failed: {str(e)[:100]}...")
    
    # All strategies failed
    error_msg = f"All download strategies failed. Last error: {str(last_error)[:200]}"
    return None, None, {'error': error_msg}

def expand_tiktok_collection(
    url: str,
    cookies_path: Optional[str] = None,
    max_videos: int = 50,
    progress_callback: Optional[callable] = None
) -> Tuple[List[Dict], Optional[str]]:
    """
    Expand a TikTok collection URL to get list of individual video URLs.

    Args:
        url: TikTok collection URL (profile, hashtag, sound, or collection)
        cookies_path: Path to cookies file for authenticated content
        max_videos: Maximum number of videos to retrieve (default 50, max 500)
        progress_callback: Optional callback for progress updates (0.0-1.0, status_message)

    Returns:
        (video_list, error_message)
        video_list: List of dicts with keys: url, title, id, duration, thumbnail, uploader, view_count
        error_message: None on success, error string on failure
    """
    collection_type, identifier = detect_tiktok_collection(url)
    if not collection_type:
        return [], "URL is not a recognized TikTok collection"

    # Cap max_videos to prevent excessive requests
    max_videos = min(max_videos, 500)

    if progress_callback:
        progress_callback(0.1, f"Fetching {collection_type.replace('_', ' ')}: {identifier}")

    # Build yt-dlp options for flat extraction (metadata only, no download)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',  # Get playlist entries without downloading
        'ignoreerrors': True,
        'no_color': True,
        'socket_timeout': 30,
        'playlistend': max_videos,  # Limit number of videos
    }

    # Add cookies if available
    if cookies_path and os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path
    elif os.path.exists("cookies.txt"):
        ydl_opts['cookiefile'] = "cookies.txt"

    # TikTok-specific options
    ydl_opts['http_headers'] = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.tiktok.com/',
    }

    videos = []

    try:
        if progress_callback:
            progress_callback(0.2, "Extracting video list from TikTok...")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if not info:
                return [], "Could not extract information from URL"

            # Handle different response formats
            entries = []
            if 'entries' in info:
                entries = list(info['entries']) if info['entries'] else []
            elif info.get('_type') == 'url':
                # Single video or redirect
                entries = [info]

            if not entries:
                # Check for specific error conditions
                if 'Private' in str(info.get('title', '')):
                    return [], "This collection is private. Please provide cookies from a logged-in account."
                return [], "Collection appears empty or videos are unavailable"

            total = min(len(entries), max_videos)

            for i, entry in enumerate(entries[:max_videos]):
                if entry is None:
                    continue

                if progress_callback:
                    progress = 0.2 + (0.8 * (i + 1) / total)
                    progress_callback(progress, f"Processing video {i + 1} of {total}...")

                # Extract video info
                video_url = entry.get('url') or entry.get('webpage_url')
                if not video_url:
                    # Try to construct URL from ID
                    video_id = entry.get('id')
                    if video_id:
                        video_url = f"https://www.tiktok.com/@{identifier}/video/{video_id}"
                    else:
                        continue

                video_info = {
                    'url': video_url,
                    'title': entry.get('title', f'Video {i + 1}'),
                    'id': entry.get('id', ''),
                    'duration': entry.get('duration', 0),
                    'thumbnail': entry.get('thumbnail', ''),
                    'uploader': entry.get('uploader', identifier),
                    'view_count': entry.get('view_count', 0),
                }

                videos.append(video_info)

        if progress_callback:
            progress_callback(1.0, f"Found {len(videos)} videos")

        return videos, None

    except yt_dlp.utils.DownloadError as e:
        error_str = str(e)
        # Parse common error conditions
        if 'private' in error_str.lower() or 'login' in error_str.lower():
            return [], "This collection requires authentication. Please provide cookies from a logged-in TikTok session."
        elif '404' in error_str or 'not found' in error_str.lower():
            return [], "Collection not found or has been removed"
        elif '429' in error_str or 'rate' in error_str.lower():
            return [], "TikTok is rate limiting requests. Please wait a few minutes and try again."
        else:
            return [], f"Failed to expand collection: {error_str[:200]}"
    except Exception as e:
        return [], f"Unexpected error expanding collection: {str(e)[:200]}"

def get_video_info_yt(url: str) -> Dict[str, Any]:
    """Get YouTube video info including live status"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'is_live': info.get('is_live', False),
                'live_status': info.get('live_status', 'none'),
                'was_live': info.get('live_status') == 'was_live',
                'description': info.get('description', ''),
                'uploader': info.get('uploader', ''),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'upload_date': info.get('upload_date', ''),
            }
    except Exception as e:
        print(f"Error getting video info: {e}")
        return {
            'title': 'Unknown',
            'duration': 0,
            'error': str(e)
        }

def sanitize_filename(filename: str) -> str:
    """Sanitize a string to be used as a filename"""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename or 'untitled'

def create_progress_container():
    """Create a comprehensive progress tracking container"""
    container = st.container()
    with container:
        # Main status
        status_placeholder = st.empty()
        
        # Progress columns
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            main_progress = st.progress(0)
            progress_text = st.empty()
        
        with col2:
            eta_text = st.empty()
        
        with col3:
            speed_text = st.empty()
        
        # Sub-progress for chunks
        sub_progress_container = st.empty()
        
        # Detailed status
        detail_status = st.empty()
        
        # Metrics row
        metrics_container = st.empty()
        
    return {
        'status': status_placeholder,
        'main_progress': main_progress,
        'progress_text': progress_text,
        'eta_text': eta_text,
        'speed_text': speed_text,
        'sub_progress_container': sub_progress_container,
        'detail_status': detail_status,
        'metrics_container': metrics_container,
        'container': container
    }

def update_download_progress(progress_ui, downloaded_bytes, total_bytes, speed=None, eta=None):
    """Update download progress with detailed information"""
    if total_bytes and total_bytes > 0:
        progress = downloaded_bytes / total_bytes
        progress_ui['main_progress'].progress(progress)
        
        # Format sizes
        downloaded_mb = downloaded_bytes / (1024 * 1024)
        total_mb = total_bytes / (1024 * 1024)
        progress_ui['progress_text'].text(f"{downloaded_mb:.1f} / {total_mb:.1f} MB ({progress*100:.1f}%)")
        
        # Speed
        if speed and speed > 0:
            speed_mb = speed / (1024 * 1024)
            progress_ui['speed_text'].text(f"⚡ {speed_mb:.1f} MB/s")
        
        # ETA
        if eta and eta > 0:
            if eta < 60:
                progress_ui['eta_text'].text(f"⏱️ {int(eta)}s remaining")
            else:
                minutes = eta // 60
                seconds = eta % 60
                progress_ui['eta_text'].text(f"⏱️ {int(minutes)}m {int(seconds)}s")

def show_chunk_progress(progress_ui, current_chunk, total_chunks, chunk_info=None):
    """Show progress for chunk processing"""
    with progress_ui['sub_progress_container'].container():
        st.markdown("**📊 Chunk Processing**")
        
        # Chunk progress bar
        chunk_progress = st.progress(current_chunk / total_chunks)
        
        # Chunk details
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"Chunk {current_chunk}/{total_chunks}")
        with col2:
            if chunk_info:
                st.text(f"Size: {chunk_info.get('size_mb', 0):.1f}MB")
        
        return chunk_progress

def chunk_audio(audio_path: str, max_chunk_size_mb: int = 24) -> List[Dict[str, Any]]:
    """Split audio into chunks that fit within Groq's size limits"""
    try:
        print(f"Loading audio file for chunking: {audio_path}")
        audio = AudioSegment.from_mp3(audio_path)
        
        total_length_ms = len(audio)
        total_length_min = total_length_ms / 1000 / 60
        print(f"Audio length: {total_length_min:.1f} minutes")
        
        # Calculate chunk duration based on file size
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        
        # Use 50% of max size for safety margin with 192kbps files
        # This accounts for potential overhead and ensures we stay well under limits
        target_chunk_size_mb = max_chunk_size_mb * 0.5
        
        # Estimate chunk duration to stay under size limit
        # Rough estimate: if full file is X MB for Y minutes, then chunk should be...
        minutes_per_chunk = (target_chunk_size_mb / file_size_mb) * total_length_min
        
        # Convert to milliseconds
        chunk_duration_ms = int(minutes_per_chunk * 60 * 1000)
        
        # For dev tier, we can use larger chunks but need to be conservative
        if max_chunk_size_mb > 50:  # Dev tier
            # For dev tier, aim for chunks that are safely under 25MB
            # With 192k bitrate: ~1.44MB per minute
            mb_per_minute = 1.44  # 192kbps
            # Target 20MB chunks to be safe (well under 25MB limit)
            safe_chunk_size_mb = 20.0
            optimal_minutes = safe_chunk_size_mb / mb_per_minute
            chunk_duration_ms = min(int(optimal_minutes * 60 * 1000), 900000)  # 15 min max
            print(f"Using dev tier settings: target chunk size {safe_chunk_size_mb:.1f}MB, ~{optimal_minutes:.1f} minutes per chunk")
        else:
            chunk_duration_ms = min(chunk_duration_ms, 600000)  # 10 min max for free tier
        
        # Ensure minimum chunk duration of 30 seconds
        chunk_duration_ms = max(chunk_duration_ms, 30000)
        
        # Reduced overlap from 5000ms to 500ms for better performance
        overlap_ms = 500  # 0.5 seconds overlap
        
        print(f"File size: {file_size_mb:.1f}MB, chunking into ~{minutes_per_chunk:.1f} minute segments (target: {target_chunk_size_mb:.1f}MB per chunk)")
        
        chunks = []
        start_ms = 0
        chunk_index = 0
        max_iterations = 1000  # Safety limit to prevent infinite loops
        
        while start_ms < total_length_ms and chunk_index < max_iterations:
            end_ms = min(start_ms + chunk_duration_ms, total_length_ms)
            
            # Extract chunk
            chunk = audio[start_ms:end_ms]
            
            # Create temporary file for chunk
            chunk_file = tempfile.NamedTemporaryFile(
                suffix='.mp3', 
                delete=False,
                prefix=f'chunk_{chunk_index}_'
            )
            
            # Export chunk - use higher bitrate for dev tier
            if max_chunk_size_mb > 50:  # Dev tier
                # Use 192k bitrate for better quality and larger chunks
                chunk.export(
                    chunk_file.name, 
                    format='mp3',
                    parameters=["-b:a", "192k"]
                )
            else:
                # Use lower bitrate for free tier to keep chunks small
                chunk.export(
                    chunk_file.name, 
                    format='mp3',
                    parameters=["-b:a", "64k"]
                )
            
            chunk_size_mb = os.path.getsize(chunk_file.name) / (1024 * 1024)
            print(f"Chunk {chunk_index}: {start_ms/1000:.1f}s - {end_ms/1000:.1f}s ({chunk_size_mb:.1f}MB) - Duration: {(end_ms-start_ms)/1000:.1f}s")
            
            # Register chunk file for cleanup
            register_temp_file(chunk_file.name)
            
            chunks.append({
                'path': chunk_file.name,
                'start_ms': start_ms,
                'end_ms': end_ms,
                'index': chunk_index,
                'duration_ms': end_ms - start_ms,
                'size_mb': chunk_size_mb
            })
            
            # Check if we've reached the end of the audio
            if end_ms >= total_length_ms:
                print(f"Reached end of audio at {end_ms}ms (total: {total_length_ms}ms)")
                break
                
            # Move to next chunk (with overlap for all chunks except the last)
            # Skip overlap if the next chunk would be the final chunk
            if end_ms + chunk_duration_ms >= total_length_ms:
                start_ms = end_ms  # No overlap for the final chunk
            else:
                start_ms = end_ms - overlap_ms
                
            chunk_index += 1
            
            # Safety check - if chunk is still too large, we need smaller chunks
            if chunk_size_mb > max_chunk_size_mb:
                print(f"WARNING: Chunk {chunk_index} is {chunk_size_mb:.1f}MB, still too large!")
                # Could implement recursive splitting here if needed
        
        if chunk_index >= max_iterations:
            print(f"WARNING: Reached maximum iterations ({max_iterations}), possible infinite loop detected!")
        
        print(f"Created {len(chunks)} chunks")
        return chunks
        
    except Exception as e:
        print(f"Error in chunk_audio: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Return the original file as a single chunk on error
        return [{
            'path': audio_path,
            'start_ms': 0,
            'end_ms': 0,
            'index': 0,
            'size_mb': os.path.getsize(audio_path) / (1024 * 1024)
        }]

class RateLimiter:
    """Rate limiter for API requests"""
    def __init__(self, rpm: int):
        self.rpm = rpm
        self.lock = threading.Lock()
        self.requests = []
        self.min_interval = 60.0 / rpm  # Minimum seconds between requests
        
    def wait_if_needed(self):
        """Wait if necessary to maintain rate limit"""
        with self.lock:
            now = time.time()
            # Remove requests older than 1 minute
            self.requests = [t for t in self.requests if now - t < 60]
            
            if len(self.requests) >= self.rpm:
                # Calculate wait time to next available slot
                oldest_request = self.requests[0]
                wait_time = 60.0 - (now - oldest_request) + 0.1  # Small buffer
                if wait_time > 0:
                    print(f"Rate limit wait: {wait_time:.2f}s")
                    time.sleep(wait_time)
                    return self.wait_if_needed()
            
            # Also enforce minimum interval between requests
            if self.requests:
                time_since_last = now - self.requests[-1]
                if time_since_last < self.min_interval:
                    wait_time = self.min_interval - time_since_last
                    time.sleep(wait_time)
                    
            self.requests.append(time.time())

def transcribe_with_retry(client: Groq, audio_path: str, language: str = 'en', 
                         max_retries: int = 5, rate_limiter: Optional['RateLimiter'] = None) -> Optional[str]:
    """Transcribe with exponential backoff retry"""
    
    # First check file size
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    is_dev_tier = st.session_state.get('groq_dev_tier', False)
    max_allowed = 100 if is_dev_tier else 25
    
    if file_size_mb > max_allowed:
        raise Exception(f"File is {file_size_mb:.1f}MB, exceeds Groq's {'dev tier' if is_dev_tier else 'free tier'} maximum of {max_allowed}MB")
    
    base_delay = 5
    max_delay = 120  # Cap at 2 minutes
    
    for attempt in range(max_retries):
        # Apply rate limiting if provided
        if rate_limiter:
            rate_limiter.wait_if_needed()
            
        try:
            with open(audio_path, 'rb') as audio_file:
                # Validate against tier limits
                if file_size_mb > max_allowed:
                    error_msg = f"File size {file_size_mb:.1f}MB exceeds {'dev tier' if is_dev_tier else 'free tier'} limit of {max_allowed}MB"
                    print(f"❌ {error_msg}")
                    raise Exception(error_msg)
                
                print(f"Sending {file_size_mb:.1f}MB file to Groq API (attempt {attempt + 1}/{max_retries})...")
                
                response = client.audio.transcriptions.create(
                    file=audio_file,
                    model="whisper-large-v3-turbo",
                    response_format="text",
                    language=language,
                    temperature=0.0,
                    prompt="Transcribe this audio accurately, including any technical terms."
                )
                return response.strip()
                
        except Exception as e:
            error_str = str(e)
            
            if '413' in error_str or 'too large' in error_str.lower():
                # File too large, don't retry
                tier_msg = "dev tier (100MB)" if is_dev_tier else "free tier (25MB)"
                raise Exception(f"File too large for Groq API {tier_msg}: {file_size_mb:.1f}MB")
            elif '503' in error_str or 'Service Unavailable' in error_str:
                # 503 Service Unavailable - exponential backoff with jitter
                wait_time = min(base_delay * (2 ** attempt) + random.uniform(0, 5), max_delay)
                
                if attempt < max_retries - 1:
                    print(f"Service unavailable (503), waiting {wait_time:.1f}s before retry...")
                    time.sleep(wait_time)
                    
                    # After multiple 503s, add cooldown
                    if attempt >= 2:
                        print("Adding cooldown period after multiple 503s...")
                        time.sleep(30)
                    continue
                else:
                    print(f"Failed after {max_retries} retries: {error_str}")
            elif '429' in error_str or 'rate' in error_str.lower():
                # Rate limit - exponential backoff
                wait_time = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                if attempt < max_retries - 1:
                    print(f"Rate limited, waiting {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue
            
            # For other errors, retry with shorter wait
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed: {error_str[:100]}...")
                time.sleep(base_delay)
                continue
            else:
                raise e
    
    return None

def transcribe_audio(audio_path: str, groq_client: Groq, 
                    progress_callback=None, language: str = 'en') -> Optional[str]:
    """Transcribe audio with chunking and parallel processing support for large files"""
    
    # Check cache
    cache_key = get_cache_key(audio_path, 'transcription')
    cached_transcription = load_from_cache(cache_key)
    if cached_transcription:
        return cached_transcription
    
    try:
        file_size = os.path.getsize(audio_path)
        file_size_mb = file_size / (1024 * 1024)
        print(f"Transcribing audio file: {file_size_mb:.1f}MB")
        
        # Get audio duration
        audio = AudioSegment.from_mp3(audio_path)
        duration_ms = len(audio)
        duration_minutes = duration_ms / 1000 / 60
        print(f"Audio duration: {duration_minutes:.1f} minutes")
    except Exception as e:
        print(f"Error getting file info: {e}")
        file_size_mb = 0
        duration_minutes = 0
    
    # Check if we need to chunk
    # IMPORTANT: Groq's actual limits are 25MB for free tier, 100MB for dev tier
    # But we need to be conservative to account for API overhead
    is_dev_tier = st.session_state.get('groq_dev_tier', False)
    
    # For dev tier, we can send up to 100MB files, but let's be conservative
    # For free tier, limit is 25MB
    max_direct_size_mb = 95 if is_dev_tier else 23
    
    # However, for optimal performance, chunk larger files even on dev tier
    # This prevents connection timeouts and improves reliability
    should_chunk = file_size_mb > 25 or duration_minutes > 30
    
    if not should_chunk and file_size_mb <= max_direct_size_mb:
        # Direct transcription for small files
        print("File small enough for direct transcription")
        transcription = transcribe_with_retry(groq_client, audio_path, language)
        if transcription:
            save_to_cache(cache_key, transcription)
        return transcription
    
    else:
        # Need to chunk the audio
        print(f"File requires chunking (size: {file_size_mb:.1f}MB, duration: {duration_minutes:.1f}min)")
        # For chunking, always target 20MB chunks for reliability
        # This works well for both free and dev tiers
        chunks = chunk_audio(audio_path, max_chunk_size_mb=20)
        
        # Check if chunking actually worked
        if len(chunks) == 1 and chunks[0]['size_mb'] > 25:
            error_msg = (f"File is {file_size_mb:.1f}MB but chunking failed. "
                        "Unable to create chunks small enough for API limits.")
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        # Determine if we should use parallel processing
        use_parallel = duration_minutes >= 30
        
        if use_parallel:
            # Parallel transcription for large files
            print(f"Using parallel transcription for {duration_minutes:.1f} minute video")
            
            # Calculate optimal number of workers based on duration and tier
            is_dev_tier = st.session_state.get('groq_dev_tier', False)
            if duration_minutes < 30:
                num_workers = 1  # Sequential
            elif duration_minutes < 120:  # 30-120 minutes
                if is_dev_tier:
                    num_workers = min(10, max(5, len(chunks) // 5))  # More workers for dev tier
                else:
                    num_workers = min(5, max(3, len(chunks) // 10))
            else:  # 120+ minutes
                if is_dev_tier:
                    num_workers = min(8, max(4, len(chunks) // 10))  # More workers for dev tier
                else:
                    num_workers = min(3, max(2, len(chunks) // 20))
            
            print(f"Using {num_workers} parallel workers for {len(chunks)} chunks")
            
            # Create rate limiter for Groq API (400 RPM for whisper-large-v3-turbo)
            rate_limiter = RateLimiter(rpm=400)
            
            # Parallel processing with ThreadPoolExecutor
            transcriptions = {}
            failed_chunks = []
            
            def transcribe_chunk(chunk_info):
                """Transcribe a single chunk with error handling"""
                chunk_start_time = time.time()
                # Set thread context for Streamlit compatibility
                try:
                    ctx = get_script_run_ctx(suppress_warning=True)
                    if ctx is not None:
                        add_script_run_ctx(threading.current_thread(), ctx)
                except Exception:
                    # Silently ignore context errors - they don't affect functionality
                    pass
                
                try:
                    chunk_text = transcribe_with_retry(
                        groq_client, 
                        chunk_info['path'], 
                        language, 
                        max_retries=5,
                        rate_limiter=rate_limiter
                    )
                    
                    # Clean up chunk file immediately after successful transcription
                    try:
                        if chunk_info['path'] != audio_path:
                            os.unlink(chunk_info['path'])
                            # Remove from cleanup registry
                            if hasattr(st.session_state, 'temp_files_to_cleanup'):
                                st.session_state.temp_files_to_cleanup.discard(chunk_info['path'])
                    except:
                        pass
                    
                    return chunk_info['index'], chunk_text
                except Exception as e:
                    print(f"Error transcribing chunk {chunk_info['index']}: {e}")
                    # Don't delete on error - we might need to retry!
                    return chunk_info['index'], None
            
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                # Submit all chunks
                future_to_chunk = {
                    executor.submit(transcribe_chunk, chunk): chunk 
                    for chunk in chunks
                }
                
                # Process completed chunks
                for i, future in enumerate(as_completed(future_to_chunk)):
                    # Check for shutdown
                    if shutdown_requested:
                        print("\n⚠️ Shutdown requested - cancelling remaining chunks")
                        executor.shutdown(wait=False)
                        break
                        
                    chunk_index, chunk_text = future.result()
                    
                    if chunk_text:
                        transcriptions[chunk_index] = chunk_text
                        words = len(chunk_text.split())
                        print(f"✅ Chunk {chunk_index} transcribed successfully - {words} words")
                    else:
                        failed_chunks.append(chunk_index)
                        print(f"Chunk {chunk_index} failed")
                    
                    # Send detailed progress info
                    if progress_callback:
                        progress_callback(
                            (i + 1) / len(chunks),
                            f"Processing chunk {i + 1}/{len(chunks)}",
                            {
                                'chunk_info': {
                                    'current': i + 1,
                                    'total': len(chunks),
                                    'progress': (i + 1) / len(chunks)
                                }
                            }
                        )
            
            # Retry failed chunks with lower concurrency
            if failed_chunks:
                print(f"Retrying {len(failed_chunks)} failed chunks sequentially...")
                # Add cooldown before retrying
                time.sleep(30)
                
                for chunk_index in failed_chunks:
                    chunk = next(c for c in chunks if c['index'] == chunk_index)
                    try:
                        chunk_text = transcribe_with_retry(
                            groq_client, 
                            chunk['path'], 
                            language,
                            max_retries=3,
                            rate_limiter=rate_limiter
                        )
                        if chunk_text:
                            transcriptions[chunk_index] = chunk_text
                            print(f"Chunk {chunk_index} transcribed on retry")
                            # Clean up successful chunk
                            try:
                                if chunk['path'] != audio_path and os.path.exists(chunk['path']):
                                    os.unlink(chunk['path'])
                                    if hasattr(st.session_state, 'temp_files_to_cleanup'):
                                        st.session_state.temp_files_to_cleanup.discard(chunk['path'])
                            except:
                                pass
                    except Exception as e:
                        print(f"Chunk {chunk_index} failed on retry: {e}")
                        # Clean up failed chunk
                        try:
                            if chunk['path'] != audio_path and os.path.exists(chunk['path']):
                                os.unlink(chunk['path'])
                                if hasattr(st.session_state, 'temp_files_to_cleanup'):
                                    st.session_state.temp_files_to_cleanup.discard(chunk['path'])
                        except:
                            pass
            
            # Combine transcriptions in order
            full_text = ' '.join(
                transcriptions.get(i, '') for i in range(len(chunks))
            ).strip()
            
        else:
            # Sequential transcription for smaller files
            print("Using sequential transcription")
            transcriptions = []
            
            for i, chunk in enumerate(chunks):
                chunk_start_time = time.time()
                # Check for shutdown
                if shutdown_requested:
                    print("\n⚠️ Shutdown requested - stopping transcription")
                    break
                    
                # Send detailed progress info
                if progress_callback:
                    progress_callback(
                        (i + 1) / len(chunks),
                        f"Processing chunk {i + 1}/{len(chunks)}",
                        {
                            'chunk_info': {
                                'current': i + 1,
                                'total': len(chunks),
                                'progress': (i + 1) / len(chunks)
                            }
                        }
                    )
                
                print(f"Transcribing chunk {i+1}/{len(chunks)}...")
                
                try:
                    chunk_text = transcribe_with_retry(groq_client, chunk['path'], language)
                    if chunk_text:
                        transcriptions.append({
                            'text': chunk_text,
                            'start_ms': chunk['start_ms'],
                            'end_ms': chunk['end_ms']
                        })
                        elapsed = time.time() - chunk_start_time
                        words = len(chunk_text.split())
                        print(f"✅ Chunk {i+1} transcribed successfully - {words} words in {elapsed:.1f}s")
                    else:
                        print(f"Chunk {i+1} returned empty transcription")
                except Exception as e:
                    print(f"Error transcribing chunk {i+1}: {e}")
                    # Continue with other chunks
                
                # Clean up chunk file
                try:
                    if chunk['path'] != audio_path:  # Don't delete the original
                        os.unlink(chunk['path'])
                except:
                    pass
            
            # Merge transcriptions
            if not transcriptions:
                return None
                
            full_text = ' '.join([t['text'] for t in transcriptions])
        
        # Save to cache
        if full_text:
            save_to_cache(cache_key, full_text)
            print("Transcription complete and cached")
        
        return full_text

def highlight_search_terms(text: str, search_terms: str) -> str:
    """Highlight search terms in text"""
    if not search_terms:
        return text
    
    # Split search terms and escape for regex
    terms = [re.escape(term.strip()) for term in search_terms.split() if term.strip()]
    if not terms:
        return text
    
    # Create regex pattern for all terms
    pattern = '|'.join(f'({term})' for term in terms)
    
    # Replace with highlighted version
    def replacer(match):
        return f"**{match.group(0)}**"
    
    return re.sub(pattern, replacer, text, flags=re.IGNORECASE)

def format_duration(seconds: int) -> str:
    """Format duration in human-readable format"""
    if seconds is None or seconds <= 0:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"

def update_batch_progress(progress_bar, status_text, detail_text, speed_text, eta_text, 
                         sub_progress_container, progress, status, details):
    """Update all progress UI elements with enhanced visual feedback"""
    progress_bar.progress(progress)
    
    # Parse status for different stages
    if "Downloading" in status:
        status_text.markdown(f'<p class="processing-status">📥 {status}</p>', unsafe_allow_html=True)
        if details.get('speed'):
            speed_mb = details['speed'] / (1024 * 1024)
            speed_text.markdown(f'<span class="metric-badge">⚡ {speed_mb:.1f} MB/s</span>', unsafe_allow_html=True)
        if details.get('eta'):
            eta_text.markdown(f'<span class="metric-badge">⏱️ {details["eta"]}s</span>', unsafe_allow_html=True)
    elif "Processing audio" in status:
        status_text.markdown(f'<p class="processing-status">🎵 {status}</p>', unsafe_allow_html=True)
        detail_text.markdown("*Extracting and converting audio track...*")
    elif "Preparing" in status and "chunks" in status:
        status_text.markdown(f'<p class="processing-status">✂️ {status}</p>', unsafe_allow_html=True)
        detail_text.markdown("*Splitting audio for optimal processing...*")
    elif "Transcribing" in status:
        status_text.markdown(f'<p class="processing-status">🎯 {status}</p>', unsafe_allow_html=True)
        if details.get('chunk_info'):
            with sub_progress_container.container():
                st.markdown('<div class="chunk-progress">', unsafe_allow_html=True)
                st.markdown(f"**📊 Processing Chunks**")
                chunk_progress = st.progress(details['chunk_info']['progress'])
                st.markdown(f"Processing chunk **{details['chunk_info']['current']}** of **{details['chunk_info']['total']}**")
                
                # Estimate remaining time based on chunk progress
                if details['chunk_info']['current'] > 0:
                    chunks_per_sec = details['chunk_info']['current'] / max(1, details.get('elapsed_time', 1))
                    remaining_chunks = details['chunk_info']['total'] - details['chunk_info']['current']
                    eta_seconds = remaining_chunks / max(0.001, chunks_per_sec)
                    if eta_seconds < 60:
                        st.markdown(f"*Estimated time remaining: {int(eta_seconds)}s*")
                    else:
                        st.markdown(f"*Estimated time remaining: {int(eta_seconds/60)}m {int(eta_seconds%60)}s*")
                
                st.markdown('</div>', unsafe_allow_html=True)
    elif "Initializing" in status:
        status_text.markdown(f'<p class="processing-status">🔄 {status}</p>', unsafe_allow_html=True)
        detail_text.markdown("*Setting up processing pipeline...*")
    elif "Completed" in status:
        status_text.markdown(f'<p class="processing-status">✅ {status}</p>', unsafe_allow_html=True)
    else:
        status_text.markdown(f'<p class="processing-status">{status}</p>', unsafe_allow_html=True)
    
    # Update detail text based on stage
    if details.get('stage'):
        stage_messages = {
            'download': 'Downloading media file',
            'audio_processing': 'Extracting audio track',
            'chunking': 'Preparing for transcription',
            'transcription': 'Transcribing with Groq AI',
            'complete': 'Processing complete'
        }
        message = stage_messages.get(details['stage'], 'Processing')
        
        # Add platform-specific messaging
        if details.get('platform'):
            platform_emojis = {
                'youtube': '🎬',
                'instagram': '📷',
                'tiktok': '🎵'
            }
            platform_emoji = platform_emojis.get(details['platform'], '📹')
            detail_text.markdown(f"{platform_emoji} **{message}**")

def process_url_batch_with_progress(urls: List[str], api_key: str, cookies_path: Optional[str] = None,
                                   language: str = 'en', progress_callback=None) -> Dict[str, Dict]:
    """Process multiple URLs with enhanced progress tracking"""
    batch_start_time = time.time()
    results = {}
    groq_client = get_groq_client(api_key)
    
    # Get current context (suppress warning for thread safety)
    ctx = get_script_run_ctx(suppress_warning=True)
    
    total_urls = len(urls)
    
    for idx, url in enumerate(urls):
        # Update overall batch progress
        batch_progress = idx / total_urls
        
        try:
            platform, video_id = detect_platform(url)
            print(f"\n{'='*60}")
            print(f"🎯 Processing URL {idx + 1}/{total_urls}")
            print(f"📍 Platform: {platform}")
            print(f"🔗 URL: {url}")
            print(f"{'='*60}")
            
            # Initial status
            if progress_callback:
                progress_callback(
                    batch_progress,
                    f"Processing URL {idx + 1}/{total_urls}",
                    {'stage': 'initializing', 'url': url, 'platform': platform}
                )
            
            # Download stage
            if progress_callback:
                progress_callback(
                    batch_progress,
                    f"Downloading from {platform}...",
                    {'stage': 'download'}
                )
            
            # Create download progress handler
            def download_progress_handler(progress):
                if progress_callback:
                    # Calculate combined progress
                    combined_progress = batch_progress + (progress * 0.5 / total_urls)
                    progress_callback(
                        combined_progress,
                        f"Downloading: {progress*100:.1f}%",
                        {'stage': 'download', 'download_progress': progress}
                    )
            
            # Download audio
            audio_path, title, info = download_audio_enhanced(
                url, 
                cookies_path=cookies_path,
                progress_callback=download_progress_handler
            )
            
            if audio_path:
                # Audio processing stage
                if progress_callback:
                    progress_callback(
                        batch_progress + 0.5 / total_urls,
                        "Processing audio file...",
                        {'stage': 'audio_processing'}
                    )
                
                # Check file size
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                
                # Transcription stage
                def transcription_progress_handler(progress, status=None, details=None):
                    if progress_callback:
                        # Calculate combined progress
                        combined_progress = batch_progress + (0.5 + progress * 0.5) / total_urls
                        
                        # Prepare details for callback
                        callback_details = {'stage': 'transcription', 'transcription_progress': progress}
                        
                        # Add chunk info if provided
                        if details and isinstance(details, dict):
                            callback_details.update(details)
                        
                        # Use status if provided, otherwise default message
                        status_msg = status or f"Transcribing with Groq ⚡: {progress*100:.1f}%"
                        
                        progress_callback(
                            combined_progress,
                            status_msg,
                            callback_details
                        )
                
                # Get audio duration for chunk estimation
                try:
                    audio = AudioSegment.from_mp3(audio_path)
                    duration_minutes = len(audio) / 1000 / 60
                    
                    # If file needs chunking, update UI
                    max_size_mb = 95 if st.session_state.get('groq_dev_tier', False) else 24
                    if file_size_mb > max_size_mb:
                        # Calculate actual chunks that will be created based on the chunk_audio logic
                        # For free tier (24MB limit): target 15MB chunks, for dev tier (95MB limit): target 20MB chunks
                        if max_size_mb > 50:  # Dev tier
                            target_chunk_size = 20.0  # MB
                        else:  # Free tier
                            target_chunk_size = 15.0  # MB
                        
                        # Calculate chunks based on actual chunking logic
                        chunks_needed = max(1, int(file_size_mb / target_chunk_size))
                        if file_size_mb % target_chunk_size > 0:
                            chunks_needed += 1
                        if progress_callback:
                            progress_callback(
                                batch_progress + 0.5 / total_urls,
                                f"Preparing {chunks_needed} chunks for transcription...",
                                {'stage': 'chunking', 'chunks': chunks_needed, 'max_chunk_size': max_size_mb}
                            )
                except:
                    pass
                
                # Transcribe with progress tracking
                transcription = transcribe_audio_with_progress(
                    audio_path, groq_client, language=language,
                    progress_callback=transcription_progress_handler
                )
                
                if transcription:
                    # Add video metadata header for YouTube videos
                    if platform == 'youtube':
                        video_header = f"""Video Title: {title}
YouTube URL: {url}
Video ID: {video_id}
{'-' * 80}

"""
                        transcription = video_header + transcription
                    
                    results[url] = {
                        'status': 'success',
                        'audio_path': audio_path,
                        'title': title,
                        'info': info,
                        'transcription': transcription
                    }
                else:
                    results[url] = {
                        'status': 'partial',
                        'audio_path': audio_path,
                        'title': title,
                        'info': info,
                        'transcription': None,
                        'error': 'Transcription failed'
                    }
            else:
                results[url] = {
                    'status': 'error',
                    'error': f"Download failed: {info.get('error', 'Unknown error')}",
                    'info': info
                }
                
        except Exception as e:
            results[url] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Update completion for this URL
        if progress_callback:
            progress_callback(
                (idx + 1) / total_urls,
                f"Completed {idx + 1}/{total_urls} URLs",
                {'stage': 'complete', 'completed': idx + 1, 'total': total_urls}
            )
    
    # Print batch summary
    print(f"\n{'='*60}")
    print(f"📊 BATCH PROCESSING SUMMARY")
    print(f"{'='*60}")
    
    success_count = sum(1 for r in results.values() if r.get('status') == 'success')
    partial_count = sum(1 for r in results.values() if r.get('status') == 'partial')
    error_count = sum(1 for r in results.values() if r.get('status') == 'error')
    
    print(f"✅ Successful: {success_count}/{total_urls}")
    print(f"⚠️  Partial (download only): {partial_count}/{total_urls}")
    print(f"❌ Failed: {error_count}/{total_urls}")
    
    # Calculate and display processing time
    batch_elapsed = time.time() - batch_start_time
    print(f"\n⏱️  Total processing time: {batch_elapsed:.1f}s")
    if success_count > 0:
        avg_time = batch_elapsed / total_urls
        print(f"📈 Average time per URL: {avg_time:.1f}s")
    
    if error_count > 0:
        print(f"\n🚨 Failed URLs:")
        for url, result in results.items():
            if result.get('status') == 'error':
                print(f"  - {url}: {result.get('error', 'Unknown error')}")
    
    print(f"{'='*60}\n")
    
    return results

def transcribe_audio_with_progress(audio_path: str, groq_client: Groq, 
                                   language: str = 'en', progress_callback=None) -> Optional[str]:
    """Wrapper for transcribe_audio that provides progress updates"""
    
    # Check cache first
    cache_key = get_cache_key(audio_path, 'transcription')
    cached_transcription = load_from_cache(cache_key)
    if cached_transcription:
        if progress_callback:
            progress_callback(1.0, "Using cached transcription", {'stage': 'transcription'})
        return cached_transcription
    
    # Get file info
    try:
        file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        audio = AudioSegment.from_mp3(audio_path)
        duration_minutes = len(audio) / 1000 / 60
    except:
        file_size_mb = 0
        duration_minutes = 0
    
    # Check if chunking is needed
    # Always use transcribe_audio for files over 25MB to ensure proper chunking
    should_use_direct = file_size_mb <= 25 and duration_minutes < 30
    
    if should_use_direct:
        # Direct transcription
        if progress_callback:
            progress_callback(0.5, "Starting transcription...", {'stage': 'transcription'})
        
        transcription = transcribe_with_retry(groq_client, audio_path, language)
        
        if progress_callback:
            progress_callback(1.0, "Transcription complete", {'stage': 'transcription'})
        
        if transcription:
            save_to_cache(cache_key, transcription)
        return transcription
    else:
        # Use existing transcribe_audio with its own progress handling
        # Don't chunk here - let transcribe_audio handle it
        # Create a wrapper for the progress callback to work with transcribe_audio
        def wrapped_progress(progress, status=None, details=None):
            if progress_callback:
                # If chunk info is provided in details, use it directly
                if details and 'chunk_info' in details:
                    progress_callback(progress, status, details)
                else:
                    # Otherwise, estimate chunks based on file size for progress display
                    # Calculate actual chunks based on chunking logic
                    max_size_mb = 95 if st.session_state.get('groq_dev_tier', False) else 24
                    if max_size_mb > 50:  # Dev tier
                        target_chunk_size = 20.0  # MB
                    else:  # Free tier
                        target_chunk_size = 15.0  # MB
                    
                    estimated_chunks = max(1, int(file_size_mb / target_chunk_size))
                    if file_size_mb % target_chunk_size > 0:
                        estimated_chunks += 1
                    
                    current_chunk = int(progress * estimated_chunks) + 1
                    
                    progress_callback(
                        progress, 
                        f"Transcribing: {progress*100:.1f}%",
                        {
                            'stage': 'transcription',
                            'transcription_progress': progress,
                            'chunk_info': {
                                'current': current_chunk,
                                'total': estimated_chunks,
                                'progress': progress
                            }
                        }
                    )
        
        return transcribe_audio(audio_path, groq_client, wrapped_progress, language)

def process_url_batch(urls: List[str], api_key: str, cookies_path: Optional[str] = None,
                     language: str = 'en') -> Dict[str, Dict]:
    """Process multiple URLs with proper context handling"""
    results = {}
    groq_client = get_groq_client(api_key)
    
    # Get current context (suppress warning for thread safety)
    ctx = get_script_run_ctx(suppress_warning=True)
    
    # Separate URLs by platform
    instagram_urls = [url for url in urls if 'instagram.com' in url]
    youtube_urls = [url for url in urls if 'youtube.com' in url or 'youtu.be' in url]
    other_urls = [url for url in urls if url not in instagram_urls and url not in youtube_urls]
    
    # Check for YouTube cookies.txt file
    youtube_cookies = None
    if os.path.exists("cookies.txt"):
        youtube_cookies = "cookies.txt"
        print("🍪 Found cookies.txt for YouTube authentication")
    
    # Process YouTube URLs with enhanced download
    for url in youtube_urls:
        try:
            print(f"🎬 Processing YouTube URL: {url}")
            
            # Use enhanced download for YouTube
            audio_path, title, info = download_audio_enhanced(
                url, 
                cookies_path=youtube_cookies or cookies_path
            )
            
            if audio_path:
                print(f"✅ YouTube download successful: {title}")
                
                # Check file size before transcription
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                
                if file_size_mb > 100:  # Warn for very large files
                    print(f"⚠️ Large audio file: {file_size_mb:.1f}MB")
                
                try:
                    transcription = transcribe_audio(audio_path, groq_client, language=language)
                    
                    results[url] = {
                        'status': 'success',
                        'audio_path': audio_path,
                        'title': title,
                        'info': info,
                        'transcription': transcription
                    }
                except Exception as transcribe_error:
                    print(f"Transcription error: {str(transcribe_error)}")
                    results[url] = {
                        'status': 'partial',
                        'audio_path': audio_path,
                        'title': title,
                        'info': info,
                        'transcription': None,
                        'error': f"Transcription failed: {str(transcribe_error)}"
                    }
            else:
                print(f"YouTube download failed: {info.get('error', 'Unknown error')}")
                results[url] = {
                    'status': 'error',
                    'error': f"Download failed: {info.get('error', 'Unknown error')}",
                    'info': info
                }
        except Exception as e:
            print(f"Error processing YouTube URL {url}: {str(e)}")
            results[url] = {
                'status': 'error',
                'error': str(e)
            }
    
    # Process Instagram URLs sequentially
    for url in instagram_urls:
        try:
            print(f"📷 Processing Instagram URL: {url}")
            audio_path, title, info = download_audio_enhanced(url, cookies_path)
            
            if audio_path:
                print(f"Download successful: {title}")
                
                try:
                    transcription = transcribe_audio(audio_path, groq_client, language=language)
                    
                    results[url] = {
                        'status': 'success',
                        'audio_path': audio_path,
                        'title': title,
                        'info': info,
                        'transcription': transcription
                    }
                except Exception as transcribe_error:
                    print(f"Transcription error: {str(transcribe_error)}")
                    results[url] = {
                        'status': 'partial',
                        'audio_path': audio_path,
                        'title': title,
                        'info': info,
                        'transcription': None,
                        'error': f"Transcription failed: {str(transcribe_error)}"
                    }
            else:
                print(f"Download failed: {info.get('error', 'Unknown error')}")
                results[url] = {
                    'status': 'error',
                    'error': f"Download failed: {info.get('error', 'Unknown error')}",
                    'info': info
                }
        except Exception as e:
            print(f"General error processing {url}: {str(e)}")
            results[url] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Brief delay between Instagram downloads
        if len(instagram_urls) > 1:
            time.sleep(2)
    
    # Process other URLs concurrently
    if other_urls:
        with ThreadPoolExecutor(max_workers=3) as executor:
            # Create wrapper function that properly handles context
            def download_with_context(url, cookies_path, ctx):
                if ctx and threading.current_thread() != threading.main_thread():
                    try:
                        add_script_run_ctx(threading.current_thread(), ctx)
                    except Exception:
                        # Silently ignore context errors - they don't affect functionality
                        pass
                
                return download_audio_enhanced(url, cookies_path)
            
            # Submit download tasks with context
            download_futures = {
                executor.submit(download_with_context, url, cookies_path, ctx): url 
                for url in other_urls
            }
            
            # Process downloads as they complete
            for future in as_completed(download_futures, timeout=900):
                url = download_futures[future]
                try:
                    audio_path, title, info = future.result()
                    
                    if audio_path:
                        try:
                            transcription = transcribe_audio(audio_path, groq_client, language=language)
                            
                            results[url] = {
                                'status': 'success',
                                'audio_path': audio_path,
                                'title': title,
                                'info': info,
                                'transcription': transcription
                            }
                        except Exception as transcribe_error:
                            results[url] = {
                                'status': 'partial',
                                'audio_path': audio_path,
                                'title': title,
                                'info': info,
                                'transcription': None,
                                'error': f"Transcription failed: {str(transcribe_error)}"
                            }
                    else:
                        results[url] = {
                            'status': 'error',
                            'error': info.get('error', 'Download failed'),
                            'info': info
                        }
                        
                except concurrent.futures.TimeoutError:
                    results[url] = {
                        'status': 'error',
                        'error': 'Download timed out after 15 minutes.'
                    }
                except Exception as e:
                    results[url] = {
                        'status': 'error',
                        'error': str(e)
                    }
    
    return results

def get_video_info_yt(url: str) -> Dict[str, Any]:
    """Get YouTube video info including live status"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'is_live': info.get('is_live', False),
                'live_status': info.get('live_status', 'none'),
                'was_live': info.get('live_status') == 'was_live',
                'description': info.get('description', ''),
                'uploader': info.get('uploader', ''),
                'view_count': info.get('view_count', 0),
                'like_count': info.get('like_count', 0),
                'upload_date': info.get('upload_date', ''),
            }
    except Exception as e:
        print(f"Error getting video info: {e}")
        return {
            'title': 'Unknown',
            'duration': 0,
            'error': str(e)
        }

def sanitize_filename(filename: str) -> str:
    """Sanitize a string to be used as a filename"""
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Replace multiple spaces with single space
    filename = re.sub(r'\s+', ' ', filename)
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    # Limit length
    if len(filename) > 200:
        filename = filename[:200]
    return filename or 'untitled'

def get_collection_hash(url: str) -> str:
    """Generate a unique hash for a collection URL."""
    return hashlib.md5(url.encode()).hexdigest()[:12]

def format_views(view_count: int) -> str:
    """Format view count with K/M suffixes."""
    if view_count is None or view_count == 0:
        return "N/A"
    if view_count >= 1_000_000:
        return f"{view_count / 1_000_000:.1f}M"
    if view_count >= 1_000:
        return f"{view_count / 1_000:.1f}K"
    return str(view_count)

def render_collection_expander(
    url: str,
    collection_type: str,
    identifier: str,
    cookies_path: Optional[str] = None
) -> List[str]:
    """
    Render the collection expander UI component for a TikTok collection.

    Args:
        url: The collection URL
        collection_type: Type of collection (user_profile, hashtag, sound, collection)
        identifier: The collection identifier (username, tag name, etc.)
        cookies_path: Path to cookies file

    Returns:
        List of selected video URLs for processing
    """
    collection_hash = get_collection_hash(url)
    collection_key = f"collection_{collection_hash}"

    # Initialize collection state if needed
    if collection_hash not in st.session_state.tiktok_collections:
        st.session_state.tiktok_collections[collection_hash] = {
            'videos': [],
            'expanded': False,
            'selected_urls': set(),
            'error': None,
            'url': url,
            'type': collection_type,
            'identifier': identifier,
        }

    collection_state = st.session_state.tiktok_collections[collection_hash]

    # Collection type display names
    type_labels = {
        'user_profile': f"@{identifier}",
        'hashtag': f"#{identifier}",
        'sound': f"Sound: {identifier}",
        'collection': f"Collection: {identifier}",
        'short_url': f"Short link: {identifier}",
    }

    type_icons = {
        'user_profile': "👤",
        'hashtag': "#️⃣",
        'sound': "🎵",
        'collection': "📁",
        'short_url': "🔗",
    }

    label = type_labels.get(collection_type, identifier)
    icon = type_icons.get(collection_type, "📂")

    with st.expander(f"{icon} TikTok Collection: {label}", expanded=True):
        st.caption(f"URL: {url}")

        # Handle short URLs - need to resolve first to check if it's a collection
        if collection_type == 'short_url' and not collection_state.get('resolved'):
            resolve_key = f"resolve_btn_{collection_hash}"
            if st.button("🔍 Check if this is a collection", key=resolve_key, type="primary"):
                with st.spinner("Resolving TikTok short URL..."):
                    is_collection, resolved_url, title = resolve_tiktok_short_url(url, cookies_path)

                    if is_collection:
                        collection_state['resolved'] = True
                        collection_state['resolved_url'] = resolved_url
                        collection_state['title'] = title or identifier
                        st.success(f"✅ This is a collection: {title or 'TikTok Collection'}")
                        st.rerun()
                    else:
                        # It's a single video, not a collection
                        collection_state['is_single_video'] = True
                        collection_state['resolved'] = True
                        st.info("ℹ️ This short URL points to a single video, not a collection. It will be processed as a regular video.")
                        return []  # Return empty - this URL should be treated as regular video

            return []  # Waiting for resolve

        # If short URL was resolved to single video, skip
        if collection_state.get('is_single_video'):
            st.info("ℹ️ This is a single video, not a collection.")
            return []

        # If not yet expanded, show expand button
        if not collection_state['expanded']:
            col1, col2 = st.columns([2, 1])
            with col1:
                max_videos = st.number_input(
                    "Maximum videos to fetch",
                    min_value=1,
                    max_value=500,
                    value=50,
                    key=f"max_videos_{collection_hash}",
                    help="Limit the number of videos to retrieve (max 500)"
                )
            with col2:
                st.write("")  # Spacer
                st.write("")  # Align with input
                expand_clicked = st.button(
                    "🔍 Expand Collection",
                    key=f"expand_btn_{collection_hash}",
                    width='stretch',
                    type="primary"
                )

            if expand_clicked:
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(progress, status):
                    progress_bar.progress(progress)
                    status_text.text(status)

                with st.spinner("Fetching videos from TikTok..."):
                    videos, error = expand_tiktok_collection(
                        url,
                        cookies_path=cookies_path,
                        max_videos=max_videos,
                        progress_callback=update_progress
                    )

                if error:
                    st.error(f"❌ {error}")
                    collection_state['error'] = error
                elif videos:
                    collection_state['videos'] = videos
                    collection_state['expanded'] = True
                    # Select all by default
                    collection_state['selected_urls'] = set(v['url'] for v in videos)
                    st.rerun()
                else:
                    st.warning("No videos found in this collection.")

        else:
            # Show video selection table
            videos = collection_state['videos']

            if not videos:
                st.info("No videos available in this collection.")
                return []

            st.write(f"**Found {len(videos)} videos**")

            # Select All / Select None buttons
            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                if st.button("✅ Select All", key=f"select_all_{collection_hash}", width='stretch'):
                    collection_state['selected_urls'] = set(v['url'] for v in videos)
                    st.rerun()
            with col2:
                if st.button("❌ Select None", key=f"select_none_{collection_hash}", width='stretch'):
                    collection_state['selected_urls'] = set()
                    st.rerun()
            with col3:
                selected_count = len(collection_state['selected_urls'])
                st.info(f"Selected: {selected_count} of {len(videos)} videos")

            # Build DataFrame for display
            df_data = []
            for i, video in enumerate(videos):
                df_data.append({
                    'Select': video['url'] in collection_state['selected_urls'],
                    'Title': video.get('title', f'Video {i + 1}')[:60],
                    'Creator': video.get('uploader', 'Unknown')[:20],
                    'Duration': format_duration(video.get('duration', 0)) if video.get('duration') else 'N/A',
                    'Views': format_views(video.get('view_count', 0)),
                    '_url': video['url'],  # Hidden column for tracking
                })

            df = pd.DataFrame(df_data)

            # Use data_editor for checkboxes
            edited_df = st.data_editor(
                df,
                column_config={
                    'Select': st.column_config.CheckboxColumn(
                        'Select',
                        help="Select videos to process",
                        default=True,
                    ),
                    'Title': st.column_config.TextColumn(
                        'Title',
                        width='large',
                    ),
                    'Creator': st.column_config.TextColumn(
                        'Creator',
                        width='small',
                    ),
                    'Duration': st.column_config.TextColumn(
                        'Duration',
                        width='small',
                    ),
                    'Views': st.column_config.TextColumn(
                        'Views',
                        width='small',
                    ),
                    '_url': None,  # Hide URL column
                },
                hide_index=True,
                width='stretch',
                key=f"video_table_{collection_hash}",
                disabled=['Title', 'Creator', 'Duration', 'Views', '_url'],
            )

            # Update selected URLs based on checkbox state
            new_selected = set()
            for i, row in edited_df.iterrows():
                if row['Select']:
                    new_selected.add(row['_url'])
            collection_state['selected_urls'] = new_selected

            # Reset button
            if st.button("🔄 Collapse & Reset", key=f"reset_{collection_hash}"):
                collection_state['expanded'] = False
                collection_state['videos'] = []
                collection_state['selected_urls'] = set()
                st.rerun()

    return list(collection_state.get('selected_urls', []))

def separate_urls_and_collections(urls: List[str]) -> Tuple[List[str], List[Dict]]:
    """
    Separate a list of URLs into regular video URLs and TikTok collections.

    Args:
        urls: List of URLs to categorize

    Returns:
        (regular_urls, collections) where collections is list of dicts with url, type, identifier
    """
    regular_urls = []
    collections = []

    for url in urls:
        collection_type, identifier = detect_tiktok_collection(url)
        if collection_type and identifier:
            collections.append({
                'url': url,
                'type': collection_type,
                'identifier': identifier,
            })
        else:
            regular_urls.append(url)

    return regular_urls, collections

# Main UI
def main():
    st.title("🎵 Universal Media Transcription Tool")
    st.markdown("Download and transcribe audio from YouTube, Instagram, and TikTok with AI-powered accuracy")
    
    # Display any Instagram-specific warnings
    if any('instagram.com' in str(v) for v in st.session_state.get('downloads', {}).keys()):
        st.info("💡 **Instagram Tip**: For best results, process Instagram URLs one at a time and ensure cookies are fresh.")
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # API Key - Check secrets first, then environment variable, then fall back to user input
        try:
            api_key = st.secrets.get("GROQ_API_KEY", "")
        except FileNotFoundError:
            api_key = ""

        if not api_key:
            api_key = os.environ.get("GROQ_API_KEY", "")

        if not api_key:
            api_key = st.text_input(
                "Groq API Key",
                type="password",
                help="Get your API key from console.groq.com, or configure it in app secrets"
            )
        
        if api_key:
            st.session_state.groq_client = get_groq_client(api_key)
            st.success("✅ API key configured")
        
            # Dev tier check
            dev_tier = st.checkbox(
                "I have Groq Dev Tier (100MB limit)",
                value=False,
                help="Check this if you've upgraded to Groq Dev Tier for larger file support"
            )
            st.session_state.groq_dev_tier = dev_tier
            
            if dev_tier:
                st.info("📈 Dev Tier: 100MB file limit")
            else:
                st.info("📊 Free Tier: 25MB file limit")

        st.divider()
        
        # Platform settings
        st.subheader("🌐 Platform Settings")
        
        with st.expander("📖 Instagram Cookie Instructions", expanded=False):
            st.markdown("""
            **How to get Instagram cookies:**
            1. Install browser extension:
               - Chrome: "Get cookies.txt LOCALLY"
               - Firefox: "cookies.txt"
            2. Log in to Instagram
            3. Visit instagram.com
            4. Click extension and export cookies
            5. Upload the file below
            """)
        
        cookies_file = st.file_uploader(
            "Cookies File (for Instagram/TikTok)",
            type=['txt'],
            help="Required for Instagram, optional for TikTok"
        )

        cookies_path = None
        if cookies_file:
            # Create a more permanent temp file that won't be deleted
            temp_cookies = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w')
            try:
                # Write and ensure it's flushed to disk
                content = cookies_file.getvalue().decode('utf-8')
                temp_cookies.write(content)
                temp_cookies.flush()
                temp_cookies.close()
                
                cookies_path = temp_cookies.name
                
                # Verify the file was written correctly
                with open(cookies_path, 'r') as f:
                    lines = f.readlines()
                    valid_cookies = sum(1 for line in lines if line.strip() and not line.startswith('#'))
                    st.success(f"✅ Cookies loaded ({valid_cookies} cookies found)")
            except Exception as e:
                st.error(f"❌ Error loading cookies: {str(e)}")
                cookies_path = None
        
        # YouTube-specific settings
        st.divider()
        st.subheader("🎬 YouTube Settings")

        # Cookie file instructions
        with st.expander("🍪 YouTube Cookie Instructions", expanded=False):
            st.markdown("""
            **For age-restricted or private videos:**
            
            1. **Install browser extension:**
            - Chrome: "Get cookies.txt LOCALLY"
            - Firefox: "cookies.txt"
            
            2. **Export YouTube cookies:**
            - Log in to YouTube
            - Visit youtube.com
            - Click the extension icon
            - Export cookies as 'cookies.txt'
            
            3. **Place in app directory:**
            - Save as 'cookies.txt' in the same folder as this app
            - Or upload using the file uploader
            
            **Note:** Cookies help bypass:
            - Age restrictions
            - Regional blocks
            - "Sign in to confirm you're not a bot" errors
            """)

        # Check for cookies.txt in app directory
        youtube_cookies_found = os.path.exists("cookies.txt")
        if youtube_cookies_found:
            st.success("✅ Found cookies.txt for YouTube")
        else:
            st.info("💡 No cookies.txt found (optional)")

        # YouTube download strategy preference
        yt_strategy = st.selectbox(
            "YouTube Download Strategy",
            options=["Auto (Try All)", "iOS Client", "Android Client", "TV Client", "Standard"],
            help="Different strategies work better for different videos"
        )

        st.divider()
        
        # Language selection
        st.subheader("🗣️ Transcription Settings")
        language = st.selectbox(
            "Language",
            options=['en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'ko', 'zh'],
            format_func=lambda x: {
                'en': 'English',
                'es': 'Spanish',
                'fr': 'French',
                'de': 'German',
                'it': 'Italian',
                'pt': 'Portuguese',
                'ru': 'Russian',
                'ja': 'Japanese',
                'ko': 'Korean',
                'zh': 'Chinese'
            }.get(x, x)
        )
        
        # Processing speed
        try:
            speed = st.segmented_control(
                "Processing Speed",
                options=['Standard', 'Fast', 'Ultra'],
                default='Standard',
                help="Trade-off between speed and accuracy"
            )
        except AttributeError:
            # Fallback for older Streamlit versions
            speed = st.radio(
                "Processing Speed",
                options=['Standard', 'Fast', 'Ultra'],
                horizontal=True,
                help="Trade-off between speed and accuracy"
            )
        
        # Store speed setting in session state
        st.session_state.processing_speed = speed
        
        st.divider()
        
        # Cache management
        st.subheader("💾 Cache Management")
        cache_files = list(CACHE_DIR.glob('*.pkl'))
        cache_size = sum(f.stat().st_size for f in cache_files) / (1024 * 1024)
        st.metric("Cache Size", f"{cache_size:.1f} MB")
        st.metric("Cached Items", len(cache_files))
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Clear Cache", type="secondary", use_container_width=True):
                for f in cache_files:
                    f.unlink()
                st.success("Cache cleared!")
                st.rerun()
        
        with col2:
            if st.button("🧹 Clean Temp Files", type="secondary", use_container_width=True):
                cleanup_temp_files()
                st.success("Temp files cleaned!")
                st.rerun()
    
    # Main content area
    col1, col2 = st.columns([3, 1])
    
    with col1:
        # URL input
        st.header("📥 Input URLs")
        
        # Input method selection
        input_method = st.radio(
            "Input Method",
            options=["Text Area", "File Upload"],
            horizontal=True
        )
        
        urls_to_process = []
        
        if input_method == "Text Area":
            urls_input = st.text_area(
                "Enter URLs (one per line)",
                height=150,
                placeholder="https://www.youtube.com/watch?v=...\nhttps://www.instagram.com/reel/...\nhttps://www.tiktok.com/@user/video/...\nhttps://www.tiktok.com/@username (profile collection)\nhttps://www.tiktok.com/tag/hashtag (hashtag collection)",
                help="Paste YouTube, Instagram, or TikTok URLs. TikTok profiles (@user) and hashtags (#tag) are expanded as collections.",
                key="urls_input"
            )
            
            if urls_input:
                urls_to_process = [url.strip() for url in urls_input.split('\n') if url.strip()]
        
        else:
            uploaded_file = st.file_uploader(
                "Upload URL list",
                type=['txt'],
                help="Upload a text file with one URL per line"
            )
            
            if uploaded_file:
                urls_to_process = uploaded_file.read().decode('utf-8').strip().split('\n')
                urls_to_process = [url.strip() for url in urls_to_process if url.strip()]
        
        # Validate URLs
        valid_urls = []  # Will hold final URLs to process (including selected from collections)

        if urls_to_process:
            validated_urls = []
            invalid_urls = []

            for url in urls_to_process:
                if validate_url(url):
                    validated_urls.append(url)
                else:
                    invalid_urls.append(url)

            if invalid_urls:
                st.warning(f"⚠️ {len(invalid_urls)} invalid URLs detected")
                with st.expander("Show invalid URLs"):
                    st.write('\n'.join(invalid_urls))

            if validated_urls:
                # Separate regular URLs from TikTok collections
                regular_urls, collections = separate_urls_and_collections(validated_urls)

                # Track URLs from collections
                collection_selected_urls = []
                # Track short URLs that resolved to single videos
                single_video_urls = []

                # Show collection expanders if any
                if collections:
                    st.divider()
                    st.subheader("📂 TikTok Collections Detected")
                    st.caption(f"Found {len(collections)} potential collection(s). Click to check/expand.")

                    for collection_info in collections:
                        # Check if this short URL was already resolved as a single video
                        collection_hash = get_collection_hash(collection_info['url'])
                        coll_state = st.session_state.tiktok_collections.get(collection_hash, {})

                        if coll_state.get('is_single_video'):
                            # This short URL is actually a single video - add to regular URLs
                            single_video_urls.append(collection_info['url'])
                            continue

                        selected_urls = render_collection_expander(
                            url=collection_info['url'],
                            collection_type=collection_info['type'],
                            identifier=collection_info['identifier'],
                            cookies_path=cookies_path
                        )
                        collection_selected_urls.extend(selected_urls)

                # Combine regular URLs with selected collection videos and resolved single videos
                valid_urls = regular_urls + collection_selected_urls + single_video_urls

                # Show summary
                st.divider()
                if valid_urls:
                    summary_parts = []
                    direct_count = len(regular_urls) + len(single_video_urls)
                    if direct_count > 0:
                        summary_parts.append(f"{direct_count} direct video URL(s)")
                    if collection_selected_urls:
                        summary_parts.append(f"{len(collection_selected_urls)} video(s) from collection(s)")

                    st.success(f"✅ {len(valid_urls)} total URLs ready to process: {', '.join(summary_parts)}")
                else:
                    # Check if there are unresolved short URLs
                    unresolved_shorts = [c for c in collections if c['type'] == 'short_url'
                                         and not st.session_state.tiktok_collections.get(
                                             get_collection_hash(c['url']), {}
                                         ).get('resolved')]
                    if unresolved_shorts:
                        st.info("ℹ️ Click 'Check if this is a collection' above to verify short URLs")
                    elif collections:
                        st.info("ℹ️ Expand collections above and select videos to process")
                    else:
                        st.warning("⚠️ No valid URLs to process")

                # Check for Instagram URLs without cookies
                instagram_urls = [url for url in valid_urls if 'instagram.com' in url]
                if instagram_urls and not cookies_path:
                    st.warning("⚠️ Instagram URLs detected but no cookies provided. Downloads may fail.")

        # Search functionality
        st.divider()
        search_terms = st.text_input(
            "🔍 Search in transcriptions",
            placeholder="Enter keywords to highlight in results...",
            help="Search terms will be highlighted in all transcriptions"
        )
        
        # Process button
        process_button = st.button(
            "🚀 Process URLs",
            type="primary",
            disabled=not api_key or not urls_to_process,
            use_container_width=True
        )
    
    with col2:
        st.header("📊 Statistics")
        
        # Display stats
        if st.session_state.downloads:
            st.metric("Downloads", len(st.session_state.downloads))
        if st.session_state.transcriptions:
            st.metric("Transcriptions", len(st.session_state.transcriptions))
            
            # In the statistics section of the main UI:

            # Calculate total duration
            total_duration = 0
            for info in st.session_state.downloads.values():
                duration = info.get('info', {}).get('duration', 0)
                if duration is not None and duration > 0:
                    total_duration += duration

            st.metric("Total Duration", format_duration(int(total_duration)))

    # Add this to your main UI for debugging:
    if st.checkbox("Enable Instagram Debug Mode"):
        if urls_to_process:
            instagram_urls = [url for url in urls_to_process if 'instagram.com' in url]
            if instagram_urls and st.button("Debug Instagram Download"):
                with st.expander("Debug Output", expanded=True):
                    for url in instagram_urls[:1]:  # Debug first URL only
                        debug_output = st.empty()
                        with st.spinner("Running debug..."):
                            # Redirect stdout to capture debug output
                            import io
                            import sys
                            old_stdout = sys.stdout
                            sys.stdout = buffer = io.StringIO()
                            
                            try:
                                debug_instagram_download(url, cookies_path)
                                debug_output.code(buffer.getvalue())
                            finally:
                                sys.stdout = old_stdout
    # Process URLs
    if process_button and valid_urls:
        st.divider()
        st.header("🔄 Processing Results")
        
        # Add custom CSS for animated progress bar
        st.markdown("""
            <style>
            /* Animated progress bar */
            .stProgress > div > div > div > div {
                background: linear-gradient(90deg, #4CAF50 0%, #8BC34A 25%, #CDDC39 50%, #8BC34A 75%, #4CAF50 100%);
                background-size: 200% 100%;
                animation: progressAnimation 3s linear infinite;
            }
            @keyframes progressAnimation {
                0% { background-position: 200% 0; }
                100% { background-position: -200% 0; }
            }
            
            /* Processing status text */
            .processing-status {
                font-weight: 600;
                color: #1976D2;
                font-size: 1.1em;
                animation: pulse 1.5s ease-in-out infinite;
                display: inline-block;
            }
            @keyframes pulse {
                0%, 100% { transform: scale(1); opacity: 0.9; }
                50% { transform: scale(1.05); opacity: 1; }
            }
            
            /* Chunk progress indicator */
            .chunk-progress {
                background: #E3F2FD;
                border-radius: 8px;
                padding: 10px;
                margin-top: 10px;
                border-left: 4px solid #2196F3;
                animation: slideIn 0.3s ease-out;
            }
            @keyframes slideIn {
                from { transform: translateX(-20px); opacity: 0; }
                to { transform: translateX(0); opacity: 1; }
            }
            
            /* Speed and ETA indicators */
            .metric-badge {
                background: #F5F5F5;
                border-radius: 16px;
                padding: 4px 12px;
                font-size: 0.9em;
                display: inline-block;
                animation: fadeIn 0.5s ease-out;
            }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            /* Green buttons - ZIP export */
            .st-key-quick_export_zip .stButton button,
            .st-key-batch_export_zip .stButton button {
                background-color: #28a745 !important;
                color: white !important;
                border-color: #28a745 !important;
            }
            .st-key-quick_export_zip .stButton button:hover,
            .st-key-batch_export_zip .stButton button:hover {
                background-color: #218838 !important;
            }

            /* Blue buttons - JSON export */
            .st-key-quick_export_json .stButton button,
            .st-key-batch_export_json .stButton button {
                background-color: #007bff !important;
                color: white !important;
                border-color: #007bff !important;
            }
            .st-key-quick_export_json .stButton button:hover,
            .st-key-batch_export_json .stButton button:hover {
                background-color: #0056b3 !important;
            }

            /* Red button - Clear All Data */
            .st-key-batch_clear_data .stButton button {
                background-color: #dc3545 !important;
                color: white !important;
                border-color: #dc3545 !important;
            }
            .st-key-batch_clear_data .stButton button:hover {
                background-color: #c82333 !important;
            }

            /* Gunmetal expander - Troubleshooting */
            .st-key-troubleshoot_expander summary,
            .st-key-quick_troubleshoot summary {
                background-color: #2a3439 !important;
                color: white !important;
                border-radius: 4px;
            }
            .st-key-troubleshoot_expander summary span,
            .st-key-quick_troubleshoot summary span {
                color: white !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # Process in batches
        batch_size = 5
        for i in range(0, len(valid_urls), batch_size):
            batch = valid_urls[i:i+batch_size]
            
            with st.container():
                st.subheader(f"Batch {i//batch_size + 1}")
                
                # Create comprehensive progress tracking UI
                progress_container = st.container()
                with progress_container:
                    # Main progress bar
                    progress_bar = st.progress(0)
                    
                    # Status columns
                    col1, col2, col3 = st.columns([2, 1, 1])
                    
                    with col1:
                        status_text = st.empty()
                        detail_text = st.empty()
                    
                    with col2:
                        speed_text = st.empty()
                    
                    with col3:
                        eta_text = st.empty()
                    
                    # Sub-progress for individual operations
                    sub_progress_container = st.empty()
                
                # Initialize status
                status_text.markdown('<p class="processing-status">🔄 Initializing batch processing...</p>', unsafe_allow_html=True)
                
                # Process batch with enhanced progress tracking
                results = process_url_batch_with_progress(
                    batch, api_key, cookies_path, language,
                    progress_callback=lambda p, s, d: update_batch_progress(
                        progress_bar, status_text, detail_text, speed_text, eta_text, 
                        sub_progress_container, p, s, d
                    )
                )
                
                # Store results in session state immediately
                for url, result in results.items():
                    if result['status'] in ['success', 'partial']:
                        st.session_state.downloads[url] = result
                        if result.get('transcription'):
                            st.session_state.transcriptions[url] = result['transcription']
                    # Store all results for display persistence
                    st.session_state.displayed_results[url] = result
                
                # After processing, display ALL results from session state
                # This ensures results persist across reruns

        # Quick-access export section (shown after processing completes)
        if st.session_state.transcriptions:
            st.divider()

            # Anchor for auto-scroll
            st.markdown('<div id="quick-export"></div>', unsafe_allow_html=True)

            st.subheader("⚡ Quick Export")
            st.caption(f"{len(st.session_state.transcriptions)} transcription(s) ready for export")

            qe_col1, qe_col2, qe_col3 = st.columns(3)

            with qe_col1:
                # ZIP export (GREEN)
                if st.button("📦 Export All as ZIP", key="quick_export_zip", width='stretch'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
                        with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                            for url, transcription in st.session_state.transcriptions.items():
                                if transcription and url in st.session_state.downloads:
                                    title = st.session_state.downloads[url].get('title', 'unknown')
                                    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
                                    zf.writestr(f"{safe_title}.txt", transcription)
                                    audio_path = st.session_state.downloads[url].get('audio_path')
                                    if audio_path and os.path.exists(audio_path):
                                        zf.write(audio_path, f"{safe_title}.mp3")
                        with open(tmp_zip.name, 'rb') as f:
                            st.download_button(
                                "⬇️ Download ZIP",
                                data=f,
                                file_name=f"transcriptions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                                mime="application/zip",
                                key="quick_zip_download",
                                width='stretch'
                            )

            with qe_col2:
                # JSON export (BLUE)
                if st.button("📊 Export as JSON", key="quick_export_json", width='stretch'):
                    export_data = {
                        'metadata': {
                            'export_date': datetime.now().isoformat(),
                            'total_items': len(st.session_state.transcriptions),
                        },
                        'transcriptions': []
                    }
                    for url, transcription in st.session_state.transcriptions.items():
                        if url in st.session_state.downloads:
                            item_data = {
                                'url': url,
                                'title': st.session_state.downloads[url].get('title', 'Unknown'),
                                'transcription': transcription,
                                'duration': st.session_state.downloads[url].get('info', {}).get('duration', 0),
                                'platform': detect_platform(url)[0]
                            }
                            export_data['transcriptions'].append(item_data)
                    json_str = json.dumps(export_data, indent=2, ensure_ascii=False)
                    st.download_button(
                        "⬇️ Download JSON",
                        data=json_str,
                        file_name=f"transcriptions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                        mime="application/json",
                        key="quick_json_download",
                        width='stretch'
                    )

            with qe_col3:
                # Save all text files
                if st.button("💾 Save All Text Files", key="quick_save_txt", width='stretch'):
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
                        with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                            for url, transcription in st.session_state.transcriptions.items():
                                if transcription and url in st.session_state.downloads:
                                    title = st.session_state.downloads[url].get('title', 'unknown')
                                    safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
                                    zf.writestr(f"{safe_title}.txt", transcription)
                        with open(tmp_zip.name, 'rb') as f:
                            st.download_button(
                                "⬇️ Download Text Files",
                                data=f,
                                file_name=f"transcripts_txt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                                mime="application/zip",
                                key="quick_txt_download",
                                width='stretch'
                            )

            # Troubleshooting in quick section
            with st.expander("🔧 Troubleshooting Guide", expanded=False):
                st.markdown("""
                **Quick Tips:**
                - **TikTok rate limiting**: Wait a few minutes and try again
                - **Instagram login required**: Upload fresh cookies
                - **Transcription failed**: Check Groq API key and credits
                - **Keep yt-dlp updated**: `pip install -U yt-dlp`
                """)

            # Auto-scroll to quick export section
            st.markdown("""
                <script>
                    document.getElementById('quick-export').scrollIntoView({behavior: 'smooth'});
                </script>
            """, unsafe_allow_html=True)

    # Always display results section if we have any downloads
    if st.session_state.downloads:
        st.divider()
        st.header("📊 Transcription Results")
        
        # Display each result from session state
        for url, result in st.session_state.downloads.items():
            with st.expander(f"📹 {url[:80]}...", expanded=True):
                if result['status'] in ['success', 'partial']:
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        if result['status'] == 'partial':
                            st.warning(f"⚠️ {result['title']} - Audio downloaded but transcription failed")
                            st.error(result.get('error', 'Transcription error'))
                        else:
                            st.success(f"✅ {result['title']}")
                                
                        # Video info
                        if 'info' in result and result['info']:
                            info = result['info']
                            info_cols = st.columns(4)
                            
                            with info_cols[0]:
                                duration = info.get('duration', 0)
                                if duration is not None and duration > 0:
                                    st.metric("Duration", format_duration(int(duration)))
                                else:
                                    st.metric("Duration", "Unknown")
                                    
                            with info_cols[1]:
                                views = info.get('view_count', 0)
                                if views is not None and views > 0:
                                    st.metric("Views", f"{views:,}")
                                else:
                                    st.metric("Views", "N/A")
                                    
                            with info_cols[2]:
                                likes = info.get('like_count', 0)
                                if likes is not None and likes > 0:
                                    st.metric("Likes", f"{likes:,}")
                                else:
                                    st.metric("Likes", "N/A")
                                    
                            with info_cols[3]:
                                upload_date = info.get('upload_date', '')
                                if upload_date:
                                    try:
                                        date = datetime.strptime(upload_date, '%Y%m%d')
                                        st.metric("Uploaded", date.strftime('%Y-%m-%d'))
                                    except:
                                        st.metric("Uploaded", "N/A")
                                
                        # Audio player
                        if result.get('audio_path') and os.path.exists(result['audio_path']):
                            with open(result['audio_path'], 'rb') as f:
                                audio_bytes = f.read()
                            st.audio(audio_bytes, format='audio/mp3')
                                
                        # Transcription
                        if result.get('transcription'):
                            st.divider()
                            
                            # Apply search highlighting - use session state
                            transcription_text = st.session_state.transcriptions.get(url, result.get('transcription', ''))
                            display_text = transcription_text
                            # Note: search_terms not available in this context, skip highlighting
                                    
                            # Show transcription with character count
                            char_count = len(transcription_text)
                            word_count = len(transcription_text.split())
                            
                            st.markdown(f"**Transcription** ({word_count:,} words, {char_count:,} characters)")
                                    
                            # Display in scrollable text area
                            # Use a unique key based on URL hash to ensure persistence
                            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                            transcript_key = f"transcript_{url_hash}"
                            
                            # CRITICAL: Store the transcription text in a separate key that won't be affected by widget state
                            transcript_content_key = f"transcript_content_{url_hash}"
                            if transcript_content_key not in st.session_state:
                                st.session_state[transcript_content_key] = display_text
                            
                            # Create text area that uses the stored content
                            st.text_area(
                                "Transcription text",
                                value=st.session_state[transcript_content_key],
                                height=300,
                                key=transcript_key,
                                label_visibility="collapsed",
                                disabled=True  # Make read-only to prevent accidental edits
                            )
                                
                    
                    with col2:
                        st.markdown("### 💾 Downloads")
                        
                        # Calculate URL hash for unique keys
                        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                        
                        # Use containers to isolate download buttons
                        download_container = st.container()
                        with download_container:
                            # Download MP3
                            if result.get('audio_path') and os.path.exists(result['audio_path']):
                                with open(result['audio_path'], 'rb') as f:
                                    st.download_button(
                                        "📥 Download MP3",
                                        data=f,
                                        file_name=f"{result['title'][:50]}.mp3",
                                        mime="audio/mpeg",
                                        key=f"mp3_{url_hash}",
                                        use_container_width=True
                                    )
                                    
                            # Download transcription
                            if result.get('transcription'):
                                # Text format
                                st.download_button(
                                    "📄 Download TXT",
                                    data=result['transcription'],
                                    file_name=f"{result['title'][:50]}.txt",
                                    mime="text/plain",
                                    key=f"txt_{url_hash}",
                                    use_container_width=True
                                )
                                        
                                # SRT format (basic)
                                srt_content = f"1\n00:00:00,000 --> 00:00:10,000\n{result['transcription']}\n"
                                st.download_button(
                                    "📄 Download SRT",
                                    data=srt_content,
                                    file_name=f"{result['title'][:50]}.srt",
                                    mime="text/plain",
                                    key=f"srt_{url_hash}",
                                    use_container_width=True
                                )
                        
                else:
                    st.error(f"❌ Error: {result.get('error', 'Unknown error')}")
                    
                    # Show troubleshooting tips for specific errors
                    if 'instagram' in url.lower() and 'login' in str(result.get('error', '')).lower():
                        st.info("💡 Tip: Make sure your cookies are fresh and from a logged-in session.")
                    elif '403' in str(result.get('error', '')):
                        st.info("💡 Tip: Check your Groq API key and ensure you have sufficient credits.")
    
    # Batch export
    if st.session_state.transcriptions:
        st.divider()
        st.header("📦 Batch Export")

        col1, col2, col3 = st.columns(3)

        with col1:
            # Export all transcriptions as ZIP (GREEN)
            if st.button("📦 Export All as ZIP", key="batch_export_zip", width='stretch'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
                    with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                        for url, transcription in st.session_state.transcriptions.items():
                            if transcription and url in st.session_state.downloads:
                                title = st.session_state.downloads[url].get('title', 'unknown')
                                safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
                                zf.writestr(f"{safe_title}.txt", transcription)
                                audio_path = st.session_state.downloads[url].get('audio_path')
                                if audio_path and os.path.exists(audio_path):
                                    zf.write(audio_path, f"{safe_title}.mp3")
                    with open(tmp_zip.name, 'rb') as f:
                        st.download_button(
                            "⬇️ Download ZIP",
                            data=f,
                            file_name=f"transcriptions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            key="batch_zip_download",
                            width='stretch'
                        )

        with col2:
            # Export as JSON (BLUE)
            if st.button("📊 Export as JSON", key="batch_export_json", width='stretch'):
                export_data = {
                    'metadata': {
                        'export_date': datetime.now().isoformat(),
                        'total_items': len(st.session_state.transcriptions),
                        'language': language
                    },
                    'transcriptions': []
                }
                for url, transcription in st.session_state.transcriptions.items():
                    if url in st.session_state.downloads:
                        item_data = {
                            'url': url,
                            'title': st.session_state.downloads[url].get('title', 'Unknown'),
                            'transcription': transcription,
                            'duration': st.session_state.downloads[url].get('info', {}).get('duration', 0),
                            'platform': detect_platform(url)[0]
                        }
                        export_data['transcriptions'].append(item_data)
                json_str = json.dumps(export_data, indent=2, ensure_ascii=False)
                st.download_button(
                    "⬇️ Download JSON",
                    data=json_str,
                    file_name=f"transcriptions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                    key="batch_json_download",
                    width='stretch'
                )

        with col3:
            # Save all text files
            if st.button("💾 Save All Text Files", key="batch_save_txt", width='stretch'):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_zip:
                    with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                        for url, transcription in st.session_state.transcriptions.items():
                            if transcription and url in st.session_state.downloads:
                                title = st.session_state.downloads[url].get('title', 'unknown')
                                safe_title = re.sub(r'[<>:"/\\|?*]', '', title)[:50]
                                zf.writestr(f"{safe_title}.txt", transcription)
                    with open(tmp_zip.name, 'rb') as f:
                        st.download_button(
                            "⬇️ Download Text Files",
                            data=f,
                            file_name=f"transcripts_txt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                            mime="application/zip",
                            key="batch_txt_download",
                            width='stretch'
                        )

        # Troubleshooting guide
        with st.expander("🔧 Troubleshooting Guide"):
            st.markdown("""
            ### Common Issues and Solutions

            **TikTok Collection Issues:**
            - **"Requires authentication"**: Private profiles/collections need cookies from a logged-in TikTok account
            - **"Collection not found"**: The profile/hashtag may have been removed or is unavailable in your region
            - **"Rate limiting"**: TikTok may block rapid requests. Wait a few minutes and try again
            - **Empty collection**: The profile may have no public videos, or videos may be restricted
            - **Tip**: Start with fewer videos (20-50) to test, then increase if needed

            **Instagram Issues:**
            - **"Login required"**: Upload fresh cookies from a logged-in session
            - **Downloads fail**: Instagram may be rate-limiting. Try:
              - Processing one URL at a time
              - Waiting 30-60 seconds between downloads
              - Re-exporting cookies if they're older than a few hours

            **ThreadPoolExecutor Warnings:**
            - These are now handled internally and won't affect functionality

            **General Tips:**
            - Keep yt-dlp updated: `pip install -U yt-dlp`
            - Ensure FFmpeg is installed correctly
            - Clear cache if experiencing persistent issues
            """)

        # Clear all data button (RED)
        if st.button("🗑️ Clear All Data", key="batch_clear_data", width='stretch'):
            # Clean up files
            for url, data in st.session_state.downloads.items():
                audio_path = data.get('audio_path')
                if audio_path and os.path.exists(audio_path):
                    try:
                        os.unlink(audio_path)
                    except:
                        pass

            # Clear session state
            st.session_state.downloads = {}
            st.session_state.transcriptions = {}
            st.session_state.progress = {}
            st.session_state.urls_input = ""
            st.session_state.displayed_results = {}
            st.session_state.tiktok_collections = {}

            # Clear all transcript text area states and other dynamic keys
            keys_to_remove = []
            for key in st.session_state:
                if key.startswith((
                    'transcript_', 'transcript_content_', 'mp3_', 'txt_', 'srt_',
                    'collection_', 'max_videos_', 'expand_btn_', 'video_table_',
                    'select_all_', 'select_none_', 'reset_', 'quick_', 'batch_'
                )):
                    keys_to_remove.append(key)
            for key in keys_to_remove:
                del st.session_state[key]

            st.success("✅ All data cleared!")
            st.rerun()

    # Footer
    st.divider()
    st.markdown(
        """
        <div style='text-align: center; color: #666;'>
        <p>Built with Streamlit, yt-dlp, and Groq Whisper</p>
        <p>Supports YouTube, Instagram Reels, TikTok videos, and TikTok collections (profiles, hashtags, sounds)</p>
        </div>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user - cleaning up...")
        cleanup_temp_files()
        print("👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        cleanup_temp_files()
        sys.exit(1)
