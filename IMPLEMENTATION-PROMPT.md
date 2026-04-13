# Jarvis Phase 2 — Implementation Prompt for Claude Code

You are implementing Phase 2 of Jarvis, a local personal assistant at `D:\AI-Lab\Jarvis`. Read the three architecture documents in the project root BEFORE writing any code:

1. `ARCHITECTURE-PHASE2.md` — Specialist loops & knowledge lake
2. `MEMORY-ARCHITECTURE.md` — Brain-inspired three-tier memory
3. `LIBRARY-OF-ALEXANDRIA.md` — Self-building KB, self-grading, guideline evolution

This is a phased implementation. Complete each wave fully (code + tests + integration) before starting the next. Run `pytest tests/ -v` after every wave to confirm nothing is broken.

---

## EXISTING CODEBASE — DO NOT BREAK THESE

```
jarvis/
├── core.py              # LLM router — routes user messages to adapters via Ollama
├── memory.py            # Conversation memory — JSON file, rolling 100 messages
├── agent_memory.py      # Decision audit log — SQLite (data/decisions.db), append-only
├── knowledge_base.py    # ChromaDB vector store — single collection, 6 categories
├── preferences.py       # User prefs — JSON file (data/preferences.json)
├── ambient.py           # Time/weather context injection
├── personality.py       # British butler style post-processing
├── brief.py             # Morning brief generator
├── scheduler.py         # APScheduler — daily brief, health check, workflow check
├── workflows.py         # Trigger→Action chains with approval gate
├── monitor.py           # Health monitoring + Discord alerts
├── notifier.py          # Discord webhook notifications
├── devices.py           # Device management
├── stt.py               # Speech-to-text (Whisper)
├── tts.py               # Text-to-speech (edge-tts)
├── adapters/
│   ├── base.py          # BaseAdapter + AdapterResult dataclass
│   ├── __init__.py      # ALL_ADAPTERS registry list
│   ├── grocery.py       # LIVE — wraps C:/AI-Lab/agents/grocery_agent.py
│   ├── investor.py      # LIVE — wraps AI_Agent_Investor orchestrator
│   ├── devteam/         # LIVE — Architect→Developer→QA pipeline
│   ├── weather.py       # OpenWeatherMap integration
│   ├── homeops_grocery.py
│   ├── receipt_ingest.py
│   ├── summerpuppy.py
│   └── stubs.py         # Calendar, Email, Finance, Home, Music, News, SalesAgent
main.py                  # Rich CLI
server.py                # FastAPI + WebSocket server
```

**Key patterns already established:**
- All LLM calls go through `_ask_ollama(prompt, model)` in `core.py`
- Adapters inherit `BaseAdapter`, implement `run(capability, params) -> AdapterResult`
- `safe_run()` wraps every adapter call with error handling + decision logging
- All decision logging goes through `jarvis.agent_memory.log_decision()`
- Lazy imports everywhere to avoid circular dependencies and heavy startup
- Tests mock Ollama with `@patch("jarvis.core._ask_ollama")`
- Tests use temp dirs for data files (never touch real data/)
- Security: user input is XML-escaped before prompt injection

**Environment:**
- Python 3.13+
- Ollama at `OLLAMA_HOST` (default `http://localhost:11434`)
- Router model: `JARVIS_MODEL` (default `gemma3:27b`)
- Fallback model: `JARVIS_FALLBACK_MODEL` (default `qwen2.5:0.5b`)
- Dependencies in requirements.txt (fastapi, chromadb, apscheduler, rich, etc.)

---

## WAVE 1: Memory Bus + Three-Tier Memory + Knowledge Lake Foundation

**Goal:** Replace the six siloed memory stores with a unified three-tier hierarchy accessed through a single MemoryBus. All existing functionality must keep working — core.py, adapters, server.py, scheduler.py all continue to function but now route through the bus.

### Step 1.1: Create `jarvis/memory_bus.py`

The central I/O interface for all memory. This is the thalamus — everything flows through it.

