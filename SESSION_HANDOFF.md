# Session Handoff Prompt

Copy and paste this at the start of a new Claude Code session:

---

## Quick Start Prompt (Copy This)

```
I'm continuing work on MultiFetch v2 - a migration from Streamlit to Next.js + Flask.

**Read these files first to get context:**
1. /home/player3/Projects/multiFetch-v2/PROGRESS.md - Current phase and task checklist
2. /home/player3/Projects/multiFetch-v2/CLAUDE.md - Project conventions and commands

**Repo:** https://github.com/lliWcWill/multiFetch-v2
**Working directory:** /home/player3/Projects/multiFetch-v2

**Current State (as of last session):**
- Phase 1 nearly complete - frontend UI built with "Data Terminal" aesthetic
- Next.js 16 + Tailwind 4 frontend working (npm run dev)
- Flask backend skeleton exists but needs venv setup
- Docker Compose files ready (dev + prod)
- GitHub Actions CI/CD configured

**Next tasks:**
1. Set up backend venv: `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. Test backend hot reload: `make dev`
3. Begin Phase 2: Flask API Core (port URL validation, platform detection from original app.py)

**Source to port from:** /home/player3/Projects/multiFetch/app.py (~3400 lines)

Read PROGRESS.md and CLAUDE.md, then continue where we left off.
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `PROGRESS.md` | Phase checklist, current state, decisions log |
| `CLAUDE.md` | Agent instructions, commands, conventions |
| `docs/MODULARIZATION.md` | Line-by-line mapping of what to port |
| `docs/MIGRATION_PRD.md` | Full PRD with API contracts |
| `docs/IMPLEMENTATION_PHASES.md` | 6-phase breakdown |

## Commands Cheatsheet

```bash
# Frontend
cd /home/player3/Projects/multiFetch-v2/frontend
npm run dev      # Hot reload on :3000
npm run build    # Production build

# Backend
cd /home/player3/Projects/multiFetch-v2/backend
source .venv/bin/activate
make dev         # Hot reload on :5000 (flask --debug)

# Docker
docker-compose -f docker-compose.dev.yml up   # Dev environment
docker-compose up -d                           # Production

# Git
git status && git diff    # Check changes
git add -A && git commit -m "msg" && git push
```

## What's Been Built

### Frontend (`/frontend/src/app/`)
- `layout.tsx` - Root layout with JetBrains Mono + Space Grotesk fonts
- `globals.css` - Dark theme, cyan accents, custom components
- `page.tsx` - Full UI with:
  - ConfigPanel (sidebar): API key, language, tier toggle
  - UrlInput: Platform detection, validation preview
  - ResultCard: Expandable transcription results
  - Export buttons (mocked)

### Backend (`/backend/`)
- `app.py` - Flask factory pattern with health endpoint
- `Makefile` - `make dev` for hot reload
- `requirements.txt` - Dependencies ready
- Needs: venv setup, then API endpoints

### Infrastructure
- `docker-compose.yml` - Production config
- `docker-compose.dev.yml` - Dev with volume mounts
- `.github/workflows/deploy.yml` - CI/CD on merge to prod
- `Dockerfile` + `Dockerfile.dev` for both services

## Phase 2 Preview (Next Up)

Port these from `/home/player3/Projects/multiFetch/app.py`:

1. **URL Patterns** (lines 83-122) → `backend/utils/constants.py`
2. **Platform Detection** (lines 323-403) → `backend/services/platform_detector.py`
3. **API Endpoints**:
   - `POST /api/urls/validate` - Validate URLs, detect platforms
   - `POST /api/config/validate` - Validate Groq API key
4. **SSE Setup** for real-time progress streaming
