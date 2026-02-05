# Phase 4: Download & Transcribe - Sprint Breakdown

**Generated**: 2026-02-04
**Source Analysis**: Streamlit app.py lines 459-1573
**Target**: Flask 3.1 backend + Next.js 16 frontend

---

## Executive Summary

Phase 4 ports the core processing pipeline from Streamlit to Flask. The existing backend already has:
- Thread-safe `JobManager` with in-memory job store
- SSE pub/sub system with `notify_*` helpers
- Platform detection and URL validation

**Missing components to build**:
1. `services/downloader.py` - Audio download with fallback strategies
2. `services/audio.py` - Chunk audio for API limits
3. `services/transcriber.py` - Groq transcription with rate limiting
4. `services/cache.py` - Disk caching layer
5. `api/jobs.py` - Job execution endpoints (create/start/cancel)

---

## Critical Gotchas

### 1. Streamlit Session State Removal

| Streamlit Pattern | Flask Replacement |
|-------------------|-------------------|
| `st.session_state.cleanup_handlers` | Job-scoped cleanup list in `JobItem` |
| `st.session_state.groq_dev_tier` | Pass as param in job creation |
| `st.session_state.temp_files_to_cleanup` | `atexit` + job cleanup handler |
| `get_script_run_ctx()` / `add_script_run_ctx()` | **Remove entirely** - not needed |
| `shutdown_requested` global | Check `job.status == CANCELLED` in loop |

### 2. Rate Limiter Architecture

**Problem**: Original uses global `RateLimiter` for single user. Flask serves multiple users with different Groq API keys.

**Solution Options**:

| Option | Complexity | Best For |
|--------|------------|----------|
| Per-request limiter (pass API key) | Low | MVP |
| Per-API-key limiter dict | Medium | Multi-user |
| Redis-based distributed limiter | High | Production scale |

**MVP Approach** (recommended for Phase 4):
```python
# services/transcriber.py
class RateLimiter:
    _instances: dict[str, 'RateLimiter'] = {}
    _lock = threading.Lock()

    @classmethod
    def for_api_key(cls, api_key: str, rpm: int = 400) -> 'RateLimiter':
        key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
        with cls._lock:
            if key_hash not in cls._instances:
                cls._instances[key_hash] = cls(rpm)
            return cls._instances[key_hash]
```

### 3. ThreadPoolExecutor + SSE Integration

**Problem**: Workers in ThreadPoolExecutor need to send progress to SSE subscribers.

**Solution**: Pass job_id and url to worker, call notify helpers:

```python
def transcribe_chunk(chunk_info, job_id: str, url: str):
    # ... transcription logic ...

    # Progress update from worker thread
    notify_item_progress(job_id, url, progress, "transcribing")

    return chunk_index, chunk_text
```

### 4. Temp File Cleanup Strategy

**Problem**: `chunk_audio()` creates temp files that must be cleaned up even on error.

**Solution**: Context manager pattern + job cleanup hook:

```python
# services/audio.py
@contextlib.contextmanager
def chunk_audio_context(audio_path: str, max_chunk_size_mb: int = 24):
    chunks = []
    try:
        chunks = chunk_audio(audio_path, max_chunk_size_mb)
        yield chunks
    finally:
        # Cleanup all chunk files
        for chunk in chunks:
            if chunk['path'] != audio_path:
                try:
                    os.unlink(chunk['path'])
                except:
                    pass
```

### 5. Cache Security

**Problem**: The original code uses unsafe serialization for caching.

**Solution**: Use JSON for simple data with validation:

```python
# services/cache.py
import json
import hashlib

def save_to_cache(cache_key: str, data: dict):
    """Save JSON-serializable data to cache."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    with open(cache_file, 'w') as f:
        json.dump(data, f)

def load_from_cache(cache_key: str) -> Optional[dict]:
    """Load data from cache with TTL check."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if not cache_file.exists():
        return None

    # Check TTL (24 hours default)
    if time.time() - cache_file.stat().st_mtime > 86400:
        cache_file.unlink()
        return None

    try:
        with open(cache_file, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        cache_file.unlink()
        return None
```

---

## Moderate Gotchas

### 1. YouTube Download Strategies Test Matrix

6 strategies need testing against:
- Age-restricted videos
- Live streams (is_live=True)
- Recorded live streams (live_status='was_live')
- Private videos (with cookies)
- Region-locked videos
- Very long videos (4+ hours)

**Test URLs to collect**:
```python
TEST_URLS = {
    'standard': 'https://youtube.com/watch?v=dQw4w9WgXcQ',
    'age_restricted': '',  # Find example
    'live': '',  # Find example
    'long_form': '',  # 4+ hour video
}
```

### 2. Instagram Headers May Be Outdated

The hardcoded Instagram headers in the source (`X-Ig-App-Id: 936619743392459`) may become stale. Consider:
- Making headers configurable
- Adding header rotation
- Monitoring for 403/429 responses

### 3. FFmpeg Dependency

`yt-dlp` postprocessors require FFmpeg. Ensure:
```dockerfile
# Dockerfile
RUN apt-get update && apt-get install -y ffmpeg
```

### 4. Groq Client Thread Safety

**Question**: Is `groq.Groq()` client thread-safe for parallel transcription?

**Answer**: Yes, the Groq Python client uses requests sessions which are thread-safe. However, create one client per job to avoid API key conflicts:

```python
def process_job(job: Job, api_key: str):
    client = Groq(api_key=api_key)
    # Use client for all chunks in this job
```

---

## Sprint Tasks