```python
class MemoryBus:
    """Unified I/O interface for all memory stores."""
    
    def __init__(self, data_dir: str = "data"):
        self.working = WorkingMemory()
        self.episodic = EpisodicStore(os.path.join(data_dir, "episodes.db"))
        self.semantic = SemanticStore(data_dir)  # wraps ChromaDB + SQLite
        self.procedural = ProceduralStore(os.path.join(data_dir, "procedures.db"))
        self.audit = agent_memory  # reuse existing module directly
        self._hooks: list[MemoryHook] = []
    
    def record_message(self, role, content, adapter=None) -> str:
        """Write to working memory + episodic store. Returns message ID."""
    
    def record_decision(self, agent, capability, **kwargs) -> str:
        """Write to audit log + link to current episode."""
    
    def recall(self, query: str, context: dict = None) -> MemoryRecall:
        """Search ALL tiers, return ranked results."""
    
    def context_for_prompt(self, user_message: str, token_budget: int = 2000) -> str:
        """Build the memory context block for LLM prompt injection."""
    
    def register_hook(self, hook: MemoryHook):
        """Register event listener for cross-store reactions."""
    
    def _emit(self, event: str, **kwargs):
        """Notify all hooks of a memory event."""
```

**MemoryHook protocol:**
```python
class MemoryHook(Protocol):
    def on_event(self, event: str, **kwargs) -> None: ...
```

**Singleton pattern:** Use a module-level `_bus: Optional[MemoryBus] = None` with a `get_bus()` function, same pattern as `_open()` in agent_memory.py. The bus must be lazy-initialized.

### Step 1.2: Create `jarvis/memory_tiers/` package

```
jarvis/memory_tiers/
├── __init__.py           # exports WorkingMemory, EpisodicStore, SemanticStore, ProceduralStore
├── working.py            # Tier 1: in-memory dict, current session only
├── episodic.py           # Tier 2: SQLite (episodes.db), full conversation episodes
├── semantic.py           # Tier 3: ChromaDB + knowledge_notes SQLite table
├── procedural.py         # Learned action patterns, compiled from repeated episodes
├── attention.py          # AttentionGate: relevance-weighted memory injection
└── types.py              # Shared dataclasses: MemoryRecall, KBEntry, Episode, etc.
```

**Tier 1 — WorkingMemory (working.py):**
- In-memory Python dict, not persisted
- Holds: last 20 messages of current conversation, current episode ID, active adapter context
- API: `add(role, text, adapter)`, `recent(n)`, `search(query)`, `current_episode_id`
- Must be thread-safe (use `threading.Lock`)

**Tier 2 — EpisodicStore (episodic.py):**
- SQLite database: `data/episodes.db`
- Tables: `episodes` (id, started_at, ended_at, summary, domain, satisfaction, consolidated)
- Tables: `episode_messages` (id, episode_id, role, content, timestamp, adapter, entities)
- Tables: `episode_decisions` (id, episode_id, decision_id)
- API: `start_episode() -> str`, `end_episode(id)`, `add_message(episode_id, ...)`, `link_decision(episode_id, decision_id)`, `search(query, limit)`, `get_unconsolidated(limit)`, `mark_consolidated(id)`, `prune(older_than_days, min_satisfaction)`
- Episode summaries generated by LLM (use FALLBACK_MODEL) when episode ends
- Search: full-text search on episode_messages.content + episode.summary

**Tier 3 — SemanticStore (semantic.py):**
- Dual storage: ChromaDB (vectors) + SQLite `data/semantic.db` (structured)
- Refactor existing `knowledge_base.py` — move ChromaDB logic here
- Add new SQLite tables from the architecture docs:

