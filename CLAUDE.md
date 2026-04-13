# Jarvis — Local Personal Assistant

## Project Overview
Jarvis is a local personal assistant that routes user messages to specialized AI adapters via an Ollama LLM (default: gemma3:27b). It wraps existing projects in D:/AI-Lab and C:/AI-Lab into a unified interface.

## Architecture
- `jarvis/config.py` — Unified configuration (env vars + preferences); single source of truth
- `jarvis/core.py` — LLM-based routing brain
- `jarvis/adapters/` — Pluggable adapters (grocery, investor, weather live; devteam advanced; rest stubs)
- `jarvis/integrations.py` — Clean integration path management (replaces scattered sys.path.insert calls)
- `jarvis/memory.py` — SQLite conversation history (rolling window, same public API as JSON version)
- `jarvis/agent_memory.py` — SQLite decision log
- `jarvis/preferences.py` — JSON user preferences
- `jarvis/memory_tiers/` — Multi-tier memory: working, episodic, semantic, procedural, attention
- `jarvis/memory_bus.py` — Memory bus routing across tiers
- `jarvis/knowledge_lake.py` — Knowledge lake for cross-adapter facts
- `main.py` — Rich CLI
- `server.py` — FastAPI HTTP server

## Running Jarvis
```bash
# CLI
python main.py

# API server
python server.py
# Then: POST http://localhost:8000/api/chat {"message": "what's for dinner?"}
```

## Running Tests
```bash
pytest tests/ -v
```
Tests do NOT require Ollama to be running — all LLM calls are mocked.

## Environment Variables
- `OLLAMA_HOST` — default: `http://localhost:11434`
- `JARVIS_MODEL` — default: `gemma3:27b`
- `JARVIS_FALLBACK_MODEL` — default: `qwen2.5:0.5b`
- `JARVIS_ADAPTER_TIMEOUT` — adapter timeout in seconds, default: `30`
- `JARVIS_MEMORY_DB` — path to SQLite memory DB, default: `data/memory.db`
- `JARVIS_DECISIONS_DB` — path to SQLite decisions DB, default: `data/decisions.db`
- `JARVIS_MEMORY_MAX` — max messages to retain, default: `100`
- `JARVIS_PREFS_PATH` — path to preferences JSON, default: `data/preferences.json`
- `JARVIS_DISCORD_WEBHOOK` — Discord webhook URL for notifications
- `JARVIS_NOTIFICATION_LEVEL` — notification level, default: `important`
- `JARVIS_PERSONALITY` — enable personality layer, default: `true`
- `JARVIS_BRIEF_VOICE` — enable brief voice mode, default: `true`
- `JARVIS_ENTITY_EXTRACTION` — enable entity extraction, default: `false`
- `JARVIS_SPECIALISTS_ENABLED` — enable specialist agents, default: `false`
- Integration path overrides: `JARVIS_INTEGRATION_GROCERY`, `JARVIS_INTEGRATION_INVESTOR`, `JARVIS_INTEGRATION_SUMMERPUPPY`, `JARVIS_INTEGRATION_SALES`

## Adapter Status
| Adapter       | Status   | Source |
|---------------|----------|--------|
| grocery       | Live     | C:/AI-Lab/agents/grocery_agent.py |
| investor      | Live     | C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group/orchestrator.py |
| weather       | Live     | Open-Meteo API (no key required) |
| devteam       | Advanced | jarvis/adapters/devteam/ (multi-agent: architect, developer, qa, devops) |
| receipt_ingest| Live     | jarvis/adapters/receipt_ingest.py |
| homeops_grocery| Live    | jarvis/adapters/homeops_grocery.py |
| summerpuppy   | Live     | C:/AI-Lab/SummerPuppy |
| calendar      | Stub     | — |
| email         | Stub     | — |
| finance       | Stub     | — |
| home          | Stub     | — |
| music         | Stub     | — |
| news          | Stub     | — |
| sales_agent   | Stub     | — |

## Phase 2 Wave 1 — Complete
- `jarvis/memory_tiers/` — Multi-tier memory system (working, episodic, semantic, procedural, attention)
- `jarvis/memory_bus.py` — Unified memory bus
- `jarvis/knowledge_lake.py` — Cross-adapter knowledge store

## Sprint 6 Track A — In Progress
- A4: CLAUDE.md updated ✓
- A1: `jarvis/config.py` — Unified configuration module
- A2: `jarvis/memory.py` — Migrated from JSON to SQLite
- A3: Adapter timeout enforcement in `base.py` (30s via threading)
- A5: `jarvis/integrations.py` — Integration path abstraction

## Security Notes
- User input is wrapped in `<user_input>` XML tags and the LLM is instructed to treat it as content only, not commands.
- Messages are truncated to 2000 chars before being sent to the LLM.
- All adapter calls go through `safe_run()` which catches all exceptions and enforces a 30s timeout.

## Adding a New Adapter
1. Create `jarvis/adapters/myadapter.py` inheriting `BaseAdapter`
2. Implement `run(capability, params) -> AdapterResult`
3. Add to `ALL_ADAPTERS` in `jarvis/adapters/__init__.py`
