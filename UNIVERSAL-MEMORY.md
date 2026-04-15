# Jarvis — Universal Memory & Project Command Center

> Read this file at the start of every session. It is the single source of truth for project state, architecture decisions, and conventions.

---

## Project Identity

**Jarvis** is a local household operating system — LLM-powered, 100% local, running on a homelab.  
Server: `192.168.111.28:8000` (EliteBook)  
Primary model: `gemma3:27b` via Ollama  
Entry points: `server.py` (FastAPI), `main.py` (CLI), `start.py` (production harness)

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| 1 | Foundation | ✅ COMPLETE |
| 2 | Intelligence Layer | ✅ COMPLETE (554 tests) |
| 3 | Knowledge Engines | ✅ COMPLETE (1626+ tests, 7 engines) |
| 4A | Web Dashboard | ✅ COMPLETE (React + Vite + Tailwind, 27 new tests) |
| 4B | Android Launcher | ⬜ PLANNED |
| 4C | Custom Android OS | ⬜ PLANNED |
| 5 | Computer Vision | ⬜ PLANNED |
| 6 | Smart Home Hub | ⬜ PLANNED |
| 7 | Network Security Agent | ⬜ PLANNED |
| 8 | Project Forge | 🔶 SCAFFOLDED |
| 9 | Model Training Pipeline | ⬜ PLANNED |

---

## Architecture Overview

```
server.py          FastAPI HTTP + WebSocket server
  └─ /api/*        All REST endpoints
  └─ /             Serves static/index.html (React dashboard)
  └─ /static/*     JS/CSS assets from static/assets/

jarvis/
  core.py          LLM routing brain
  specialists/     6 domain agents (grocery, finance, calendar, home, news, investor)
  engines/         7 knowledge accumulation engines
  memory*.py       4-tier memory system
  knowledge_lake.py Cross-adapter fact store (SQLite)
  household_state.py State machine
  blackboard.py    Cross-specialist pub/sub
  engine_store.py  Per-engine SQLite DBs in data/engines/
  preferences.py   JSON user preferences
  agent_memory.py  Decision audit log (SQLite)

dashboard/         React source (Vite + Tailwind)
  src/
    App.jsx        Root component with tab navigation
    api.js         API client (all endpoints)
    components/    7 panel components
  → builds to static/ (served by FastAPI)

static/            Built React app (do not edit directly)
tests/             pytest suite (~1700 tests)
```

---

## API Endpoints (Phase 4A additions)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/specialists` | Status of all 6 specialists |
| GET | `/api/knowledge-lake` | Browse/search Knowledge Lake facts |
| GET | `/api/household-state` | Current state + history |
| PUT | `/api/household-state` | Transition/add/remove modifier |
| GET | `/api/engines/status` | Record counts for all 7 engines |
| GET | `/api/blackboard` | Cross-specialist blackboard posts |

---

## Key Conventions

- **Tests**: All tests in `tests/`. Run with `pytest tests/ -q`. Mocks for LLM/Ollama always required.
- **No direct edits to `static/`** — edit `dashboard/src/` and run `npm run build` in `dashboard/`.
- **Env vars**: See `.env.example`. `JARVIS_DEV_MODE=true` enables wildcard CORS.
- **Data files**: All SQLite DBs in `data/`. Engine DBs in `data/engines/`.
- **CORS**: PUT method allowed (needed for household state updates).

---

## Running Locally

```bash
# API server
python server.py

# Dashboard dev server (hot reload, proxies /api to :8000)
cd dashboard && npm run dev

# Build dashboard for production
cd dashboard && npm run build

# Tests
pytest tests/ -q
```

---

## Hardware

| Role | IP | RAM | Notes |
|------|----|-----|-------|
| Primary brain / Jarvis server | 192.168.111.28 | 16GB | EliteBook, FastAPI + Ollama |
| Worker node | 192.168.111.27 | 8GB | Mini PC, Forge agents |
| Compute 1 | — | 128GB (96GB GPU) | GMKtec EVO-X2, model training |
| Compute 2 | — | 128GB (96GB GPU) | GMKtec EVO-X2, parallel engines |
