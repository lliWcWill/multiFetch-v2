# MultiFetch v2 - Progress Tracker

**Last Updated**: 2026-01-25
**Current Phase**: 3 - Frontend-Backend Integration
**Status**: Complete

---

## Quick Context for New Agent Sessions

> **READ THIS FIRST**: This file is the source of truth for project progress.
> After compaction or new session, read this file + CLAUDE.md to understand state.

### What This Project Is
- Migration from Streamlit monolith (`/home/player3/Projects/multiFetch/app.py`) to Next.js + Flask
- Source app: ~3400 lines, handles YouTube/Instagram/TikTok download + Groq transcription
- Target: Decoupled frontend (Next.js 16) + backend (Flask 3.1) with SSE for real-time progress

### Current Working Branch
```
main (local development)
```

### Active Task
- [x] Phase 1 complete (frontend UI + backend venv + hot reload verified)
- [x] Phase 2 complete: all core API endpoints working
- [x] Phase 3 complete: frontend connected to Flask API
- [ ] Phase 4: Download & Transcribe (next)

---

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Local development (current) |
| `prod` | Production deployment (create later) |
| `feature/*` | Feature branches |

### CI/CD Flow
```
feature/xyz → PR → main → PR → prod → GitHub Actions → Deploy
```

---

## Phase Checklist

### Phase 1: Project Setup [COMPLETE]
- [x] Create repo structure (frontend/, backend/, docs/)
- [x] Initialize git + GitHub repo
- [x] Write migration docs (PRD, phases, modularization)
- [x] Create Flask app skeleton with hot reload (`make dev`)
- [x] Set up Docker Compose (dev + prod)
- [x] Create Dockerfiles (frontend + backend)
- [x] Set up GitHub Actions CI/CD workflow
- [x] Create DEPLOYMENT.md guide
- [x] Scaffold Next.js frontend
- [x] Build frontend UI (sidebar config, URL input, results)
- [x] Set up backend venv and verify hot reload
- [ ] Test Docker Compose dev environment (optional, deferred)
- [ ] Commit Phase 1 complete (pending)

### Phase 2: Flask API Core [COMPLETE]
- [x] Port URL regex patterns to `utils/constants.py`
- [x] Create `services/platform_detector.py`
- [x] Create `/api/urls/validate` endpoint
- [x] Create `/api/config/validate` endpoint
- [x] Create job management system (`services/job_manager.py`, `api/jobs.py`)
- [x] Implement SSE for progress streaming (`api/sse.py`)
- [ ] Write tests (deferred to Phase 4)

### Phase 3: Frontend-Backend Integration [COMPLETE]
- [x] Create layout with sidebar (done in Phase 1)
- [x] Build ConfigPanel (API key, cookies, language) (done in Phase 1)
- [x] Build UrlInput component (done in Phase 1)
- [x] Create Zustand stores (`stores/configStore.ts`, `stores/jobStore.ts`)
- [x] Create API client (`lib/api.ts`)
- [x] Implement SSE hook for progress (`hooks/useSSE.ts`)
- [x] Connect to Flask API (page.tsx updated)

### Phase 4: Download & Transcribe [NOT STARTED]
- [ ] Port download_audio_enhanced()
- [ ] Port chunk_audio()
- [ ] Port transcription logic
- [ ] Port caching system
- [ ] Create /api/jobs/* endpoints
- [ ] Build processing UI components
- [ ] End-to-end test

### Phase 5: TikTok Collections [NOT STARTED]
- [ ] Port TIKTOK_COLLECTION_PATTERNS
- [ ] Port expand_tiktok_collection()
- [ ] Create /api/tiktok/expand endpoint
- [ ] Build collection UI components

### Phase 6: Polish & Deploy [NOT STARTED]
- [ ] Implement export (ZIP, JSON)
- [ ] Error handling + edge cases
- [ ] Test Docker prod build
- [ ] Set up server deployment
- [ ] Configure GitHub secrets
- [ ] Deploy to production

---

## Docker Setup

### Local Development
```bash
docker-compose -f docker-compose.dev.yml up
```

### Production
```bash
docker-compose up -d
```

### Images
- `ghcr.io/lliwcwill/multifetch-frontend`
- `ghcr.io/lliwcwill/multifetch-backend`

---

## Key Files Reference

### Source (to port from)
| File | What to Extract |
|------|-----------------|
| `/home/player3/Projects/multiFetch/app.py:83-122` | Platform regex patterns |
| `/home/player3/Projects/multiFetch/app.py:323-403` | URL detection/validation |
| `/home/player3/Projects/multiFetch/app.py:459-791` | Download engine |
| `/home/player3/Projects/multiFetch/app.py:793-923` | TikTok collection expansion |
| `/home/player3/Projects/multiFetch/app.py:1054-1185` | Audio chunking |
| `/home/player3/Projects/multiFetch/app.py:1187-1573` | Transcription + rate limiting |
| `/home/player3/Projects/multiFetch/app.py:3004-3321` | Export functions |

### Target Structure
```
multiFetch-v2/
├── PROGRESS.md              # This file
├── CLAUDE.md                # Agent instructions
├── docker-compose.yml       # Production
├── docker-compose.dev.yml   # Development
├── .github/workflows/       # CI/CD
├── frontend/
│   ├── Dockerfile           # Production
│   ├── Dockerfile.dev       # Development
│   └── src/
│       ├── app/
│       │   └── page.tsx     # Main page (connected to API) ✓
│       ├── stores/
│       │   ├── configStore.ts   # Config state ✓
│       │   └── jobStore.ts      # Job state ✓
│       ├── lib/
│       │   └── api.ts       # API client ✓
│       └── hooks/
│           └── useSSE.ts    # SSE hook ✓
└── backend/
    ├── Dockerfile           # Production
    ├── Dockerfile.dev       # Development
    ├── app.py               # Flask factory
    ├── api/
    │   ├── urls.py          # URL validation ✓
    │   ├── config.py        # Config validation ✓
    │   ├── jobs.py          # Job CRUD endpoints ✓
    │   └── sse.py           # SSE progress streaming ✓
    ├── services/
    │   ├── platform_detector.py  # Platform detection ✓
    │   └── job_manager.py   # Job state management ✓
    └── utils/
        └── constants.py     # Regex patterns ✓
```

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-21 | SSE over WebSockets | Simpler, serverless-compatible |
| 2026-01-21 | Flask with `make dev` | Hot reload via debug mode |
| 2026-01-21 | Docker Compose | Consistent dev/prod environments |
| 2026-01-21 | GitHub Actions CI/CD | Auto deploy on merge to prod |
| 2026-01-21 | ghcr.io for images | Free with GitHub, no Docker Hub limits |
| 2026-01-21 | No co-author attribution | User preference |
| 2026-01-25 | Zustand for state | Simple, minimal boilerplate |
| 2026-01-25 | Persist config in localStorage | Better UX, remember settings |

---

## Notes for Future Sessions

- User on WSL2 with Docker Desktop
- Password for sudo: `2345`
- GitHub CLI authenticated as `lliWcWill`
- User prefers hot reload dev experience
- Keep it simple, no over-engineering