```sql
-- Central index
CREATE TABLE kb_index (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_agent TEXT NOT NULL,
    confidence REAL DEFAULT 0.8,
    storage TEXT NOT NULL,        -- 'sqlite' or 'chromadb'
    storage_ref TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT,
    superseded_by TEXT,
    tags TEXT DEFAULT ''
);

-- Zettelkasten links (A-MEM inspired)
CREATE TABLE knowledge_links (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relationship TEXT NOT NULL,   -- 'supports', 'contradicts', 'extends', 'caused_by', 'supersedes'
    strength REAL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    evidence TEXT
);

-- Provenance chain
CREATE TABLE provenance (
    id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_detail TEXT,
    model_used TEXT,
    prompt_hash TEXT,
    input_summary TEXT,
    confidence_at_event REAL,
    agent TEXT
);

-- Domain-specific structured tables
CREATE TABLE prices (id TEXT PRIMARY KEY, item_name TEXT NOT NULL, store TEXT, price REAL NOT NULL, unit TEXT DEFAULT 'each', observed_at TEXT NOT NULL);
CREATE TABLE schedules (id TEXT PRIMARY KEY, title TEXT NOT NULL, who TEXT, start_time TEXT NOT NULL, end_time TEXT, recurrence TEXT, location TEXT, source TEXT);
CREATE TABLE budgets (id TEXT PRIMARY KEY, category TEXT NOT NULL, period TEXT NOT NULL, budgeted REAL NOT NULL, spent REAL DEFAULT 0, notes TEXT);
CREATE TABLE inventory (id TEXT PRIMARY KEY, item_name TEXT NOT NULL, category TEXT, quantity REAL DEFAULT 1, unit TEXT DEFAULT 'each', expires_at TEXT, location TEXT);
CREATE TABLE maintenance (id TEXT PRIMARY KEY, item TEXT NOT NULL, last_done TEXT, next_due TEXT, interval_days INTEGER, notes TEXT, cost_estimate REAL);
CREATE TABLE contacts (id TEXT PRIMARY KEY, name TEXT NOT NULL, relation TEXT, phone TEXT, email TEXT, notes TEXT);
```

- API: `add_fact(domain, fact_type, content, **kwargs) -> str`, `search(query, n, domain, min_confidence)`, `query_facts(domain, fact_type, min_confidence)`, `get_provenance(fact_id)`, `add_link(source_id, target_id, relationship, evidence)`, `get_links(fact_id)`
- Lazy import chromadb (same pattern as existing knowledge_base.py)

**Tier 4 — ProceduralStore (procedural.py):**
- SQLite: `data/procedures.db`
- Table: `procedures` (id, trigger_pattern, trigger_embedding BLOB, action_sequence TEXT/JSON, confidence REAL, execution_count INTEGER, success_rate REAL, compiled_from TEXT, created_at, last_used)
- API: `match(user_message) -> Optional[Procedure]`, `add(trigger, action_sequence, ...)`, `reinforce(id)`, `decompile(id)` (when success_rate drops)
- For now: implement the schema and basic CRUD. Compilation logic comes in Wave 3.

**AttentionGate (attention.py):**
- `gate(query, recall, budget) -> str` — relevance-weighted filtering
- Scoring: 0.35 semantic_similarity + 0.20 recency + 0.15 frequency + 0.15 domain_alignment + 0.15 surprise_value
- For now: implement recency and domain_alignment scoring. Semantic similarity comes from ChromaDB search scores. Surprise and frequency can be stubs that return 0.5.

### Step 1.3: Wire MemoryBus into core.py

**Critical: backward compatibility.** The existing `memory.add()`, `memory.recent()`, and `agent_memory.log_decision()` calls in core.py must continue to work. The approach:

1. `core.py` imports and uses `memory_bus.get_bus()` instead of raw `memory` and `agent_memory`
2. `memory_bus.record_message()` writes to BOTH working memory AND episodic store
3. `memory_bus.record_decision()` writes to BOTH agent_memory AND links to episode
4. `_general_chat()` uses `bus.context_for_prompt()` instead of manually building context
5. The routing prompt in `_route_message()` gets KB context injection via `bus.context_for_prompt()`

**Keep the old modules importable** — other files (server.py, workflows.py, brief.py) still import them directly. Add deprecation comments pointing to the bus.

### Step 1.4: Create Knowledge Lake wrapper

