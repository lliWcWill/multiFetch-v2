# MultiFetch v2 - Progress Tracker

**Last Updated**: 2026-01-21
**Current Phase**: 2 - Flask API Core
**Status**: In Progress

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
- [x] Phase 2 started: URL validation endpoint working
- [ ] Continue Phase 2: config validation, job management, SSE

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

### Phase 2: Flask API Core [IN PROGRESS]
- [x] Port URL regex patterns to `utils/constants.py`
- [x] Create `services/platform_detector.py`
- [x] Create `/api/urls/validate` endpoint
- [ ] Create `/api/config/validate` endpoint
- [ ] Create job management system
- [ ] Implement SSE for progress streaming
- [ ] Write tests

### Phase 3: Next.js Frontend Shell [NOT STARTED]
- [ ] Create layout with sidebar
- [ ] Build ConfigPanel (API key, cookies, language)
- [ ] Build UrlInput component
- [ ] Create Zustand stores (config, jobs)
- [ ] Implement SSE hook for progress
- [ ] Connect to Flask API

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
│   └── src/                 # Next.js app
└── backend/
    ├── Dockerfile           # Production
    ├── Dockerfile.dev       # Development
    ├── app.py               # Flask factory
    ├── api/
    │   └── urls.py          # URL validation endpoints ✓
    ├── services/
    │   └── platform_detector.py  # Platform detection ✓
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

---

## Notes for Future Sessions

- User on WSL2 with Docker Desktop
- Password for sudo: `2345`
- GitHub CLI authenticated as `lliWcWill`
- User prefers hot reload dev experience
- Keep it simple, no over-engineering
