# Jarvis — Local Household AI

> A self-improving personal AI that runs entirely on your hardware. Jarvis learns your household's patterns, manages specialists that watch finance, home, news, calendar, and groceries 24/7, and gets smarter every night while you sleep.

---

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Ollama** (must be running):
   ```bash
   ollama serve
   ollama pull gemma3:27b
   ollama pull qwen2.5:0.5b
   ```

3. **Configure** (optional — copy and edit):
   ```bash
   cp .env.example .env
   # Edit .env with your API keys, location, preferences
   ```

4. **Run Jarvis:**
   ```bash
   # Full server (API + specialists + engines)
   python start.py

   # CLI chat only
   python start.py --cli

   # Health check (verify Ollama, config, all 7 engines)
   python start.py --check
   ```

5. **Access:**
   - CLI: Interactive terminal chat
   - API: `http://localhost:8000/api/chat`
   - Dashboard: `http://localhost:8000/` (coming soon)

---

## What It Does

You talk to Jarvis in plain English. It routes your request to the right specialist, remembers context across conversations, and proactively surfaces what matters — without sending your data anywhere.

```
You: "What should we make for dinner this week given we're tight on budget?"
Jarvis: "Based on current inventory and your $85 remaining grocery budget, here are
        5 meals using what you already have — estimated cost $12 to restock..."
```

