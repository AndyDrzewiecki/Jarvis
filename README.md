# Jarvis — Household Operating System

> A self-improving, fully local AI that runs your home. Manages finance, health, family scheduling, local intelligence, and legal/regulatory awareness. Learns your household's patterns. Trains its own models. Replaces Alexa, Google Home, and every smart home hub — 100% on your hardware.

**1,711 tests passing** · **7 knowledge engines** · **6 specialists** · **Phase 3 complete** · No cloud required

---

## What It Is

Jarvis is a local household operating system built on [Ollama](https://ollama.ai). You talk to it in plain English; it routes your request to the right specialist, remembers everything across conversations, and proactively surfaces what matters — market moves, health alerts, family activity ideas, medication recalls — without sending your data anywhere.

```
You: "What should we make for dinner this week given we're tight on budget?"
Jarvis: "Based on current inventory and your $85 remaining grocery budget,
        here are 5 meals using what you already have — estimated restock $12..."

You: "Are there any drug recalls I should know about?"
Jarvis: "OpenFDA flagged 2 relevant events this week. AQI in your area is 87
        (Moderate) — worth noting for the kids' outdoor time tomorrow."
```

---

## Current Status

| Phase | What | Status | Tests |
|-------|------|--------|-------|
| **1** | Foundation — LLM router, adapters, FastAPI, security | ✅ Complete | — |
| **2** | Intelligence Layer — 4-tier memory, 6 specialists, self-improvement loops | ✅ Complete | 554 |
| **3** | Knowledge Engines — 7 live data pipelines (8M+ records/year) | ✅ Complete | 1,626 |
| **8** | Project Forge — autonomous dev framework (scaffolding) | 🔨 In Progress | 85 |
| **4** | Web Dashboard + Android Launcher | 📋 Planned | — |
| **5** | Computer Vision | 📋 Planned | — |
| **6** | Smart Home Hub (BLE/IoT/Voice) | 📋 Planned | — |
| **7** | Network Security Agent | 📋 Planned | — |
| **9** | Model Training Pipeline (LoRA) | 📋 Planned | — |

---

## Quick Start

**Prerequisites:** [Ollama](https://ollama.ai) installed and running.

```bash
# 1. Pull models
ollama pull gemma3:27b
ollama pull qwen2.5:0.5b

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure (optional — all keys are optional, engines skip missing sources)
cp .env.example .env
# Edit .env with your location, API keys, preferences

# 4. Run
python start.py              # Full: API server + specialists + engines
python start.py --cli        # CLI chat only
python start.py --api-only   # API server, no background loops
python start.py --check      # Health check — verify everything is wired up
```

**API:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what should I cook tonight?"}'
```

---

## Architecture

### Core

```
┌──────────────────���────────────────────────────────��──────────────┐
│                          Jarvis Core                              │
│        Rich CLI ── FastAPI Server ── LLM Router (Ollama)         │
└─────────────────────��────┬────────────────────────���──────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   Memory Bus         Blackboard       Scheduler
 (thalamus routing)  (cross-specialist (APScheduler
                      pub/sub signals)  cron jobs)
          │
   ┌──────┴──────────────────────────┐
   ▼          ▼          ▼           ▼
Working    Episodic   Semantic    Procedural
Memory     Store      Store       Store
(session)  (SQLite)   (SQLite +   (SQLite)
                      ChromaDB)
```

### Knowledge Engines (Phase 3)

Seven live data pipelines accumulate world knowledge continuously through a shared `IngestionBuffer` → `EngineStore` pipeline:

| Engine | Data Sources | Domain |
|--------|-------------|--------|
| **Financial** | FRED, Yahoo Finance, SEC EDGAR | Markets, economy, filings |
| **Geopolitical** | GDELT, Congress.gov, world news RSS | World events, legislation |
| **AI/ML Research** | arXiv, GitHub, HuggingFace | Research papers, model releases |
| **Legal & Regulatory** | Federal Register, IRS, MN Legislature | Rules, tax changes |
| **Health & Wellness** | CDC RSS, OpenFDA, AirNow AQI | Drug recalls, health alerts, air quality |
| **Local Intelligence** | NWS Weather, Eventbrite, local RSS | Local events, weather, community |
| **Family & Life** | NPS Parks, event cross-ref, AAP RSS | Activities, parenting, outings |

All engines deduplicate, score, and route through the Knowledge Lake. Target: 8M+ records/year.

### Specialist Loops (Phase 2)

Six autonomous background specialists run on cron schedules, share signals via the blackboard, and evolve their own operating guidelines based on graded outcomes:

| Specialist | Schedule | Domain |
|------------|----------|--------|
| **Grocery** | Every 4h | Prices, inventory, meal planning |
| **Finance** | Every 6h | Budget, spending patterns |
| **Calendar** | Every 2h | Schedule conflicts, reminders |
| **Home** | 8 AM daily | Maintenance, seasonal tasks |
| **News** | Every 3h | RSS feeds, relevant headlines |
| **Investor** | 9 AM + 4 PM (weekdays) | Market moves, portfolio signals |

### Self-Improvement Loop

Every night Jarvis runs automatically:

```
11 PM  Short-term grading  — LLM grades all recent decisions (good/neutral/poor)
 3 AM  Consolidation       — Episodes compressed into Semantic memory
 2 AM  Long-term grading   — Re-grades decisions 7–30 days later with hindsight
1st    Guideline evolution — Rewrites specialist guidelines from graded patterns
Mon    Context rebuild     — Refreshes prompt context for each specialist
```

### Memory System

| Tier | Store | Purpose | Retention |
|------|-------|---------|-----------|
| **Working** | In-memory | Current conversation context | Session |
| **Episodic** | SQLite | Full conversation episodes | 90 days |
| **Semantic** | SQLite + ChromaDB | Facts, prices, schedules, preferences | Long-term |
| **Procedural** | SQLite | Reinforced routines, fast-paths | Permanent |

The **Knowledge Lake** wraps semantic storage with time-decay confidence scoring — prices decay in 3 days, research in 90 days, preferences in 180 days.

---

## Project Forge (Phase 8) — Autonomous Dev Platform

Project Forge is the self-improving development layer. Once complete, Jarvis will autonomously build, test, review, and improve software across all projects — with minimal human intervention.

### 5-Brain Architecture

| Brain | Model | Role |
|-------|-------|------|
| **Brain 0** | Gemma 4 27B | User-facing — routes requests, responds |
| **Brain 1: Critic** | 12B | Monitors output quality, catches hallucinations, writes verdicts |
| **Brain 2: Pattern Analyst** | 12B | Reads feedback + verdicts, identifies trends, proposes fixes |
| **Brain 3: Tester** | 27B | Runs sandboxed A/B tests on proposed fixes, promotes or discards |
| **Brain 4: Code Auditor** | 12B | Reviews code/prompt changes for bugs, security, regressions |

### 7-Layer Introspection Memory

```
Layer 1  Raw interaction logs
Layer 2  Decision audit trail      — what was routed where, why
Layer 3  User correction pairs     — bad_output → good_output (LoRA training data)
Layer 4  Hallucination registry
Layer 5  Routing accuracy tracking
Layer 6  Prompt evolution history  — what changed, when, why, what improved
Layer 7  Meta-patterns             — cross-layer insights, systemic failure modes
```

### 3-Tier Self-Modification

- **Tier 1 (auto-apply):** Prompt tweaks, retry logic, adapter description rewording
- **Tier 2 (weekly review):** Code modifications, new capabilities — queued for human approval
- **Tier 3 (manual trigger):** LoRA fine-tuning batches — prepared, waits for green light

### Current Forge Scaffolding (`jarvis/forge/`)

| Module | Description |
|--------|-------------|
| `memory_store.py` | SQLite-backed 7-layer shared memory — all agents read before acting, write after |
| `agent_base.py` | `BaseDevAgent` ABC — `read_memory()`, `write_memory()`, `execute_task()`, `run()`, `report_status()` |
| `critic.py` | Brain 1 — evaluates output quality, registers hallucinations to Layer 4 |
| `orchestrator.py` | Routes tasks to registered agents, logs routing decisions to Layer 2 |
| `trainer.py` | Reviews interaction history, rewrites prompts, exports LoRA pairs (ShareGPT/DPO) |

---

## Roadmap

```
Phase 1  ████████████████████  COMPLETE — Foundation (router, adapters, FastAPI, security)
Phase 2  ████████████████████  COMPLETE — Intelligence Layer (memory, specialists, self-improvement)
Phase 3  ████████████████████  COMPLETE — Knowledge Engines (all 7 engines, 1,711 tests)
Phase 4  ░░░░░░░░░░░░░░░░░░░░  PLANNED  — Web Dashboard + Android Launcher + Custom OS
Phase 5  ░░░░░░░░░░░░░░░░░░░░  PLANNED  — Computer Vision (tablet cameras, object recognition)
Phase 6  ░░░░░░░░░░░░░░░░░░░░  PLANNED  — Smart Home Hub (BLE, Zigbee, voice control)
Phase 7  ░░░░░░░░░░░░░░░░░░░░  PLANNED  — Network Security (Firewalla, Aruba, threat detection)
Phase 8  ▓░░░░░░░░░░░░░░░░░░░  IN PROG  — Project Forge (autonomous dev, 5-brain architecture)
Phase 9  ░░░░░░░░░░░░░░░░░░░░  PLANNED  — Model Training (LoRA fine-tuning on EVO-X2 cluster)
```

**Phase 4** — Web Dashboard: React frontend hitting FastAPI, real-time specialist status, Knowledge Lake browser, household controls. Android app with wake-word detection.

**Phase 6** — Smart Home Hub: BLE device discovery, HubSpace/Zigbee lighting, Instant Pot/Camp Chef cooking monitors, IR/CEC TV control. Natural language → device commands.

**Phase 7** — Network Security: Firewalla API integration, Aruba wireless AP monitoring, auto-block suspicious traffic, isolate compromised IoT to quarantine VLAN.

**Phase 9** — Model Training: 12–18 months of engine data → ShareGPT export → LoRA fine-tuning on EVO-X2 (96GB GPU-allocatable). Bitemporal knowledge for backtesting. Project Forge dev data feeds directly into training.

---

## Hardware

| Role | Hardware | Memory | Purpose |
|------|----------|--------|---------|
| Primary brain | Current workstation | 64GB RAM, 16–24GB VRAM | FastAPI server, Ollama, all engines |
| Dev agent node | EliteBook 840 G2 (`192.168.111.28`) | 16GB | Initial Jarvis brain, Forge dev agents |
| Worker node | Mini PC (`192.168.111.27`) | 8GB | Parallel build agents |
| Compute node | GMKtec EVO-X2 | 128GB unified (96GB GPU) | Model training, heavy inference |
| Compute node | GMKtec EVO-X2 | 128GB unified (96GB GPU) | Redundancy, parallel engines |
| Tablets | Android tablets | Varies | Thin clients, cameras, BLE hubs |
| Network | Firewalla + Aruba APs | — | Security + wireless management |

All Ollama inference stays on-device. No data leaves the home network.

---

## Configuration

All configuration via environment variables. Copy `.env.example` to `.env` to get started — all keys are optional; engines skip missing sources and run with what's available.

```bash
# Core
OLLAMA_HOST=http://localhost:11434
JARVIS_MODEL=gemma3:27b
JARVIS_FALLBACK_MODEL=qwen2.5:0.5b

# Feature flags
JARVIS_SPECIALISTS_ENABLED=true
JARVIS_ENGINES_ENABLED=true

# Optional API keys (engines degrade gracefully without these)
FRED_API_KEY=...          # Federal Reserve economic data
GITHUB_TOKEN=...          # GitHub trending repos
CONGRESS_API_KEY=...      # Congress.gov legislation
AIRNOW_API_KEY=...        # AQI air quality data
EVENTBRITE_API_KEY=...    # Local events
NPS_API_KEY=...           # National Park Service
```

---

## Development

```bash
# Run all tests (no Ollama required — all LLM calls mocked)
pytest tests/ -v

# Run just the forge tests
pytest tests/test_forge_*.py -v

# Run with health check first
python start.py --check
```

### Project Structure

```
jarvis/
├── core.py               — LLM routing brain
├── config.py             — Single source of truth for all settings
├── memory_bus.py         — Routes all memory I/O across tiers
├── knowledge_lake.py     — High-level semantic knowledge facade
├── blackboard.py         — Cross-specialist pub/sub signaling
├── scheduler.py          — APScheduler job wiring
├── grading.py            — Decision grader (short + long term)
├── guideline_evolver.py  — Monthly LLM-driven guideline rewriting
├── context_engine.py     — Self-improving prompt context builder
├─�� ingestion.py          — IngestionBuffer (dedup → score → route)
├── engine_store.py       — Per-engine SQLite databases
├── adapters/             — Pluggable adapters (grocery, investor, weather, devteam, ...)
├── specialists/          — 6 autonomous background loops
├── engines/              — 7 knowledge accumulation engines
├── forge/                — Project Forge autonomous dev framework
│   ├── memory_store.py   — 7-layer introspection SQLite memory
│   ├── agent_base.py     — BaseDevAgent ABC
│   ├── critic.py         — Brain 1: quality evaluator
│   ├── orchestrator.py   — Task dispatcher
│   └── trainer.py        — Prompt improvement + LoRA export
├── memory_tiers/         — Working, Episodic, Semantic, Procedural, Attention
├── library/              — Research Librarian framework
└── integrations/         — Google Calendar/Sheets, external agents
```

---

## Security

- All user input is wrapped in `<user_input>` XML tags and treated as untrusted content
- Messages truncated to 2,000 chars before LLM injection
- Adapter calls isolated via `safe_run()` with 30s timeout and exception sandboxing
- No data leaves the local network — fully local inference via Ollama

---

*Built with [Ollama](https://ollama.ai) · [FastAPI](https://fastapi.tiangolo.com) · [ChromaDB](https://www.trychroma.com) · [APScheduler](https://apscheduler.readthedocs.io) · [Rich](https://rich.readthedocs.io)*
