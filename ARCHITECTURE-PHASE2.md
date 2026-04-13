# Jarvis Phase 2 — Specialist Loops & Shared Knowledge Architecture

**Author:** Andy + Claude | **Date:** 2026-04-13 | **Status:** Design

---

## Vision

Jarvis evolves from a request-response router into a **living household intelligence system**. Specialist AI agents run continuously in the background, each owning a domain (grocery, finance, home, kids, etc.), writing discoveries to a shared local knowledge base. Every specialist can read what the others know. When Andy asks Jarvis a question, the answer draws from an always-current, cross-domain KB — not just a single adapter's output.

---

## What Exists Today (Phase 1)

| Component | Status | Notes |
|-----------|--------|-------|
| LLM Router (core.py) | Live | gemma3:27b via Ollama, routes to adapters |
| ChromaDB KB (knowledge_base.py) | Built, underused | Single collection, 6 categories, semantic search |
| APScheduler (scheduler.py) | Live | Daily brief, health check, workflow check |
| Workflow Engine (workflows.py) | Live | Trigger→Action chains with approval gate |
| Decision Audit (agent_memory.py) | Live | 478 entries in SQLite |
| Conversation Memory (memory.py) | Live | Rolling 100 messages, JSON |
| Adapters | 14 total | 2 live (grocery, investor), 1 advanced (devteam), rest stubs |

---

## Phase 2 Architecture

### Core Concept: The Knowledge Lake

Replace the current flat ChromaDB collection with a structured **Knowledge Lake** — a local SQLite database (for structured facts) paired with ChromaDB (for semantic search over unstructured content). Every specialist writes to both stores.