```python
# jarvis/knowledge_lake.py
"""Unified API for the Knowledge Lake (semantic tier + structured tables)."""

class KnowledgeLake:
    """High-level API that specialists and adapters use to read/write knowledge."""
    
    def __init__(self):
        self._bus = get_bus()
    
    def store_fact(self, domain, fact_type, content, source_agent, confidence=0.8, 
                   tags=None, expires_at=None, structured_data=None) -> str:
        """Store a fact. Writes to semantic store + provenance. Returns fact ID."""
    
    def query_facts(self, domain=None, fact_type=None, min_confidence=0.5, 
                    limit=20) -> list[dict]:
        """Query structured facts from SQLite."""
    
    def search(self, query, n=10, domain=None) -> list[dict]:
        """Semantic search via ChromaDB."""
    
    def store_price(self, item_name, store, price, unit='each', source_agent='') -> str:
    def store_schedule(self, title, who, start_time, **kwargs) -> str:
    def store_budget(self, category, period, budgeted, spent=0) -> str:
    def store_inventory(self, item_name, category, quantity, **kwargs) -> str:
    def store_maintenance(self, item, **kwargs) -> str:
    
    def recent_by_domain(self, limit_per_domain=3) -> dict[str, list]:
        """Get recent facts grouped by domain — for prompt context injection."""
    
    def effective_confidence(self, fact_id) -> float:
        """Compute decayed confidence based on fact_type half-life."""
```

### Step 1.5: Tests for Wave 1

Create these test files:

- `tests/test_memory_bus.py` — Test the bus routes writes to correct tiers, recall searches all tiers, hooks fire on events
- `tests/test_working_memory.py` — Thread-safe add/search, 20-message limit, session isolation
- `tests/test_episodic_store.py` — Episode lifecycle (start/add/end/summarize), search, consolidation marking, pruning
- `tests/test_semantic_store.py` — kb_index CRUD, knowledge_links, provenance, structured tables (prices, schedules, etc.), ChromaDB integration (use `:memory:` client)
- `tests/test_knowledge_lake.py` — High-level API: store_fact, query_facts, search, effective_confidence with decay
- `tests/test_attention_gate.py` — Relevance scoring, token budget enforcement

**Testing patterns to follow:**
- Use `tmp_path` fixture for all SQLite databases
- Mock ChromaDB with `chromadb.Client()` (in-memory, no persist)
- Mock `_ask_ollama` for any LLM calls
- Existing tests must still pass — run full suite

### Step 1.6: Update requirements.txt

No new dependencies needed — chromadb, sentence-transformers, and sqlite3 (stdlib) are already available.

---

## WAVE 2: Specialist Loop Framework + GrocerySpec (First Specialist)

**Goal:** Build the BaseSpecialist framework and implement GrocerySpec as the proof-of-concept specialist running on a background schedule.

### Step 2.1: Create `jarvis/specialists/` package

```
jarvis/specialists/
├── __init__.py           # SPECIALIST_REGISTRY, start_all(), stop_all()
├── base.py               # BaseSpecialist with gather/analyze/improve loop
└── grocery_spec.py       # First real specialist
```

**BaseSpecialist (base.py):**

