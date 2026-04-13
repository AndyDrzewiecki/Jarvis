# Jarvis Architecture Review & Rearchitecture Plan

**Date:** April 13, 2026  
**Reviewer:** Claude (Cowork)  
**Scope:** Full codebase review of D:\AI-Lab\Jarvis — Sprint 5 state

---

## 1. What You've Built (Current State Summary)

Jarvis is a local-first personal assistant that routes natural language to specialized adapters via an Ollama LLM (gemma3:27b). It's impressively far along for what appears to be ~5 sprints of work.

**Core architecture:** FastAPI server + Rich CLI → LLM Router (core.py) → Adapter Layer → External Systems

**What's working well:**

- **BaseAdapter contract** is clean — `safe_run()` wrapping all calls with error isolation and audit logging is excellent defensive design.
- **Agent decision memory** (SQLite) provides a real audit trail with linked message IDs threading routing decisions back to conversation entries. This is rare in hobby projects and shows architectural maturity.
- **14 adapters registered**, with 6 live (grocery, investor, homeops_grocery, summerpuppy, devteam, receipt_ingest, weather, sales_agent) and 6 stubs.
- **Test suite:** 25 test files, ~3,500 lines, all LLM calls mocked. Solid coverage.
- **Multi-adapter synthesis** — the router can fan out to multiple adapters and synthesize results. Not trivial.
- **Full vertical stack:** CLI, web dashboard, FastAPI API, SSE streaming, WebSocket push, TTS/STT, Android client (Kotlin/Compose), OTA updates, device registry with profile-based context injection.
- **Background automation:** scheduler (APScheduler), health monitor, workflow engine with approval gates.
- **ChromaDB knowledge base** with semantic search — the notebook feature.
- **Personality layer** — JARVIS-style rewrite using the fallback model. Fun and functional.
- **Security hardening** is above average: prompt injection guards, XML-tag isolation of user input, capability whitelist validation, CORS restrictions, artifact promotion whitelist.

---

## 2. Honest Problems (Architecture Debt)

### 2.1 — The Monolith Is Becoming Load-Bearing

Everything runs in a single FastAPI process: routing, adapter execution, scheduling, health monitoring, workflow evaluation, TTS synthesis, STT transcription, ChromaDB queries. This is fine at hobby scale but creates real issues:

- **A slow adapter blocks the event loop.** `run_in_executor` is used in a few places but not consistently — the sync `chat()` endpoint blocks directly.
- **APScheduler in-process** means if the server crashes, all scheduled jobs stop. No resilience.
- **ChromaDB + sentence-transformers loaded in the same process** as the web server — that's 500MB+ of RAM just for the knowledge base embeddings, competing with Ollama connections.

### 2.2 — Memory System is Fragile

- `memory.py` reads/writes the entire JSON array on every single message (`_load()` + `_save()`). At 100 messages this is fine; it will not scale to multi-device concurrent access.
- `agent_memory.py` (SQLite) is better but opens/closes a new connection on every call rather than using a connection pool or context manager pattern.
- Conversation memory and agent decision memory are separate systems with no shared transaction boundary — you can have a conversation entry without a corresponding routing decision if the process crashes between them.

### 2.3 — Adapter Coupling to Filesystem Paths

Multiple adapters use hardcoded `sys.path.insert(0, "C:/AI-Lab/agents")` to import external code. This is brittle:

- Breaks on any machine that isn't your ZBook
- Makes testing without the real filesystem impossible (you've worked around this with mocking, but it's fragile)
- The SalesAgentAdapter modifies `sys.path` in multiple methods without cleanup

### 2.4 — No Configuration Layer

Configuration is scattered across environment variables, `data/preferences.json`, hardcoded paths, and class-level constants. There's no single source of truth for "where does X come from." The `preferences.py` and env vars overlap (e.g., personality can be controlled by either).

### 2.5 — The Router is a Single Point of Fragility

The entire system depends on one LLM call (`_route_message`) to correctly parse JSON out of gemma3:27b's output. If the model hallucinates bad JSON, misroutes, or is slow, the whole experience degrades. There's no:

