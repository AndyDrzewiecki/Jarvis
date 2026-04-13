# Jarvis Phase 2 — Wave 2 Implementation Prompt

You are continuing the Phase 2 implementation of Jarvis, a local personal assistant at `D:\AI-Lab\Jarvis`. The repo is at https://github.com/AndyDrzewiecki/Jarvis.

**Read these architecture docs BEFORE writing any code:**

1. `ARCHITECTURE-PHASE2.md` — Specialist loops, Knowledge Lake, 7-engine vision
2. `MEMORY-ARCHITECTURE.md` — Brain-inspired three-tier memory + 7-engine addendum (storage tiers, training export, bitemporal facts)
3. `LIBRARY-OF-ALEXANDRIA.md` — Research librarian pattern, all 7 engine wings

Run `pytest tests/ -v` after every major step to confirm nothing is broken.

---

## COMPLETED WORK — DO NOT REDO

**Wave 1 (committed):** Memory Bus + Three-Tier Memory + Knowledge Lake — 362 tests passing.

Files created in Wave 1:
- `jarvis/memory_bus.py` — MemoryBus singleton with record_message, record_decision, recall, context_for_prompt
- `jarvis/memory_tiers/` — WorkingMemory, EpisodicStore, SemanticStore, ProceduralStore, AttentionGate, types.py
- `jarvis/knowledge_lake.py` — KnowledgeLake wrapper with store_fact, query_facts, search, effective_confidence
- `jarvis/config.py` — Unified configuration (env vars + defaults, single source of truth)
- Tests for all of the above

**Track A (uncommitted — commit first):** The following changes are staged or modified but not yet committed. Commit them as a single commit before starting new work:
- `jarvis/config.py` — NEW: Centralized configuration module
- `jarvis/memory.py` — MODIFIED: SQLite conversation memory migration
- `jarvis/core.py` — MODIFIED: Adapter timeout wiring via config
- `tests/test_config.py` — NEW: Config tests
- `tests/test_memory.py` — NEW: Memory tests
- `tests/test_adapters.py` — MODIFIED
- `CLAUDE.md` — MODIFIED

**Important:** The architecture docs (ARCHITECTURE-PHASE2.md, MEMORY-ARCHITECTURE.md, LIBRARY-OF-ALEXANDRIA.md, docs/Jarvis-Phase2-Architecture.pdf) have also been modified locally but these are documentation updates — include them in the Track A commit.

**Step 0: Commit Track A**

```bash
git add jarvis/config.py tests/test_config.py tests/test_memory.py
git add jarvis/memory.py jarvis/core.py tests/test_adapters.py CLAUDE.md
git add ARCHITECTURE-PHASE2.md MEMORY-ARCHITECTURE.md LIBRARY-OF-ALEXANDRIA.md docs/Jarvis-Phase2-Architecture.pdf
git add data/preferences.json
git commit -m "feat(phase2): Track A — config.py, SQLite memory, adapter timeouts, arch docs update"
```

Run `pytest tests/ -v` to confirm everything passes before continuing.

---

## EXISTING CODEBASE PATTERNS — FOLLOW THESE

- All LLM calls go through `_ask_ollama(prompt, model)` in `core.py`
- Adapters inherit `BaseAdapter`, implement `run(capability, params) -> AdapterResult`
- `safe_run()` wraps every adapter call with error handling + decision logging
- All decision logging goes through `jarvis.agent_memory.log_decision()`
- Lazy imports everywhere to avoid circular dependencies and heavy startup
- Tests mock Ollama with `@patch("jarvis.core._ask_ollama")`
- Tests use `tmp_path` for data files (never touch real `data/`)
- Security: user input is XML-escaped before prompt injection
- All timestamps: `datetime.now(timezone.utc).isoformat()`
- All IDs: `str(uuid.uuid4())`
- Python 3.13+ type hints (`str | None` not `Optional[str]`)
- `from __future__ import annotations` at top of every file
- All SQL DDL in constants at module top (same pattern as agent_memory.py)
- Never use `print()` — use `logging.getLogger(__name__)`

---

