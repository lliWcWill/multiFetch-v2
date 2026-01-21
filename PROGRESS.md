# MultiFetch v2 - Progress Tracker

**Last Updated**: 2026-01-21
**Current Phase**: 1 - Project Setup
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
main
```

### Active Task
- [ ] Scaffold Next.js frontend with hot reload

---

## Phase Checklist

### Phase 1: Project Setup [IN PROGRESS]
- [x] Create repo structure (frontend/, backend/, docs/)
- [x] Initialize git + GitHub repo
- [x] Write migration docs (PRD, phases, modularization)
- [x] Create Flask app skeleton with hot reload (`make dev`)
- [ ] Scaffold Next.js frontend
- [ ] Verify both dev servers run with hot reload
- [ ] Create initial commit for Phase 1 complete

### Phase 2: Flask API Core [NOT STARTED]
- [ ] Port URL regex patterns to `utils/constants.py`
- [ ] Create `services/platform_detector.py` (detect_platform, validate_url)
- [ ] Create `/api/urls/validate` endpoint
- [ ] Create `/api/config/validate` endpoint
- [ ] Create job management system
- [ ] Implement SSE for progress streaming
- [ ] Write tests for validators

### Phase 3: Next.js Frontend Shell [NOT STARTED]
- [ ] Create layout with sidebar
- [ ] Build ConfigPanel (API key, cookies, language)
- [ ] Build UrlInput component
- [ ] Create Zustand stores (config, jobs)
- [ ] Implement SSE hook for progress
- [ ] Connect to Flask API

### Phase 4: Download & Transcribe [NOT STARTED]
- [ ] Port download_audio_enhanced() to services/downloader.py
- [ ] Port chunk_audio() to services/audio.py
- [ ] Port transcription logic to services/transcriber.py
- [ ] Port caching system
- [ ] Create /api/jobs/* endpoints
- [ ] Build processing UI components
- [ ] End-to-end test: URL → transcription

### Phase 5: TikTok Collections [NOT STARTED]
- [ ] Port TIKTOK_COLLECTION_PATTERNS
- [ ] Port expand_tiktok_collection()
- [ ] Create /api/tiktok/expand endpoint
- [ ] Build CollectionExpander component
- [ ] Build VideoSelector component

### Phase 6: Polish & Deploy [NOT STARTED]
- [ ] Implement export (ZIP, JSON)
- [ ] Error handling + edge cases
- [ ] Docker configuration
- [ ] Vercel deployment (frontend)
- [ ] Railway/Fly.io deployment (backend)
- [ ] Final testing

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

### Target (new structure)
```
multiFetch-v2/
├── frontend/           # Next.js 16 + TypeScript + Tailwind
├── backend/
│   ├── app.py          # Flask factory
│   ├── api/            # Route blueprints
│   ├── services/       # Business logic
│   ├── models/         # Data models
│   └── utils/          # Constants, helpers
└── docs/               # PRD, phases, modularization
```

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-21 | SSE over WebSockets | Simpler, serverless-compatible, unidirectional is enough |
| 2026-01-21 | Flask with `make dev` | Hot reload via `flask run --debug` |
| 2026-01-21 | Vercel + Railway | Split deployment, best DX for each stack |
| 2026-01-21 | No co-author attribution | User preference |

---

## Git Workflow

1. **Feature branches**: `phase-X/feature-name`
2. **PR per phase**: Merge to main when phase complete
3. **Commits**: Descriptive, no co-author line

### Branch Status
| Branch | Status | PR |
|--------|--------|-----|
| main | Active | - |

---

## Notes for Future Sessions

- User password for sudo: `2345`
- GitHub CLI authenticated as `lliWcWill`
- User prefers hot reload dev experience (`npm run dev` style)
- User dislikes excessive CSS/dark mode attempts
- Keep it simple, no over-engineering