Everything runs locally via [Ollama](https://ollama.ai). No cloud required.

---

## Architecture

Jarvis is built around a **brain-inspired memory system** and **autonomous specialist loops**:

```
┌─────────────────────────────────────────────────────┐
│                     Jarvis Core                      │
│  Rich CLI ─── FastAPI server ─── LLM Router (Ollama) │
└────────────────────┬────────────────────────────────┘
                     │
         ┌───────────┴───────────┐
         │      Memory Bus        │
         │  (thalamus routing)    │
         └───┬───┬───┬───┬───────┘
             │   │   │   │
      ┌──────┘   │   │   └──────────┐
      ▼          ▼   ▼              ▼
  Working    Episodic  Semantic   Procedural
  Memory     Store     Store      Store
  (live)     (SQLite)  (ChromaDB  (SQLite)
                       + SQLite)
```

### Specialist Loops

Six autonomous background specialists run on cron schedules, share signals via a blackboard, and evolve their own guidelines based on graded outcomes:

| Specialist | Schedule | What It Watches |
|------------|----------|-----------------|
| **Grocery** | Every 4h | Prices, inventory, meal planning |
| **Finance** | Every 6h | Budget, spending patterns, alerts |
| **Calendar** | Every 2h | Schedule conflicts, upcoming events |
| **Home** | 8 AM daily | Maintenance, seasonal tasks |
| **News** | Every 3h | RSS feeds, relevant headlines |
| **Investor** | 9 AM + 4 PM weekdays | Market moves, portfolio signals |

### Self-Improvement Loop

Every night Jarvis runs:
1. **Consolidation** (3 AM) — Episodes → Semantic memory
2. **Short-term grading** (11 PM) — LLM grades recent decisions
3. **Long-term grading** (Sundays 2 AM) — Re-grades decisions 7–30 days later with hindsight
4. **Guideline evolution** (1st of month) — Rewrites specialist guidelines from graded patterns
5. **Context rebuild** (Mondays 5 AM) — Refreshes prompt context for each specialist

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI
python main.py

# Or start the API server
python server.py
```

**Requirements:** [Ollama](https://ollama.ai) running locally with `gemma3:27b` pulled.

```bash
ollama pull gemma3:27b
```

---

## API

```bash
# Chat
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what should I cook tonight?"}'

# List adapters
curl http://localhost:8000/api/adapters
```

---

## Adapters

| Adapter | Status | Capabilities |
|---------|--------|-------------|
| **grocery** | Live | meal_plan, shopping_list, inventory, price_check |
| **investor** | Live | daily_brief, market_check |
| **weather** | Live | current, forecast |
| **devteam** | Advanced | Multi-agent: architect, developer, QA, devops |
| **receipt_ingest** | Live | Parse and store receipts |
| **homeops_grocery** | Live | HomeOps grocery integration |
| **summerpuppy** | Live | SummerPuppy integration |
| **calendar** | Stub | today, week, add_event, reminders |
| **email** | Stub | unread, summary, send |
| **finance** | Stub | budget, spending, accounts |
| **home** | Stub | status, devices |
| **music** | Stub | play, pause, queue |
| **news** | Stub | headlines, summary |
| **sales_agent** | Stub | sales pipeline |

---

## Configuration

All configuration via environment variables — no config files to edit:

```bash
# Core
OLLAMA_HOST=http://localhost:11434   # Ollama endpoint
JARVIS_MODEL=gemma3:27b              # Primary model
JARVIS_FALLBACK_MODEL=qwen2.5:0.5b  # Fast fallback model

# Feature flags
JARVIS_SPECIALISTS_ENABLED=true     # Enable background specialist loops
JARVIS_PERSONALITY=true             # Enable personality layer
JARVIS_ENTITY_EXTRACTION=false      # Enable entity extraction

# Data paths (defaults to data/ in project root)
JARVIS_MEMORY_DB=data/memory.db
JARVIS_DECISIONS_DB=data/decisions.db
JARVIS_EPISODES_DB=data/episodes.db
JARVIS_CHROMADB_PATH=data/chromadb

# Integrations
JARVIS_NEWS_FEEDS=https://feeds.bbci.co.uk/news/rss.xml,https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml
JARVIS_DISCORD_WEBHOOK=https://discord.com/api/webhooks/...

# Integration paths (for external agent projects)
JARVIS_INTEGRATION_GROCERY=C:/AI-Lab/agents
JARVIS_INTEGRATION_INVESTOR=C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group
```

---

## Memory System

Jarvis uses a four-tier memory architecture inspired by human cognition:

| Tier | Store | Purpose | Retention |
|------|-------|---------|-----------|
| **Working** | In-memory | Current conversation context | Session |
| **Episodic** | SQLite | Full conversation episodes | 90 days |
| **Semantic** | ChromaDB + SQLite | Facts, prices, schedules, preferences | Long-term |
| **Procedural** | SQLite | How-to patterns, reinforced routines | Permanent |

The **Knowledge Lake** wraps semantic storage with time-decay confidence scoring — prices decay in 3 days, research in 90 days, preferences in 180 days.

---

## Shared Blackboard

Specialists communicate asynchronously via a shared blackboard. Example signals:

- `grocery → budget`: "Milk prices up 18% — consider store brand"
- `news → news_alert`: "Storm warning Tuesday — check outdoor plans"
- `investor → market_alert`: "Portfolio position down 3.2% — review threshold"
- `calendar → calendar`: "Conflict detected: dentist overlaps school pickup"

---

## Project Structure

```
jarvis/
├── core.py                  # LLM routing brain
├── config.py                # Single source of truth for all settings
├── memory_bus.py            # Memory thalamus — routes all memory I/O
├── knowledge_lake.py        # High-level semantic knowledge facade
├── blackboard.py            # Cross-specialist pub/sub signaling
├── consolidation.py         # Nightly episodic→semantic consolidation
├── household_state.py       # Household mode FSM (normal/travel/budget_tight/...)
├── grading.py               # Decision grader (short-term + long-term)
├── guideline_evolver.py     # Monthly LLM-driven guideline rewriting
├── context_engine.py        # Self-improving prompt context builder
├── scheduler.py             # APScheduler job wiring
├── adapters/                # Pluggable adapters (grocery, investor, weather, ...)
├── specialists/             # Autonomous background loops
│   ├── base.py              # BaseSpecialist with gather/analyze/improve
│   ├── grocery_spec.py
│   ├── finance_spec.py
│   ├── calendar_spec.py
│   ├── home_spec.py
│   ├── news_spec.py
│   └── investor_spec.py
├── memory_tiers/            # Working, Episodic, Semantic, Procedural, Attention
├── library/                 # Research Librarian framework + catalog
└── integrations/            # Google Calendar/Sheets, external agents
```

---

## Development

```bash
# Run all tests (no Ollama required — all LLM calls mocked)
pytest tests/ -v

# Run a specific test file
pytest tests/test_memory_bus.py -v

# Enable specialists in dev
JARVIS_SPECIALISTS_ENABLED=true python main.py
```

**526 tests, all passing.** All LLM calls are mocked in tests — you can run the full suite without Ollama.

---

## Adding a Specialist

1. Create `jarvis/specialists/myspec.py`:

```python
from __future__ import annotations
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist
from jarvis.memory_tiers.types import Insight

@register
class MySpec(BaseSpecialist):
    name = "my_specialist"
    domain = "my_domain"
    schedule = "0 */4 * * *"  # every 4 hours

    def gather(self) -> list[dict]:
        return self.lake.query_facts(domain=self.domain, limit=20)

    def analyze(self, gathered: list[dict]) -> list[Insight]:
        # call self.context_engine.inject(), then _ask_ollama
        ...

    def improve(self, insights: list[Insight]) -> None:
        # post to self.blackboard, flag stale data
        ...
```

2. Add seed guidelines: `data/library/my_domain/guidelines.md`
3. Add tests: `tests/test_myspec.py`

The specialist is automatically discovered, registered, and wired to the scheduler.

---

## Adding an Adapter

1. Create `jarvis/adapters/myadapter.py` inheriting `BaseAdapter`
2. Implement `run(capability, params) -> AdapterResult`
3. Add to `ALL_ADAPTERS` in `jarvis/adapters/__init__.py`

All adapters automatically get a 30s timeout, decision logging, and error isolation via `safe_run()`.

---

## Roadmap

- [x] Wave 1 — Four-tier memory + Knowledge Lake
- [x] Wave 2 — BaseSpecialist + GrocerySpec
- [x] Wave 3 — Consolidation Engine + Household State Machine
- [x] Wave 4 — Guideline Evolution + Context Engines + Library Foundation
- [x] Wave 5 — 5 Specialists + Shared Blackboard + Google Integration
- [ ] Wave 6 — Metacognitive Supervisor + Preference Learning + Memory Introspection API
- [ ] Track D — Fast-path keyword router + Service layer

---

## Security

- User input is wrapped in `<user_input>` XML tags and treated as content only
- Messages are truncated to 2000 chars before LLM injection
- All adapter calls go through `safe_run()` with timeout and exception isolation
- No data leaves your machine — fully local inference

---

*Built with [Ollama](https://ollama.ai), [FastAPI](https://fastapi.tiangolo.com), [ChromaDB](https://www.trychroma.com), [APScheduler](https://apscheduler.readthedocs.io), and [Rich](https://rich.readthedocs.io).*