## WAVE 2: Specialist Loop Framework + GrocerySpec

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
from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Insight:
    fact_type: str
    content: str
    confidence: float = 0.8
    tags: str = ""

@dataclass 
class CycleReport:
    specialist: str
    started_at: str = ""
    ended_at: str = ""
    gathered: int = 0
    insights: int = 0
    gaps_identified: int = 0
    error: str | None = None

class BaseSpecialist:
    """Background AI loop that owns a knowledge domain."""
    
    name: str               # e.g. "grocery_specialist"
    domain: str             # e.g. "grocery"  
    model: str              # Ollama model to use (default: FALLBACK_MODEL for speed)
    schedule: str           # cron expression
    
    def __init__(self):
        self._bus = None   # lazy init
        self._lake = None  # lazy init
    
    @property
    def bus(self):
        if self._bus is None:
            from jarvis.memory_bus import get_bus
            self._bus = get_bus()
        return self._bus
    
    @property
    def lake(self):
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake
    
    def run_cycle(self) -> CycleReport:
        """Full specialist loop: gather -> analyze -> write -> improve."""
        report = CycleReport(specialist=self.name, started_at=_now())
        try:
            raw_data = self.gather()
            report.gathered = len(raw_data)
            
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
            logger.exception("Specialist %s cycle failed", self.name)
            report.error = str(exc)
        
        report.ended_at = _now()
        from jarvis import agent_memory
        agent_memory.log_decision(
            agent=self.name, capability="run_cycle",
            decision=f"Cycle complete: {report.gathered} gathered, {report.insights} insights",
            reasoning=str(report),
            outcome="success" if not report.error else "failure",
        )
        return report
    
    # Subclasses implement these three:
    def gather(self) -> list[dict]:
        raise NotImplementedError
    
    def analyze(self, raw_data: list[dict], cross_context: dict) -> list[Insight]:
        raise NotImplementedError
    
    def improve(self) -> list[str]:
        raise NotImplementedError
```

**GrocerySpec (grocery_spec.py):**
- `name = "grocery_specialist"`, `domain = "grocery"`, `schedule = "0 */4 * * *"` (every 4 hours)
- `model` defaults to `config.FALLBACK_MODEL`
- `gather()`: Read current inventory, prices, and preferences from KB. Check calendar data in KB if available. Call existing grocery adapter for fresh data if KB data is stale (>24h).
- `analyze()`: Compare new vs. KB prices, flag significant changes (>15%). Check inventory against meal plan. Cross-reference budget data. Use LLM (via `_ask_ollama`) to generate insights like "chicken up 25%, suggest switching to pork this week."
- `improve()`: Query own facts with low confidence (<0.5), schedule re-research. Check which past suggestions were accepted. Return list of knowledge gaps.

**`__init__.py` registry:**

```python
from __future__ import annotations

SPECIALIST_REGISTRY: list = []  # populated at import time

def register(spec_class):
    """Decorator to register a specialist class."""
    SPECIALIST_REGISTRY.append(spec_class)
    return spec_class

def start_all():
    """Instantiate and return all registered specialists."""
    return [cls() for cls in SPECIALIST_REGISTRY]

def stop_all():
    """Cleanup hook for shutdown."""
    pass
```

Use the `@register` decorator on GrocerySpec.

### Step 2.2: Wire specialists into scheduler.py

Add a `_run_specialist_cycle(name)` job function to scheduler.py. In the existing `start()` function, if `config.SPECIALISTS_ENABLED` is True, register all specialists from SPECIALIST_REGISTRY:

```python
if config.SPECIALISTS_ENABLED:
    from jarvis.specialists import SPECIALIST_REGISTRY, start_all
    _specialists = start_all()
    for spec in _specialists:
        _scheduler.add_job(
            _run_specialist_cycle,
            trigger=CronTrigger.from_crontab(spec.schedule),
            args=[spec.name],
            id=f"specialist_{spec.name}",
            replace_existing=True,
        )
