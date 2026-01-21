# Modularization Map

Source: `/home/player3/Projects/multiFetch/app.py` (~3400 lines)

---

## Module Breakdown

### 1. Download Engine → `backend/services/downloader.py`

| Function | Line | Description |
|----------|------|-------------|
| `detect_platform()` | 323 | URL platform detection |
| `validate_url()` | 387 | URL validation |
| `download_audio_enhanced()` | 459-791 | Main download with fallbacks |
| `DownloadProgressHook` | 425 | Progress hook for yt-dlp |

**Constants:**
- `SUPPORTED_PLATFORMS` (lines 83-97)
- YouTube strategies (lines 567-700)

---

### 2. Audio Processing → `backend/services/audio.py`

| Function | Line | Description |
|----------|------|-------------|
| `chunk_audio()` | 1054-1185 | Split audio for API limits |
| `sanitize_filename()` | 957 | Clean filename |

---

### 3. Transcription → `backend/services/transcriber.py`

| Function | Line | Description |
|----------|------|-------------|
| `RateLimiter` | 1187 | Rate limiting class |
| `transcribe_with_retry()` | 1220 | Single file transcription |
| `transcribe_audio()` | 1300 | Main transcription |
| `get_groq_client()` | 265 | Groq client factory |

---

### 4. TikTok Collections → `backend/services/tiktok.py`

| Function | Line | Description |
|----------|------|-------------|
| `detect_tiktok_collection()` | 332 | Detect collection URL |
| `resolve_tiktok_short_url()` | 347-385 | Resolve /t/ URLs |
| `expand_tiktok_collection()` | 793-923 | Get video list |
| `get_collection_hash()` | 2192 | Generate collection ID |

**Constants:**
- `TIKTOK_COLLECTION_PATTERNS` (lines 100-122)

---

### 5. Caching → `backend/services/cache.py`

| Function | Line | Description |
|----------|------|-------------|
| `get_cache_key()` | 401 | Generate cache key |
| `load_from_cache()` | 405 | Load from disk |
| `save_to_cache()` | 416 | Save to disk |

---

### 6. Batch Processing → `backend/services/batch.py`

| Function | Line | Description |
|----------|------|-------------|
| `process_url_batch()` | 1960 | Core batch processing |
| `process_url_batch_with_progress()` | 1678 | With progress callbacks |

---

### 7. Utilities → `backend/utils/helpers.py`

| Function | Line | Description |
|----------|------|-------------|
| `format_duration()` | 1594 | Format seconds |
| `highlight_search_terms()` | 1575 | Highlight in text |
| `cleanup_temp_files()` | 168 | Clean temp files |

---

### 8. Constants → `backend/utils/constants.py`

| Constant | Line | Description |
|----------|------|-------------|
| `SUPPORTED_PLATFORMS` | 83-97 | Platform regex patterns |
| `TIKTOK_COLLECTION_PATTERNS` | 100-122 | Collection patterns |
| `CACHE_DIR` | 127 | Cache directory |

---

## Session State → API State Mapping

| Streamlit State | Flask Equivalent |
|-----------------|------------------|
| `st.session_state.downloads` | In-memory dict / Redis |
| `st.session_state.transcriptions` | In-memory dict / Redis |
| `st.session_state.progress` | SSE stream |
| `st.session_state.groq_client` | Request-scoped |
| `st.session_state.tiktok_collections` | In-memory dict |

---

## UI-Only Code (→ Next.js)

| Function | Line | Destination |
|----------|------|-------------|
| `create_progress_container()` | 970 | React component |
| `update_batch_progress()` | 1610 | React component |
| `render_collection_expander()` | 2206 | React component |
| `main()` | 2455 | Next.js pages |
| CSS styles | 2836-2935 | Tailwind |