```python
class BaseSpecialist:
    """Background AI loop that owns a knowledge domain."""
    
    name: str               # e.g. "grocery_specialist"
    domain: str             # e.g. "grocery"  
    model: str              # Ollama model to use (default: FALLBACK_MODEL for speed)
    schedule: str           # cron expression
    
    def __init__(self):
        self._bus = None  # lazy init via get_bus()
        self._lake = None  # lazy init via KnowledgeLake()
    
    @property
    def bus(self) -> MemoryBus:
        if self._bus is None:
            from jarvis.memory_bus import get_bus
            self._bus = get_bus()
        return self._bus
    
    @property
    def lake(self) -> KnowledgeLake:
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake
    
    def run_cycle(self) -> CycleReport:
        """Full specialist loop: gather → analyze → write → improve."""
        report = CycleReport(specialist=self.name, started_at=now())
        try:
            raw_data = self.gather()
            report.gathered = len(raw_data)
            
            # Read cross-domain context from KB
            cross_domain_context = self.lake.recent_by_domain(limit_per_domain=3)
            
            insights = self.analyze(raw_data, cross_domain_context)
            report.insights = len(insights)
            
            for insight in insights:
                self.lake.store_fact(
                    domain=self.domain,
                    fact_type=insight.fact_type,
                    content=insight.content,
                    source_agent=self.name,
                    confidence=insight.confidence,
                    tags=insight.tags,
                )
            
            gaps = self.improve()
            report.gaps_identified = len(gaps)
            
        except Exception as exc:
            report.error = str(exc)
        
        report.ended_at = now()
        # Log to agent_memory
        agent_memory.log_decision(
            agent=self.name, capability="run_cycle",
            decision=f"Cycle complete: {report.gathered} gathered, {report.insights} insights",
            reasoning=str(report),
            outcome="success" if not report.error else "failure",
        )
        return report
    
    # Subclasses implement these three:
    def gather(self) -> list[dict]: ...
    def analyze(self, raw_data, cross_context) -> list[Insight]: ...
    def improve(self) -> list[str]: ...
```

**GrocerySpec (grocery_spec.py):**
- `domain = "grocery"`
- `schedule = "0 */4 * * *"` (every 4 hours)
- `gather()`: 
  - Read current inventory from KB (if any)
  - Read current prices from KB
  - Read preferences (city, budget, dietary, preferred stores)
  - Check calendar for upcoming events (if CalendarSpec has posted to KB)
  - Call existing grocery adapter for fresh data if KB data is stale
- `analyze()`:
  - Compare new prices with KB prices → flag significant changes
  - Check inventory against meal plan → identify items running low
  - Cross-reference with budget data from finance domain
  - Use LLM to generate insights: "chicken up 25%, suggest switching to pork this week"
- `improve()`:
  - Query own facts with low confidence → schedule re-research
  - Check which of its past suggestions were accepted (from preference_signals, if exists)
  - Return list of knowledge gaps

### Step 2.2: Wire specialists into scheduler.py

Add a `_run_specialist_cycle(name)` job function. In `start()`, register all specialists:

```python
for spec in SPECIALIST_REGISTRY:
    _scheduler.add_job(
        _run_specialist_cycle,
        trigger=CronTrigger.from_crontab(spec.schedule),
        args=[spec.name],
        id=f"specialist_{spec.name}",
        replace_existing=True,
    )
```

Add `JARVIS_SPECIALISTS_ENABLED` env var (default `false`) so specialists can be turned on explicitly.

### Step 2.3: Tests for Wave 2

- `tests/test_base_specialist.py` — Cycle lifecycle, error handling, decision logging
- `tests/test_grocery_spec.py` — Gather/analyze/improve with mocked data sources and LLM

---

## WAVE 3: Self-Grading + Consolidation Engine + Household State Machine

**Goal:** Close the feedback loops. Decisions get graded. Episodes get consolidated. Household state affects specialist behavior.

### Step 3.1: Decision Grading System

Create `jarvis/grading.py`:

```python
class DecisionGrader:
    """Grades decisions short-term (daily) and long-term (weekly)."""
    
    def grade_short_term(self, decision: dict) -> dict:
        """Was this decision immediately useful? Checks acceptance signals."""
    
    def grade_long_term(self, decision: dict) -> dict:
        """Did this decision lead to good outcomes over time?"""
    
    def run_short_term_batch(self) -> int:
        """Grade all ungraded decisions from the last 24h. Returns count."""
    
    def run_long_term_batch(self) -> int:
        """Re-grade decisions from 7-30 days ago. Returns count."""
```

Add SQLite table `decision_grades` to `data/decisions.db` (extend agent_memory.py with a new DDL block, same migration pattern):

```sql
CREATE TABLE IF NOT EXISTS decision_grades (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    short_term_grade TEXT,
    short_term_score REAL,
    short_term_reason TEXT,
    short_term_graded_at TEXT,
    long_term_grade TEXT,
    long_term_score REAL,
    long_term_reason TEXT,
    long_term_graded_at TEXT,
    grading_model TEXT,
    revised INTEGER DEFAULT 0
);
```