### Task 1: Create services/downloader.py
**Complexity**: 4/5
**Dependencies**: None
**Files**:
- Create `backend/services/downloader.py`

**Subtasks**:
1. Port `download_audio_enhanced()` without Streamlit refs
2. Replace progress_callback with `notify_item_progress()`
3. Remove `get_script_run_ctx()` calls
4. Use job-scoped temp dir cleanup
5. Add logging instead of print statements

**Test Scenarios**:
- [ ] Download YouTube video (standard)
- [ ] Download with cookie authentication
- [ ] Download Instagram reel
- [ ] Download TikTok video
- [ ] Handle download failure gracefully
- [ ] Verify cache hit/miss behavior

---

### Task 2: Create services/audio.py
**Complexity**: 3/5
**Dependencies**: Task 1
**Files**:
- Create `backend/services/audio.py`

**Subtasks**:
1. Port `chunk_audio()` function
2. Implement context manager for cleanup
3. Accept tier as parameter (not session state)
4. Add proper logging

**Test Scenarios**:
- [ ] Chunk small file (<25MB) - should return single chunk
- [ ] Chunk large file (>100MB) - verify chunk sizes
- [ ] Verify overlap between chunks
- [ ] Test error fallback (return original as single chunk)
- [ ] Verify temp file cleanup on success
- [ ] Verify temp file cleanup on error

---

### Task 3: Create services/transcriber.py
**Complexity**: 4/5
**Dependencies**: Task 2
**Files**:
- Create `backend/services/transcriber.py`

**Subtasks**:
1. Port `RateLimiter` class with per-API-key instances
2. Port `transcribe_with_retry()` with proper error handling
3. Port `transcribe_audio()` with parallel/sequential modes
4. Replace `shutdown_requested` with job status check
5. Integrate with SSE notifications

**Test Scenarios**:
- [ ] Transcribe small file directly (no chunking)
- [ ] Transcribe large file with chunking
- [ ] Test parallel transcription (30+ min video)
- [ ] Test rate limiter behavior
- [ ] Test 503 retry with backoff
- [ ] Test 429 rate limit handling
- [ ] Test 413 file too large handling
- [ ] Test job cancellation mid-transcription

---

### Task 4: Create services/cache.py
**Complexity**: 2/5
**Dependencies**: None
**Files**:
- Create `backend/services/cache.py`

**Subtasks**:
1. Implement `get_cache_key()` with MD5
2. Implement `load_from_cache()` with JSON (safe serialization)
3. Implement `save_to_cache()` with JSON
4. Add TTL-based invalidation
5. Add cache directory config from environment

**Test Scenarios**:
- [ ] Cache hit returns correct data
- [ ] Cache miss returns None
- [ ] Expired cache is invalidated
- [ ] Corrupted cache file is handled gracefully
- [ ] Cache key uniqueness for different operations

---

### Task 5: Create api/process.py (Job Execution)
**Complexity**: 4/5
**Dependencies**: Tasks 1-4
**Files**:
- Create `backend/api/process.py`

**Subtasks**:
1. Create `/api/jobs/{id}/start` endpoint
2. Implement background job execution with threading
3. Wire up all services (download -> chunk -> transcribe)
4. Integrate with JobManager status updates
5. Integrate with SSE notifications
6. Handle job cancellation

**Test Scenarios**:
- [ ] Start job and receive SSE updates
- [ ] Process multiple URLs in one job
- [ ] Cancel job mid-processing
- [ ] Handle partial failure (some URLs succeed, some fail)
- [ ] Verify job completion notification

---

### Task 6: Frontend Job Processing UI
**Complexity**: 3/5
**Dependencies**: Task 5
**Files**:
- Update `frontend/src/app/page.tsx`
- Update `frontend/src/hooks/useSSE.ts`
- Update `frontend/src/stores/jobStore.ts`

**Subtasks**:
1. Add "Start Processing" button
2. Display real-time progress per URL
3. Display transcription results as they complete
4. Handle job cancellation UI
5. Handle errors gracefully

**Test Scenarios**:
- [ ] Progress bar updates in real-time
- [ ] Completed items show transcription
- [ ] Failed items show error message
- [ ] Cancel button stops processing
- [ ] Multiple jobs can run sequentially

---

## Task Dependencies Graph

```
Task 1 (downloader) ──┬──> Task 5 (api/process)
                      │
Task 2 (audio) ───────┤
                      │
Task 3 (transcriber) ─┤
                      │
Task 4 (cache) ───────┘
                              │
                              v
                      Task 6 (frontend)
```

---

## Environment Variables to Add

```env
# .env.example additions
CACHE_DIR=/tmp/multifetch-cache
CACHE_TTL_SECONDS=86400
MAX_PARALLEL_TRANSCRIPTIONS=5
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| YouTube strategy failures | Medium | High | Log which strategy succeeds, A/B test |
| Groq API rate limits | Medium | Medium | Per-key rate limiter, queue system |
| Memory exhaustion on large files | Low | High | Stream processing, temp file cleanup |
| Instagram header staleness | Medium | Low | Make headers configurable |
| Cache corruption | Low | Low | JSON format, graceful fallback |

---

## Estimated Effort

| Task | Story Points | Notes |
|------|--------------|-------|
| Task 1: downloader.py | 5 | Complex with 6 strategies |
| Task 2: audio.py | 3 | Straightforward port |
| Task 3: transcriber.py | 5 | Parallel processing complexity |
| Task 4: cache.py | 2 | Simple utility |
| Task 5: api/process.py | 5 | Integration work |
| Task 6: Frontend UI | 3 | SSE already set up |
| **Total** | **23** | ~1-2 sprints |