- Retry with backoff
- Confidence threshold (the router logs confidence but doesn't act on it)
- Fast-path for obvious patterns (e.g., "what's the weather" doesn't need an LLM call to route)
- Caching of repeated routing decisions

### 2.6 — Android Client is Scaffold-Only

The `jarvis-android/` directory has proper Kotlin/Compose structure with kiosk mode, OTA updater, and WebSocket service — but it's all scaffold code. The server has OTA endpoints (`/api/os/version`, `/api/os/apk`) that point to a non-existent `dist/` directory. This is fine as a placeholder but should be clearly marked as such.

### 2.7 — CLAUDE.md is Stale

The recon output already flagged this: CLAUDE.md says 9 adapters and "Phase 1" while reality is 14 adapters and Sprint 5. This matters because Claude Code uses CLAUDE.md as ground truth — stale docs mean stale AI assistance.

---

## 3. Architecture Recommendations

### 3.1 — Introduce a Service Layer Between Server and Core

**Problem:** `server.py` at 557 lines is doing too much — it's a web framework, a WebSocket manager, a file promotion endpoint, and a notebook CRUD layer all in one.

**Recommendation:** Split into:
- `server.py` — HTTP routes only, thin handlers
- `services/chat_service.py` — wraps core.chat() + personality
- `services/notebook_service.py` — ChromaDB operations
- `services/device_service.py` — device registry
- `services/workflow_service.py` — workflow engine interface

This is not microservices — it's just clean separation within the monolith. Each service can be tested independently.

### 3.2 — Add a Fast-Path Router

Before hitting the LLM for routing, run a lightweight keyword/regex matcher:

```
"weather" → WeatherAdapter.current  
"grocery|meal plan|shopping" → GroceryAdapter  
"market|stocks|portfolio" → InvestorAdapter  
"security|camera|approval" → SummerPuppyAdapter
```

This cuts latency for 80% of queries from ~2-5 seconds (LLM round-trip) to near-instant. Fall through to the LLM router for ambiguous queries. Log when fast-path and LLM disagree for calibration.

### 3.3 — Move to Async-First

The current pattern of sync functions wrapped in `run_in_executor` is inside-out. Adapters should be async by default:

```python
class BaseAdapter:
    async def run(self, capability: str, params: dict) -> AdapterResult:
        raise NotImplementedError
    
    async def safe_run(self, capability, params, **kwargs) -> AdapterResult:
        try:
            return await asyncio.wait_for(self.run(capability, params), timeout=30)
        except asyncio.TimeoutError:
            return AdapterResult(success=False, text="Adapter timed out", ...)
```

This also naturally gives you per-adapter timeouts, which you don't have today.

### 3.4 — Unify Configuration

Create a single `jarvis/config.py` that:
1. Loads `.env` file (python-dotenv)
2. Overlays environment variables  
3. Merges `data/preferences.json` for user-facing settings
4. Exposes typed attributes: `config.ollama_host`, `config.model`, `config.brief_hour`

Everything else reads from this. No more scattered `os.getenv()` calls.

### 3.5 — Abstract External System Access

Replace hardcoded `sys.path.insert` patterns with a plugin/integration config:

```python
# jarvis/config.py or jarvis/integrations.py
INTEGRATIONS = {
    "grocery_agent": {"path": "C:/AI-Lab/agents", "module": "grocery_agent"},
    "investor": {"path": "C:/AI-Lab/AI_Agent_Investor/...", "module": "orchestrator"},
}
```

Each adapter uses an `import_integration("grocery_agent")` helper that handles path manipulation cleanly and fails gracefully with a clear error.

### 3.6 — Replace JSON Memory with SQLite

Conversation memory should move to SQLite (like agent_memory already did). One database, two tables: `conversations` and `decisions`. This gives you:
- Concurrent access from multiple devices
- Proper transaction boundaries
- Query capabilities (search history by adapter, date range, etc.)
- No more read-entire-file-on-every-message

### 3.7 — Extract Scheduler to a Separate Process

Run the scheduler as a standalone worker (`python -m jarvis.worker`) that:
- Uses APScheduler with a persistent job store (SQLite)
- Calls Jarvis API endpoints to trigger briefs, health checks, workflows
- Can be restarted independently of the web server
- Can be monitored via a simple health endpoint

---

## 4. Feature Prioritization (What to Build Next)

Based on what's in the codebase and what's clearly aspirational:

### Tier 1 — High impact, low effort (Sprint 6)
1. **Fix CLAUDE.md** — 30 minutes. Unblocks better AI-assisted development.
2. **Fast-path router** — 2-3 hours. Dramatically improves UX for common queries.
3. **Unified config** — half day. Reduces confusion, makes deployment easier.
4. **SQLite conversation memory** — half day. Already have the pattern in agent_memory.
5. **Adapter timeout enforcement** — 1 hour. Add `asyncio.wait_for()` to prevent one slow adapter from hanging everything.

### Tier 2 — Medium effort, high value (Sprint 7-8)
6. **Service layer refactor** — 1-2 days. Clean separation, better testability.
7. **Integration abstraction** — 1 day. Decouple from filesystem paths.
8. **Async-first adapters** — 2 days. Unlock parallel adapter execution and proper timeout handling.
9. **Android client MVP** — bring the scaffold to life with basic chat + TTS playback on a real device.

### Tier 3 — Strategic (Sprint 9+)
10. **Separate scheduler worker** — decouple from web server lifecycle.
11. **Multi-user support** — if this expands beyond your household.
12. **Plugin system** — allow third-party adapters without touching core code.
13. **Bring DevTeam adapter to production** — it's the most ambitious piece (Architect → Developer → QA pipeline) but currently generates code into an isolated artifacts directory with no clear deployment path beyond the whitelist promote endpoint.

---

## 5. What I'd Do Differently (Opinionated Takes)

**Drop the personality rewrite layer or make it optional-per-request.** Running a second LLM call (even on qwen2.5:0.5b) on every single response adds latency and can distort adapter output. Make it a preference toggle that defaults to OFF, and let the user enable it for specific contexts (morning brief, ambient mode).

**The DevTeam adapter is cool but premature.** It's a full AI software engineering pipeline (Architect → Developer → QA → DevOps) embedded inside a home assistant. The SalesAgentAdapter even delegates scraper generation to DevTeam. This is a separate product — consider extracting it to its own repo and having Jarvis call it as an external service rather than an in-process adapter.

**Discord as the notification channel is fine for now** but consider supporting multiple channels (Pushover, ntfy, Telegram) behind a simple interface. The `DiscordNotifier` class is already well-structured for this.

**The weather adapter should cache aggressively.** Weather doesn't change minute-to-minute. The ambient cache (1hr TTL) is good but the adapter itself should short-circuit repeated calls.

---

## 6. Proposed Sprint 6 Plan

**Theme: Stabilize the foundation before adding features**

| Task | Est. | Priority |
|------|------|----------|
| Update CLAUDE.md to reflect Sprint 5 reality | 30min | P0 |
| Create `jarvis/config.py` — unified configuration | 4h | P0 |
| Migrate conversation memory to SQLite | 4h | P0 |
| Add keyword-based fast-path router | 3h | P1 |
| Add adapter-level timeout (30s default) | 1h | P1 |
| Create `docs/` directory with RECON-REPORT.md and this review | 1h | P1 |
| Refactor `server.py` into service layer (at least extract notebook + device endpoints) | 6h | P2 |
| Abstract external integration paths | 4h | P2 |

**Total estimate: ~24 hours of focused work (1 sprint)**

After Sprint 6, you'll have a much cleaner foundation to build Sprint 7+ features on — particularly the Android client and any new adapters.

---

## 7. Questions for You

Before we start executing, I'd want to understand:

1. **What's the deployment target?** Always running on the ZBook? Docker? Multiple machines?
2. **Is the Android client a priority?** The scaffold is there but needs real investment to become usable.
3. **Which adapters actually get daily use?** Should we focus on making grocery + investor bulletproof, or spread effort across all of them?
4. **Is the DevTeam adapter something you use regularly, or was it an experiment?**
5. **What's the vision for the other C:\ai-lab projects** (SummerPuppy, Vision, AI_Agent_Investor)? Are they converging into Jarvis or staying independent?
