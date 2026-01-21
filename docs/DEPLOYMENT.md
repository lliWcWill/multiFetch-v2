# Deployment Guide

## Branch Strategy

| Branch | Purpose | Docker |
|--------|---------|--------|
| `main` | Local development | `docker-compose.dev.yml` |
| `prod` | Production deployment | `docker-compose.yml` |

### Workflow
```
feature/xyz → PR → main (dev) → PR → prod (deploy)
```

---

## Docker Architecture

```
┌─────────────────────────────────────────────┐
│              Docker Compose                  │
├─────────────────┬───────────────────────────┤
│   frontend      │      backend              │
│   (Next.js)     │      (Flask)              │
│   Port: 3000    │      Port: 5000           │
└─────────────────┴───────────────────────────┘
```

### Images
- `multifetch-frontend`: Next.js app
- `multifetch-backend`: Flask API

---

## Local Development (main branch)

### Prerequisites
- Docker Desktop (WSL2 backend on Windows)
- Docker Compose

### Quick Start
```bash
# Start both services with hot reload
docker-compose -f docker-compose.dev.yml up

# Or run individually
docker-compose -f docker-compose.dev.yml up frontend
docker-compose -f docker-compose.dev.yml up backend
```

### Hot Reload
- Frontend: Volume mounts `./frontend/src` → changes reflect immediately
- Backend: Volume mounts `./backend` → Flask debug mode auto-reloads

### Without Docker (native)
```bash
# Terminal 1: Backend
cd backend && make dev

# Terminal 2: Frontend
cd frontend && npm run dev
```

---

## Production Deployment (prod branch)

### CI/CD Flow

```
1. Merge PR to main
   ↓
2. GitHub Actions triggered
   ↓
3. Build Docker images
   ↓
4. Push to GitHub Container Registry (ghcr.io)
   ↓
5. SSH to server
   ↓
6. git pull && docker-compose pull && docker-compose up -d
```

### GitHub Actions Triggers
- Push to `prod` branch
- Manual workflow dispatch

### Server Setup (one-time)
```bash
# On server
git clone https://github.com/lliWcWill/multiFetch-v2.git
cd multiFetch-v2
cp .env.example .env  # Edit with production values
docker-compose pull
docker-compose up -d
```

### Environment Variables (Production)
```bash
# .env on server
GROQ_API_KEY=your_production_key
FLASK_ENV=production
FRONTEND_URL=https://your-domain.com
```

---

## Docker Files

### docker-compose.dev.yml (Local Dev)
- Hot reload enabled
- Source code mounted as volumes
- Debug mode on

### docker-compose.yml (Production)
- Optimized builds
- No source mounts
- Production configs

### Dockerfiles
- `frontend/Dockerfile` - Multi-stage Next.js build
- `backend/Dockerfile` - Python with gunicorn

---

## GitHub Actions

### `.github/workflows/deploy.yml`
Triggers on:
- Push to `prod` branch
- Manual dispatch

Actions:
1. Build frontend image
2. Build backend image
3. Push to ghcr.io
4. SSH deploy to server

### Secrets Required
| Secret | Description |
|--------|-------------|
| `GHCR_TOKEN` | GitHub Container Registry token |
| `SERVER_HOST` | Production server IP/hostname |
| `SERVER_USER` | SSH username |
| `SERVER_SSH_KEY` | SSH private key |
| `GROQ_API_KEY` | Production Groq API key |

---

## Ports

| Service | Dev Port | Prod Port |
|---------|----------|-----------|
| Frontend | 3000 | 3000 |
| Backend | 5000 | 5000 |
| Nginx (optional) | - | 80/443 |

---

## Commands Reference

```bash
# Local dev
docker-compose -f docker-compose.dev.yml up
docker-compose -f docker-compose.dev.yml down
docker-compose -f docker-compose.dev.yml logs -f

# Production
docker-compose up -d
docker-compose pull
docker-compose down
docker-compose logs -f

# Rebuild specific service
docker-compose build frontend
docker-compose build backend
```
