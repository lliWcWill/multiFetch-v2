# MultiFetch v2

Modern web app for downloading and transcribing audio from YouTube, Instagram, and TikTok.

## Stack

- **Frontend**: Next.js 16 + TypeScript + Tailwind CSS 4
- **Backend**: Flask 3 + Python 3.11+
- **Transcription**: Groq Whisper API

## Project Structure

```
multiFetch-v2/
├── frontend/          # Next.js app
├── backend/           # Flask API
└── docs/              # Migration documentation
```

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
make dev  # or: flask run --debug
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Documentation

- [Migration PRD](docs/MIGRATION_PRD.md) - Requirements and API contracts
- [Implementation Phases](docs/IMPLEMENTATION_PHASES.md) - 6-phase plan
- [Modularization](docs/MODULARIZATION.md) - Code mapping from Streamlit

## Legacy

Original Streamlit app: `/home/player3/Projects/multiFetch/`