Add grading jobs to scheduler.py: short-term daily at 11 PM, long-term weekly on Sundays.

### Step 3.2: Consolidation Engine

Create `jarvis/consolidation.py`:

```python
class ConsolidationEngine:
    """Nightly 'sleep cycle': episodic → semantic memory."""
    
    def run(self) -> ConsolidationReport:
        """
        1. Get unconsolidated episodes
        2. For each: extract knowledge via LLM
        3. Merge into semantic store (reinforce existing or add new)
        4. Mark episodes consolidated
        5. Prune low-value old episodes
        """
    
    def _extract_knowledge(self, messages, decisions) -> list[Insight]:
        """LLM extracts generalizable knowledge from an episode."""
    
    def _merge_into_semantic(self, insight: Insight):
        """Check for existing similar knowledge. Reinforce or create new."""
```

Add to scheduler.py: runs at 3 AM (`id="memory_consolidation"`).

### Step 3.3: Household State Machine

Create `jarvis/household_state.py`:

```python
VALID_STATES = {"normal", "school_year", "summer", "holiday", "travel", 
                "sick_house", "guests", "crunch", "budget_tight"}

class HouseholdState:
    """Composite household state: one primary + zero or more modifiers."""
    
    primary: str = "normal"
    modifiers: set[str] = set()
    
    def current(self) -> HouseholdState: ...
    def transition(self, new_primary: str, reason: str): ...
    def add_modifier(self, modifier: str, reason: str): ...
    def remove_modifier(self, modifier: str, reason: str): ...
```

Persist state to `data/household_state.json`. Log all transitions to agent_memory.

Specialists read household state in their `analyze()` method and adjust behavior accordingly (e.g., GrocerySpec switches to budget mode when `budget_tight` is active).

### Step 3.4: Tests for Wave 3

- `tests/test_grading.py` — Short/long-term grading, batch processing
- `tests/test_consolidation.py` — Episode extraction, merge logic, pruning
- `tests/test_household_state.py` — Transitions, modifiers, persistence, logging

---

## WAVE 4: Guideline Evolution + Context Engines + Library Foundation

**Goal:** Specialists write and improve their own operating guidelines. Context engines provide rich prompt injection. Library catalog structure is laid down.

### Step 4.1: Guideline Evolver

Create `jarvis/guideline_evolver.py`:

```python
class GuidelineEvolver:
    """Reads decision grades, rewrites specialist operating guidelines."""
    
    def evolve(self, domain: str) -> GuidelineUpdate:
        """Monthly: analyze graded decisions → rewrite guidelines."""
    
    def _load_guidelines(self, domain: str) -> Guidelines: ...
    def _save_guidelines(self, domain: str, text: str, version: int): ...
    def _draft_corrective_guideline(self, pattern) -> str: ...
    def _draft_reinforcement_guideline(self, pattern) -> str: ...
```

Guidelines stored at `data/library/{domain}/guidelines.md`. Initial guidelines are hand-written seed files. The evolver reads grades, clusters failure/success patterns via LLM, and rewrites the guidelines. All changes logged with full provenance.

### Step 4.2: Context Engine

Create `jarvis/context_engine.py`:

```python
class ContextEngine:
    """Self-improving prompt context for a specialist."""
    
    def rebuild(self, domain: str) -> str:
        """Full rebuild from KB + historicals + grades + guidelines."""
    
    def patch(self, domain: str, section: str, update: str): ...
    
    def inject(self, domain: str, base_prompt: str, token_budget: int = 3000) -> str:
        """Inject context into a specialist's LLM prompt via AttentionGate."""
```

Context docs stored at `data/library/{domain}/context_engine.md`. Rebuilt weekly by scheduler.

### Step 4.3: Library Catalog Foundation

Create `jarvis/library/` package:

```
jarvis/library/
├── __init__.py
├── catalog.py            # SQLite catalog: library_catalog + research_queue tables
├── librarian_base.py     # BaseResearchLibrarian (survey/evaluate/catalog/curate)
└── grocery_librarian.py  # First real librarian
```