```
┌─────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE LAKE                          │
│                                                             │
│  ┌──────────────────────┐  ┌─────────────────────────────┐  │
│  │   facts.db (SQLite)  │  │  chromadb/ (vector store)   │  │
│  │                      │  │                             │  │
│  │  Structured facts:   │  │  Unstructured knowledge:    │  │
│  │  - prices            │  │  - research summaries       │  │
│  │  - schedules         │  │  - recipe notes             │  │
│  │  - budgets           │  │  - how-to guides            │  │
│  │  - contacts          │  │  - conversation insights    │  │
│  │  - inventory         │  │  - news analysis            │  │
│  │  - maintenance logs  │  │  - investment memos         │  │
│  └──────────────────────┘  └─────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              kb_index (metadata table)               │   │
│  │  id | domain | source_agent | confidence | fresh_at  │   │
│  │  Every fact and doc gets a row here for cross-query  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Why dual storage?**
- SQLite for fast, exact lookups ("what's my grocery budget?", "when is soccer practice?")
- ChromaDB for fuzzy, semantic queries ("what do we know about saving money on groceries?")
- The `kb_index` table bridges both — every piece of knowledge gets a metadata row regardless of where the payload lives

### Knowledge Lake Schema (SQLite: `data/facts.db`)

```sql
-- Central index for ALL knowledge items (structured + unstructured)
CREATE TABLE kb_index (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,       -- grocery, finance, kids, home, health, ...
    fact_type       TEXT NOT NULL,       -- price, schedule, budget, note, research, ...
    summary         TEXT NOT NULL,       -- one-line human summary
    source_agent    TEXT NOT NULL,       -- which specialist wrote this
    confidence      REAL DEFAULT 0.8,   -- 0.0-1.0, decays over time
    storage         TEXT NOT NULL,       -- 'sqlite' or 'chromadb'
    storage_ref     TEXT,               -- table+id for sqlite, chromadb doc id
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    expires_at      TEXT,               -- optional TTL (prices expire fast, recipes don't)
    superseded_by   TEXT,               -- id of newer version (never delete, supersede)
    tags            TEXT DEFAULT ''      -- comma-separated for fast filtering
);

-- Domain-specific structured tables
CREATE TABLE prices (
    id          TEXT PRIMARY KEY,       -- matches kb_index.id
    item_name   TEXT NOT NULL,
    store       TEXT,
    price       REAL NOT NULL,
    unit        TEXT DEFAULT 'each',
    observed_at TEXT NOT NULL
);

CREATE TABLE schedules (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    who         TEXT,                   -- family member
    start_time  TEXT NOT NULL,
    end_time    TEXT,
    recurrence  TEXT,                   -- rrule or 'once'
    location    TEXT,
    source      TEXT                    -- 'google_calendar', 'manual', etc.
);

CREATE TABLE budgets (
    id          TEXT PRIMARY KEY,
    category    TEXT NOT NULL,          -- grocery, utilities, fun, ...
    period      TEXT NOT NULL,          -- '2026-04' (monthly)
    budgeted    REAL NOT NULL,
    spent       REAL DEFAULT 0,
    notes       TEXT
);

CREATE TABLE inventory (
    id          TEXT PRIMARY KEY,
    item_name   TEXT NOT NULL,
    category    TEXT,                   -- pantry, fridge, freezer, cleaning, ...
    quantity    REAL DEFAULT 1,
    unit        TEXT DEFAULT 'each',
    expires_at  TEXT,
    location    TEXT                    -- kitchen, garage, basement, ...
);

CREATE TABLE maintenance (
    id              TEXT PRIMARY KEY,
    item            TEXT NOT NULL,      -- 'furnace filter', 'lawn mower oil', ...
    last_done       TEXT,
    next_due        TEXT,
    interval_days   INTEGER,
    notes           TEXT,
    cost_estimate   REAL
);

CREATE TABLE contacts (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    relation    TEXT,                   -- 'plumber', 'pediatrician', 'coach', ...
    phone       TEXT,
    email       TEXT,
    notes       TEXT
);
```

### Specialist Loop Architecture

Each specialist is a class that inherits from `BaseSpecialist` and implements three methods:

```python
class BaseSpecialist:
    """Background AI loop that owns a knowledge domain."""

    name: str               # e.g. "grocery_specialist"
    domain: str             # e.g. "grocery"
    model: str              # Ollama model to use for reasoning
    schedule: str           # cron expression, e.g. "0 */4 * * *" (every 4 hours)

    def gather(self) -> list[dict]:
        """Pull raw data from sources (APIs, files, Google, scraping)."""
        ...

    def analyze(self, raw_data: list[dict]) -> list[KBEntry]:
        """Use LLM to extract insights, compare with existing KB, find gaps."""
        ...

    def improve(self) -> list[str]:
        """Self-critique: what's stale? what's missing? what should I research next?"""
        ...
```

**The loop cycle (runs on schedule via APScheduler):**

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────┐
│  GATHER  │────▶│ ANALYZE  │────▶│ WRITE TO KB  │────▶│  IMPROVE  │
│          │     │          │     │              │     │           │
│ Pull new │     │ LLM rea- │     │ Insert/update│     │ Identify  │
│ data from│     │ sons over│     │ facts.db +   │     │ gaps and  │
│ sources  │     │ raw data │     │ chromadb     │     │ schedule  │
│          │     │ + KB ctx │     │              │     │ follow-up │
└──────────┘     └──────────┘     └──────────────┘     └───────────┘
                      │
                      ▼
              ┌──────────────┐
              │ READ FROM KB │
              │              │
              │ Cross-domain │
              │ context from │
              │ other specs  │
              └──────────────┘
```

### Planned Specialists

| Specialist | Domain | Schedule | Data Sources | Key Outputs |
|-----------|--------|----------|-------------|-------------|
| **GrocerySpec** | grocery | Every 4h | Store APIs, receipt scans, inventory | Prices, deals, meal suggestions, restock alerts |
| **FinanceSpec** | finance | Daily | Bank feeds (API), budgets table | Spending patterns, budget warnings, savings tips |
| **CalendarSpec** | kids, family | Every 2h | Google Calendar API | Schedule conflicts, upcoming events, reminders |
| **HomeSpec** | home | Daily | Maintenance table, weather API | Maintenance due, seasonal tasks, contractor recs |
| **NewsSpec** | news | Every 6h | RSS feeds, news APIs | Relevant headlines, market-moving news for investor |
| **InvestorSpec** | investing | Every 4h | Existing investor adapter, NewsSpec KB | Portfolio insights cross-referenced with news |
| **HealthSpec** | health | Daily | Manual input, schedules | Appointment reminders, med refills, wellness tips |
| **ResearchSpec** | research | On-demand + daily | Web search, existing KB gaps | Deep dives on topics other specialists flag |

### Cross-Specialist Communication

Specialists don't talk directly — they communicate through the KB. This is intentional:

1. **GrocerySpec** writes that chicken breast is on sale at Aldi for $1.99/lb
2. **FinanceSpec** reads this and updates the projected grocery spend for the month
3. **CalendarSpec** sees a birthday party on Saturday
4. **GrocerySpec** reads this and suggests adding cake ingredients to the shopping list

The `kb_index` table makes this possible — any specialist can query:
```sql
SELECT * FROM kb_index
WHERE domain IN ('grocery', 'finance')
AND updated_at > datetime('now', '-24 hours')
AND confidence > 0.5
ORDER BY updated_at DESC;
```

### Google Integration Layer

New module: `jarvis/integrations/google.py`

```python
class GoogleSync:
    """Pull data from Google ecosystem into the Knowledge Lake."""

    def sync_calendar(self) -> list[dict]:
        """Google Calendar API → schedules table."""

    def sync_sheets(self, sheet_id: str, mapping: dict) -> list[dict]:
        """Google Sheets → any structured table (budgets, inventory, etc.)."""

    def sync_drive_docs(self, folder_id: str) -> list[dict]:
        """Google Drive documents → ChromaDB for semantic search."""
```

**Auth:** OAuth2 with offline refresh tokens stored in `data/google_credentials.json`. Runs locally — tokens never leave the machine.

### Confidence Decay & Freshness

Knowledge isn't static. A price from 3 days ago is less trustworthy than one from today.

```python
def effective_confidence(entry: KBEntry) -> float:
    """Confidence decays based on fact_type half-life."""
    half_lives = {
        "price": 3,        # days — prices change fast
        "schedule": 7,     # weekly recurrence is stable-ish
        "budget": 30,      # monthly budgets are set
        "research": 90,    # research stays relevant longer
        "note": 180,       # personal notes decay slowly
    }
    age_days = (now - entry.updated_at).days
    half_life = half_lives.get(entry.fact_type, 30)
    decay = 0.5 ** (age_days / half_life)
    return entry.confidence * decay
```

When a specialist runs its `improve()` phase, it queries for low-confidence items in its domain and schedules re-research.

### Hardware Strategy: Multi-Node Scaling

With GMKtec EVO-X2 nodes (128GB unified memory, 96GB GPU-allocatable each):

```
Phase 2a: Single Node (current machine)
  └── Ollama serves all models (gemma3:27b router + specialist models)
  └── All specialists share one Ollama instance
  └── Stagger schedules to avoid GPU contention

Phase 2b: First EVO-X2 Node
  └── Dedicated to Jarvis specialists (heavier models: 70B for analysis)
  └── Current machine becomes the router + UI server
  └── Ollama cluster mode or load balancer

Phase 2c: Multi-Node Lab
  └── Node 1: Jarvis router + lightweight specialists
  └── Node 2: Heavy specialists (investor, research) + PraxisForma
  └── Node 3: DevTeam agent + overflow
  └── Shared KB via network SQLite (litestream) or PostgreSQL
```

**Model allocation per EVO-X2 (96GB VRAM):**
- 1x 70B model (Q4 quant) ≈ 40GB → heavy reasoning
- 1x 27B model ≈ 16GB → routing/fast tasks
- 1x 7-13B model ≈ 8GB → entity extraction, summarization
- Headroom for context windows and concurrent requests

### File Structure (New/Modified)

```
jarvis/
├── knowledge_lake/
│   ├── __init__.py          # KnowledgeLake class (unified API)
│   ├── facts_db.py          # SQLite structured store
│   ├── vector_store.py      # ChromaDB wrapper (refactored from knowledge_base.py)
│   ├── index.py             # kb_index manager
│   └── decay.py             # Confidence decay calculations
│
├── specialists/
│   ├── __init__.py          # SPECIALIST_REGISTRY, start_all(), stop_all()
│   ├── base.py              # BaseSpecialist with gather/analyze/improve loop
│   ├── grocery_spec.py
│   ├── finance_spec.py
│   ├── calendar_spec.py
│   ├── home_spec.py
│   ├── news_spec.py
│   ├── investor_spec.py
│   ├── health_spec.py
│   └── research_spec.py
│
├── integrations/
│   ├── __init__.py
│   ├── google.py            # Google Calendar/Sheets/Drive sync
│   └── rss.py               # RSS feed ingestion
│
├── adapters/                # Existing — adapters now READ from KB
│   ├── grocery.py           # Enhanced: checks KB before calling external agent
│   └── ...
│
├── scheduler.py             # Enhanced: registers specialist loops
├── core.py                  # Enhanced: injects KB context into routing prompt
└── knowledge_base.py        # Deprecated → replaced by knowledge_lake/
```

### How Adapters Change

Adapters become **thin read layers** over the Knowledge Lake. Instead of calling external tools every time:

```python
# BEFORE (Phase 1): Every question hits the external grocery agent
class GroceryAdapter(BaseAdapter):
    def run(self, capability, params):
        grocery_agent = _import_grocery()
        return grocery_agent.generate_meal_plan(...)

# AFTER (Phase 2): Check KB first, fall back to external only if stale
class GroceryAdapter(BaseAdapter):
    def run(self, capability, params):
        kb = KnowledgeLake()

        if capability == "meal_plan":
            # Check if we already have a fresh meal plan
            existing = kb.query_facts(domain="grocery", fact_type="meal_plan",
                                       min_confidence=0.6)
            if existing:
                return AdapterResult(success=True, text=existing[0].summary,
                                     data=existing[0].payload)

            # Nothing fresh — generate and store
            grocery_agent = _import_grocery()
            plan = grocery_agent.generate_meal_plan(...)
            kb.store_fact(domain="grocery", fact_type="meal_plan",
                         summary="Weekly meal plan", payload=plan,
                         source_agent="grocery_adapter")
            return AdapterResult(success=True, text=format_plan(plan), data=plan)
```

### Router Enhancement

The routing prompt in `core.py` gets KB context injection:

```python
def _build_routing_prompt(user_message: str) -> str:
    kb = KnowledgeLake()

    # Get recent cross-domain context
    recent_facts = kb.recent_by_domain(limit_per_domain=3)
    kb_summary = format_kb_context(recent_facts)

    return f"""
    You are Jarvis, a household AI assistant.

    Current knowledge state:
    {kb_summary}

    Available adapters:
    {adapter_registry_json}

    Route the following user message...
    """
```

This means Jarvis's routing decisions are informed by what the specialists have discovered, making the whole system smarter over time.

---

## Implementation Priority

### Wave 1: Foundation (1-2 weeks)
1. Build `knowledge_lake/` module (facts.db schema + ChromaDB integration)
2. Build `BaseSpecialist` class with the gather/analyze/improve loop
3. Wire specialists into `scheduler.py`
4. Build `GrocerySpec` as the first real specialist (it has the most existing infrastructure)

### Wave 2: Google + Cross-Domain (2-3 weeks)
5. Google Calendar integration → `CalendarSpec`
6. `FinanceSpec` with budget tracking
7. KB context injection into router (core.py enhancement)
8. Cross-specialist communication via KB queries

### Wave 3: Intelligence (2-3 weeks)
9. Confidence decay system
10. `improve()` loop — specialists self-identify knowledge gaps
11. `ResearchSpec` — fills gaps flagged by other specialists
12. `HomeSpec` + `NewsSpec`

### Wave 4: Multi-Node (when EVO-X2 arrives)
13. Ollama load balancing across nodes
14. KB replication (litestream or shared PostgreSQL)
15. Heavier specialist models (70B+)
16. `InvestorSpec` enhanced with deep analysis

---

## Open Questions

1. **Google Auth flow** — should this be a one-time CLI OAuth dance, or should the FastAPI server handle it with a callback URL?
2. **KB backup strategy** — litestream for continuous SQLite replication to a backup location?
3. **Specialist model selection** — should each specialist use the same model, or should heavy-reasoning specialists (investor, research) get bigger models?
4. **Family member profiles** — should the KB have a `family_members` table so specialists can personalize (e.g., "Emma has soccer on Tuesdays")?
5. **PraxisForma integration** — how does Jarvis interact with PraxisForma? Shared KB? API calls? Same Ollama instance?