```

The `_run_specialist_cycle` function:
1. Finds the specialist instance by name
2. Calls `spec.run_cycle()`
3. Logs the CycleReport
4. Wraps everything in try/except — specialist errors must NEVER crash the scheduler

### Step 2.3: Tests for Wave 2

Create these test files:
- `tests/test_base_specialist.py` — Test the full cycle lifecycle with a mock subclass. Test error handling (gather throws, analyze throws). Test that decision logging is called. Test lazy bus/lake initialization.
- `tests/test_grocery_spec.py` — Test gather/analyze/improve with mocked KnowledgeLake data and mocked `_ask_ollama`. Test that insights are stored to the lake. Test the stale data detection (>24h).

**Testing patterns:**
- Use `tmp_path` fixture for all databases
- Mock `_ask_ollama` for any LLM calls
- Mock KnowledgeLake methods to return controlled test data
- All existing tests must still pass

### Step 2.4: Commit Wave 2

```bash
git add jarvis/specialists/ tests/test_base_specialist.py tests/test_grocery_spec.py
git add jarvis/scheduler.py  # modified
git commit -m "feat(phase2): Wave 2 — BaseSpecialist framework + GrocerySpec"
```

---

## TRACK C: Decision Grading Foundation

**Goal:** Add the decision_grades table and short-term grading job. This is a prerequisite for Wave 3's full grading + consolidation system but can be built independently now.

### Step C.1: Extend agent_memory.py

Add the `decision_grades` table DDL to `agent_memory.py` (same migration pattern — CREATE TABLE IF NOT EXISTS at module init):

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

Add helper functions to agent_memory.py:
- `save_grade(decision_id, short_term_grade, short_term_score, short_term_reason, model)` — insert or update
- `get_ungraded_decisions(since_hours=24) -> list[dict]` — decisions without a grade row
- `get_grade(decision_id) -> dict | None` — retrieve grade for a decision

### Step C.2: Create `jarvis/grading.py`

```python
class DecisionGrader:
    """Grades decisions using LLM analysis of outcomes."""
    
    def grade_short_term(self, decision: dict) -> dict:
        """Was this decision immediately useful? Checks acceptance signals."""
        # Use FALLBACK_MODEL to analyze decision + outcome
        # Return {"grade": "good"|"neutral"|"poor", "score": 0.0-1.0, "reason": str}
    
    def run_short_term_batch(self) -> int:
        """Grade all ungraded decisions from the last 24h. Returns count graded."""
```

Wire into scheduler.py: add a daily job at 11 PM local (`id="short_term_grading"`), gated by `config.SPECIALISTS_ENABLED`.

### Step C.3: Tests for Track C

- `tests/test_grading.py` — Test grade_short_term with mocked LLM. Test run_short_term_batch with seeded decisions. Test the save_grade/get_grade helpers.

### Step C.4: Commit Track C

```bash
git add jarvis/agent_memory.py jarvis/grading.py tests/test_grading.py jarvis/scheduler.py
git commit -m "feat(phase2): Track C — decision_grades table + short-term grader"
```

---

## FINAL CHECKS

After all work is complete:

1. Run `pytest tests/ -v` — ALL tests must pass, zero failures
2. Run `python -c "from jarvis.specialists.base import BaseSpecialist; print('OK')"` — import check
3. Run `python -c "from jarvis.grading import DecisionGrader; print('OK')"` — import check
4. Push to GitHub: `git push origin main`

---

## GLOBAL RULES

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
- User input is ALWAYS XML-escaped before LLM prompt injection
- Specialist loop errors NEVER crash the scheduler — wrap in try/except, log to agent_memory
- No specialist can modify core.py, server.py, or security-critical code

### Testing
- Every new module gets a corresponding test file
- Tests NEVER require Ollama running — all LLM calls mocked
- Tests NEVER touch `data/` — use `tmp_path` fixture
- ChromaDB tests use `chromadb.Client()` (in-memory)
- Run `pytest tests/ -v` after every step — zero failures allowed
- Aim for at least one test per public method

### Commit Strategy
- One commit per step section (Wave 2 as one commit, Track C as one commit)
- Commit message format: `feat(phase2): description`
- Run tests before every commit
