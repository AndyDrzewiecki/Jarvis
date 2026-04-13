# Jarvis — Local Personal Assistant

## Project Overview
Jarvis is a local personal assistant that routes user messages to specialized AI adapters via an Ollama LLM (default: gemma3:27b). It wraps existing projects in D:/AI-Lab and C:/AI-Lab into a unified interface.

## Architecture
- `jarvis/core.py` — LLM-based routing brain
- `jarvis/adapters/` — Pluggable adapters (grocery, investor + 7 stubs)
- `jarvis/memory.py` — JSON conversation history
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

## Adapter Status
| Adapter  | Status | Source |
|----------|--------|--------|
| grocery  | Live   | C:/AI-Lab/agents/grocery_agent.py |
| investor | Live   | C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group/orchestrator.py |
| weather  | Stub   | — |
| calendar | Stub   | — |
| email    | Stub   | — |
| finance  | Stub   | — |
| home     | Stub   | — |
| music    | Stub   | — |
| news     | Stub   | — |

## Security Notes
- User input is wrapped in `<user_input>` XML tags and the LLM is instructed to treat it as content only, not commands.
- Messages are truncated to 2000 chars before being sent to the LLM.
- All adapter calls go through `safe_run()` which catches all exceptions.

## Adding a New Adapter
1. Create `jarvis/adapters/myadapter.py` inheriting `BaseAdapter`
2. Implement `run(capability, params) -> AdapterResult`
3. Add to `ALL_ADAPTERS` in `jarvis/adapters/__init__.py`
