# Implementation Phases

## Summary

| Phase | Duration | Deliverables |
|-------|----------|--------------|
| 1: Setup | 1-2 days | Project scaffolding, dev environment |
| 2: Flask Core | 2-3 days | API endpoints, URL validation, job system |
| 3: Next.js Shell | 2-3 days | Layout, config panel, URL input, SSE |
| 4: Download/Transcribe | 3-4 days | Full processing pipeline |
| 5: TikTok Collections | 2 days | Collection expansion, video selection |
| 6: Polish/Deploy | 2-3 days | Export, error handling, deployment |

**Total: 12-17 days**

---

## Phase 1: Project Setup

### Backend (Flask)

```
backend/
├── app.py              # Flask app factory
├── config.py           # Configuration
├── requirements.txt
├── .env.example
└── Makefile            # dev commands
```

**Key Dependencies:**
```txt
flask>=3.1.0
flask-cors>=4.0.0
python-dotenv>=1.0.0
yt-dlp>=2025.1.1
groq>=0.11.0
pydub>=0.25.1
validators>=0.20.0
gunicorn>=23.0.0
```

**Dev Commands:**
```bash
make dev      # flask run --debug (hot reload)
make test     # pytest
make lint     # ruff check
```

### Frontend (Next.js)

```bash
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir
cd frontend && npm install zustand @tanstack/react-query
npx shadcn-ui@latest init
```

**Dev Commands:**
```bash
npm run dev   # next dev (hot reload)
npm run build # next build
npm run lint  # eslint
```

### Verification

```bash
# Backend
cd backend && make dev
curl http://localhost:5000/api/health  # {"status": "ok"}

# Frontend
cd frontend && npm run dev
# Visit http://localhost:3000
```

---

## Phase 2: Flask API Core

### Files to Create

```
backend/
├── api/
│   ├── __init__.py
│   ├── config.py       # /api/config/*
│   ├── urls.py         # /api/urls/*
│   ├── jobs.py         # /api/jobs/*
│   └── tiktok.py       # /api/tiktok/*
├── services/
│   ├── platform_detector.py
│   ├── job_manager.py
│   └── sse.py
├── models/
│   └── job.py
└── utils/
    └── constants.py    # Regex patterns
```

### Port from app.py

| Function | Line | New Location |
|----------|------|--------------|
| `SUPPORTED_PLATFORMS` | 83-97 | `utils/constants.py` |
| `TIKTOK_COLLECTION_PATTERNS` | 100-122 | `utils/constants.py` |
| `detect_platform()` | 323 | `services/platform_detector.py` |
| `validate_url()` | 387 | `services/platform_detector.py` |

### Verification

```bash
curl -X POST http://localhost:5000/api/urls/validate \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://youtube.com/watch?v=dQw4w9WgXcQ"]}'
# {"valid_urls": [...], "invalid_urls": []}
```

---

## Phase 3: Next.js Frontend Shell

### Files to Create

```
frontend/src/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   └── globals.css
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── ConfigPanel.tsx
│   └── input/
│       ├── UrlInput.tsx
│       └── UrlValidator.tsx
├── hooks/
│   ├── useApi.ts
│   └── useJobProgress.ts
├── lib/
│   └── api.ts
└── store/
    ├── configStore.ts
    └── jobStore.ts
```

### Install Shadcn Components

```bash
npx shadcn-ui@latest add button input textarea progress card badge
```

---

## Phase 4: Download & Transcribe

### Port from app.py

| Function | Line | New Location |
|----------|------|--------------|
| `download_audio_enhanced()` | 459-791 | `services/downloader.py` |
| `chunk_audio()` | 1054-1185 | `services/audio.py` |
| `transcribe_audio()` | 1220-1573 | `services/transcriber.py` |
| `RateLimiter` | 1187 | `services/rate_limiter.py` |
| `get_cache_key()` | 401 | `services/cache.py` |

### Verification

```bash
curl -X POST http://localhost:5000/api/jobs/create \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://youtube.com/watch?v=dQw4w9WgXcQ"], "language": "en", "groq_api_key": "..."}'

# Monitor SSE
curl -N http://localhost:5000/api/jobs/{job_id}/progress
```

---

## Phase 5: TikTok Collections

### Port from app.py

| Function | Line | New Location |
|----------|------|--------------|
| `detect_tiktok_collection()` | 332 | `services/tiktok.py` |
| `resolve_tiktok_short_url()` | 347-385 | `services/tiktok.py` |
| `expand_tiktok_collection()` | 793-923 | `services/tiktok.py` |

### Frontend Components

```
components/tiktok/
├── CollectionExpander.tsx
├── VideoSelector.tsx
└── VideoTable.tsx
```

---

## Phase 6: Polish & Deploy

### Export Functions (from app.py lines 3004-3321)

- ZIP export with audio + transcripts
- JSON export with metadata
- Cleanup handlers

### Deployment

**Frontend (Vercel):**
```bash
cd frontend && vercel
```

**Backend (Railway):**
```bash
cd backend && railway up
```

### Docker (optional)

```yaml
# docker-compose.yml
services:
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
  backend:
    build: ./backend
    ports: ["5000:5000"]
```