Create disk structure:
```
data/library/
├── catalog.db
├── grocery/
│   ├── guidelines.md     # seed file
│   ├── context_engine.md # generated
│   └── resources/
├── finance/
│   ├── guidelines.md
│   └── resources/
└── shared/
    └── cross_references.db
```

For now: implement catalog schema, BaseResearchLibrarian interface, and GroceryLibrarian with a basic `survey()` that checks USDA data or similar public APIs.

### Step 4.4: Tests for Wave 4

- `tests/test_guideline_evolver.py` — Guideline loading, evolution, version increment
- `tests/test_context_engine.py` — Rebuild, inject, token budgeting
- `tests/test_library_catalog.py` — Catalog CRUD, research queue

---

## WAVE 5: Additional Specialists + Cross-Domain Communication

**Goal:** Build out remaining specialists. Enable cross-specialist communication via the blackboard and knowledge lake.

### Step 5.1: Additional Specialists

Create in `jarvis/specialists/`:

- `finance_spec.py` — Budget tracking, spending patterns, savings tips. Reads from budget/spending tables in semantic store. 
- `calendar_spec.py` — Google Calendar API integration. Writes schedules to KB. Detects conflicts.
- `home_spec.py` — Maintenance tracking, seasonal task generation. Reads maintenance table.
- `news_spec.py` — RSS feed ingestion, relevant headline extraction.
- `investor_spec.py` — Enhanced version wrapping existing investor adapter + news cross-reference.

Each specialist:
- Inherits BaseSpecialist
- Implements gather/analyze/improve
- Reads household state
- Writes to the knowledge lake
- Has its own library wing in `data/library/{domain}/`

### Step 5.2: Shared Blackboard

Create `jarvis/blackboard.py`:

```python
class SharedBlackboard:
    """Real-time cross-specialist signals (events, alerts, requests)."""
    
    def post(self, agent, topic, content, urgency="normal") -> str: ...
    def read(self, topics=None, since=None, agents=None) -> list[dict]: ...
    def subscribe(self, agent, topics): ...
```

Storage: `data/blackboard.db` (SQLite). Entries expire after 7 days. The MemoryBus emits blackboard events via hooks so specialists can react to posts from other specialists.

### Step 5.3: Google Integration

Create `jarvis/integrations/google.py`:

```python
class GoogleSync:
    def sync_calendar(self) -> list[dict]: ...
    def sync_sheets(self, sheet_id, mapping) -> list[dict]: ...
```

OAuth2 credentials stored in `data/google_credentials.json`. Use `google-auth` and `google-api-python-client` packages. Add to requirements.txt.

### Step 5.4: Tests for Wave 5

- Test files for each new specialist (mock all external APIs)
- `tests/test_blackboard.py` — Post, read, subscribe, expiry
- `tests/test_google_sync.py` — Calendar/Sheets sync with mocked Google API

---

## WAVE 6: Advanced Features — Self-Improvement Loops

**Goal:** Implement the metacognitive supervisor, preference learning, procedural compilation, and memory introspection.

### Step 6.1: Metacognitive Supervisor

Create `jarvis/specialists/metacognitive.py`:

- Monitors all specialist cycle reports, decision grades, KB quality metrics
- Identifies underperforming specialists (low acceptance, high failure rate)
- Proposes prompt rewrites, schedule adjustments, model reassignments
- Generates weekly system health report
- Schedule: daily analysis, weekly report

### Step 6.2: Active Preference Learning

Create `jarvis/preference_learning.py`:

- New table `preference_signals` (suggestion_id, action, context, modification)
- New table `learned_preferences` (domain, rule, confidence, evidence_count, context_conditions)
- `PreferenceMiner` runs weekly: analyzes all signals, extracts patterns via LLM
- Learned preferences are injected into specialist context engines

### Step 6.3: Procedural Compilation

Extend `jarvis/memory_tiers/procedural.py`:

