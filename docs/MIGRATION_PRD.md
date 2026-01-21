# MultiFetch v2 - Migration PRD

## Overview

Migration from Streamlit monolith to Next.js + Flask architecture.

**Source**: `/home/player3/Projects/multiFetch/app.py` (~3400 lines)

---

## Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Frontend | Next.js (App Router) | 16.1.x |
| Frontend | React | 19.2.x |
| Frontend | TypeScript | 5.9.x |
| Frontend | Tailwind CSS | 4.1.x |
| Backend | Python | 3.11+ |
| Backend | Flask | 3.1.x |
| Real-time | Server-Sent Events (SSE) | Native |
| Deployment (FE) | Vercel | - |
| Deployment (BE) | Railway / Fly.io | - |

---

## User Stories

### US-1: Single Video Processing
```
As a user, I want to paste a YouTube/Instagram/TikTok URL and receive
the audio file and transcription.

Acceptance Criteria:
- Validate URL and detect platform
- Real-time progress (download + transcription)
- Play audio and view transcription
- Download MP3 and TXT files
```

### US-2: Batch Processing
```
As a user, I want to process multiple URLs at once.

Acceptance Criteria:
- Input multiple URLs (newline-separated or file upload)
- Validate all URLs before processing
- Progress tracking (overall + per-URL)
- Results persist in session
```

### US-3: TikTok Collection Expansion
```
As a user, I want to paste a TikTok profile/hashtag URL and select
which videos to transcribe.

Acceptance Criteria:
- Detect collection vs single video URLs
- Expand collection to view videos
- Select/deselect with Select All/None
- Add selected to processing queue
```

### US-4: Export Results
```
As a user, I want to export transcriptions in various formats.

Acceptance Criteria:
- Export all as ZIP (MP3 + TXT)
- Export as JSON with metadata
- Individual file downloads
```

### US-5: Configuration
```
As a user, I want to configure API keys and preferences.

Acceptance Criteria:
- Groq API key input with validation
- Cookie file upload for Instagram/TikTok
- Language selection
- Dev tier toggle for larger file limits
```

---

## API Contracts

### Configuration

```yaml
POST /api/config/validate
Request:
  { "groq_api_key": "string", "is_dev_tier": boolean }
Response:
  { "valid": boolean, "tier": "free"|"dev", "max_file_size_mb": number }

POST /api/config/cookies
Request: multipart/form-data (file: cookies.txt)
Response:
  { "valid": boolean, "cookie_count": number, "platforms": ["instagram"] }
```

### URL Validation

```yaml
POST /api/urls/validate
Request:
  { "urls": ["string"] }
Response:
  {
    "valid_urls": [{
      "url": "string",
      "platform": "youtube"|"instagram"|"tiktok",
      "type": "video"|"collection"
    }],
    "invalid_urls": ["string"]
  }
```

### TikTok Collections

```yaml
POST /api/tiktok/expand
Request:
  { "url": "string", "max_videos": 50 }
Response:
  {
    "videos": [{
      "url": "string",
      "title": "string",
      "duration": number,
      "thumbnail": "string",
      "view_count": number
    }],
    "total_found": number
  }
```

### Processing Jobs

```yaml
POST /api/jobs/create
Request:
  { "urls": ["string"], "language": "en", "groq_api_key": "string" }
Response:
  { "job_id": "uuid", "total_urls": number, "status": "queued" }

GET /api/jobs/{job_id}/progress (SSE)
Response: Server-Sent Events stream
  data: {
    "overall_progress": 0.5,
    "current_url": "string",
    "current_stage": "downloading"|"transcribing",
    "completed": [{ "url": "string", "status": "success"|"error" }]
  }

GET /api/jobs/{job_id}/results
Response:
  {
    "status": "completed"|"partial"|"failed",
    "results": [{
      "url": "string",
      "title": "string",
      "transcription": "string",
      "audio_url": "/api/files/{id}.mp3"
    }]
  }
```

### Export

```yaml
POST /api/export/zip
Request: { "job_id": "uuid", "include_audio": true }
Response: application/zip

POST /api/export/json
Request: { "job_id": "uuid" }
Response: application/json
```

---

## Data Models

### Backend (Python)

```python
from dataclasses import dataclass
from enum import Enum

class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ProcessingStage(Enum):
    DOWNLOADING = "downloading"
    CHUNKING = "chunking"
    TRANSCRIBING = "transcribing"

@dataclass
class UrlResult:
    url: str
    status: str
    title: str | None = None
    transcription: str | None = None
    audio_path: str | None = None
    error: str | None = None

@dataclass
class Job:
    id: str
    urls: list[str]
    language: str
    status: JobStatus
    results: list[UrlResult]
```

### Frontend (TypeScript)

```typescript
type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';
type Platform = 'youtube' | 'instagram' | 'tiktok';

interface UrlResult {
  url: string;
  status: 'success' | 'error';
  title?: string;
  transcription?: string;
  audioUrl?: string;
  error?: string;
}

interface JobProgress {
  jobId: string;
  overallProgress: number;
  currentStage: string;
  completed: UrlResult[];
}
```
