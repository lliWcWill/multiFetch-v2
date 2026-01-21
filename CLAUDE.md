# CLAUDE.md - Agent Instructions

## Project: MultiFetch v2

Migration from Streamlit to Next.js + Flask.

---

## CRITICAL: Read First on New Session

1. **Read `PROGRESS.md`** - Current phase, active tasks, what's done
2. **Check git status** - See uncommitted work
3. **Check current branch** - Know where you are

```bash
cd /home/player3/Projects/multiFetch-v2
cat PROGRESS.md | head -50
git status
git branch
```

---

## Project Structure

```
multiFetch-v2/
├── PROGRESS.md         # ⭐ Progress tracker (UPDATE THIS)
├── CLAUDE.md           # This file
├── README.md
├── frontend/           # Next.js 16 + TypeScript + Tailwind
└── backend/
    ├── app.py          # Flask app (make dev for hot reload)
    ├── Makefile        # dev, test, lint commands
    ├── api/            # Route blueprints
    ├── services/       # Business logic
    └── utils/          # Constants, helpers
```

---

## Commands

### Backend (Flask)
```bash
cd /home/player3/Projects/multiFetch-v2/backend
make dev          # Hot reload server on :5000
make test         # Run pytest
make lint         # Ruff check
```

### Frontend (Next.js)
```bash
cd /home/player3/Projects/multiFetch-v2/frontend
npm run dev       # Hot reload server on :3000
npm run build     # Production build
npm run lint      # ESLint
```

---

## Source Reference

Original Streamlit app to port from:
```
/home/player3/Projects/multiFetch/app.py (~3400 lines)
```

Key line ranges documented in `docs/MODULARIZATION.md`

---

## Workflow Rules

1. **Update PROGRESS.md** after completing tasks
2. **Feature branches**: `phase-X/feature-name`
3. **No co-author** in commits (configured in ~/.claude/settings.json)
4. **Hot reload**: Both frontend and backend must support it
5. **Keep it simple**: No over-engineering

---

## Tech Stack

| Layer | Tech | Version |
|-------|------|---------|
| Frontend | Next.js (App Router) | 16.x |
| Frontend | TypeScript | 5.9.x |
| Frontend | Tailwind CSS | 4.x |
| Backend | Flask | 3.1.x |
| Backend | Python | 3.11+ |
| Real-time | SSE | Native |

---

## User Preferences

- Prefers `npm run dev` / `make dev` style hot reload
- No excessive CSS styling attempts
- No emojis in code unless requested
- Keep commits clean, no co-author attribution
- Password for sudo if needed: `2345`

---

## Multi-Agent Notes

If spawning sub-agents:
1. Give them clear scope (which files, which feature)
2. Have them read CLAUDE.md + PROGRESS.md first
3. Each agent should work on separate files when possible
4. Update PROGRESS.md when done