- `compile_from_episodes(episodes)` — LLM analyzes similar episodes, extracts common action sequence
- Wire into consolidation engine: during sleep cycle, detect routing patterns with 5+ repetitions
- Wire into core.py: before LLM routing, check procedural store for a match (confidence > 0.9, execution_count > 5)

### Step 6.4: Memory Introspection API

Create `jarvis/introspection.py`:

- `explain_recommendation(decision_id)` — trace through provenance
- `knowledge_audit(domain)` — confidence distributions, gaps, staleness
- `memory_diff(since)` — new/updated/retired knowledge since a date

Add to server.py:
- `GET /api/memory/audit` — knowledge audit
- `GET /api/memory/diff?since=ISO_DATE` — memory diff
- `GET /api/memory/explain/{decision_id}` — explain a recommendation

Add `memory_diff()` output to the daily brief in `brief.py`.

### Step 6.5: Tests for Wave 6

- `tests/test_metacognitive.py`
- `tests/test_preference_learning.py`
- `tests/test_procedural_compilation.py`
- `tests/test_introspection.py`

---

## GLOBAL RULES FOR ALL WAVES

### Coding Standards
- Python 3.13+ type hints everywhere (use `str | None` not `Optional[str]`)
- Docstrings on every public class and method
- `from __future__ import annotations` at top of every file
- Lazy imports for heavy dependencies (chromadb, apscheduler)
- All SQLite access through helper functions with `sqlite3.Row` row factory
- All SQL DDL in constants at module top (same pattern as agent_memory.py)
- Never use `print()` — use `logging.getLogger(__name__)`
- All timestamps: `datetime.now(timezone.utc).isoformat()`
- All IDs: `str(uuid.uuid4())`

### Safety
- User input is ALWAYS XML-escaped before LLM prompt injection (existing `_sanitize_for_prompt()`)
- Specialist loop errors NEVER crash the scheduler — wrap in try/except, log to agent_memory
- All self-modification (guideline rewrites, procedural compilation) requires the existing `JARVIS_AUTO_APPROVE_WORKFLOWS` gate or equivalent
- No specialist can modify `core.py`, `server.py`, or security-critical code

### Testing
- Every new module gets a corresponding test file
- Tests NEVER require Ollama running — all LLM calls mocked
- Tests NEVER touch `data/` — use `tmp_path` fixture
- ChromaDB tests use `chromadb.Client()` (in-memory)
- Run `pytest tests/ -v` after every wave — zero failures allowed
- Aim for at least one test per public method

### File Organization
- New packages: `jarvis/memory_tiers/`, `jarvis/specialists/`, `jarvis/library/`, `jarvis/integrations/`
- Data dirs: `data/library/`, `data/` (existing)
- All new SQLite databases in `data/` with env var overrides for testing
- Config env vars follow existing pattern: `JARVIS_` prefix, sane defaults

### Dependencies
- Prefer stdlib (sqlite3, json, uuid, datetime, threading, pathlib)
- ChromaDB already in requirements.txt — reuse
- APScheduler already in requirements.txt — reuse
- New dependencies ONLY when essential (google-auth for Wave 5)

### Commit Strategy
- One commit per step (1.1, 1.2, etc.)
- Commit message format: `feat(phase2): step X.Y — description`
- Run tests before every commit

---

## ARCHITECTURE DOCS TO READ

These three files in the project root contain the full design rationale, schemas, and diagrams. Read them in order before starting:

1. **ARCHITECTURE-PHASE2.md** — Knowledge Lake schema, specialist loop architecture, cross-specialist communication via KB, hardware scaling strategy, adapter changes
2. **MEMORY-ARCHITECTURE.md** — Three-tier hierarchy, consolidation engine, MemoryBus, Zettelkasten linking, attention gating, procedural memory, provenance, significance scoring, blackboard, introspection API
3. **LIBRARY-OF-ALEXANDRIA.md** — Research Librarian pattern, historical context engines, self-growing context engines, decision grading, guideline evolution, cross-wing research network

When in doubt about a design decision, refer back to these docs. They contain the full rationale.
