# Jarvis — Local Household Operating System

## Project Overview
Jarvis is a local household operating system that routes user messages to specialized AI adapters via an Ollama LLM (default: gemma3:27b). It wraps existing projects in D:/AI-Lab and C:/AI-Lab into a unified interface.

## Vision & Roadmap
**Read `ROADMAP.md` for the full 8-phase product roadmap.** Jarvis is being built to run as a custom Android OS on tablets throughout the house, with voice control, computer vision, Bluetooth/IoT smart home management, network security, and self-training models. The current work is Phase 3 (Knowledge Engines). All implementation decisions should align with this long-term vision.

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
- `JARVIS_MEMORY_MAX` — max messages to retain, defau