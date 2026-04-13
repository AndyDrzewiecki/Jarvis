# Changelog

## [0.1.0] — 2026-04-10

### Phase 1

#### Added
- `jarvis/adapters/base.py`: BaseAdapter + AdapterResult contract
- `jarvis/adapters/grocery.py`: Live GroceryAdapter wrapping C:/AI-Lab/agents/grocery_agent.py
- `jarvis/adapters/investor.py`: Live InvestorAdapter wrapping AI_Agent_Investor orchestrator
- `jarvis/adapters/stubs.py`: 7 stub adapters (weather, calendar, email, finance, home, music, news)
- `jarvis/core.py`: LLM routing brain with Ollama integration and prompt injection hardening
- `jarvis/memory.py`: JSON-backed conversation memory with rolling 100-message window
- `main.py`: Rich CLI with help, history, colored adapter routing display
- `server.py`: FastAPI server with CORS, /api/status, /api/adapters, /api/chat, /api/history
- `tests/`: 30+ tests covering adapters, core routing, server endpoints
- CLAUDE.md, README.md with adapter status table

#### Security Hardening (qa-security review)
- `core.py`: `_sanitize_for_prompt()` escapes `<`, `>`, `&` in user input before LLM interpolation
- `core.py`: General chat prompt now uses XML delimiters + injection guard (same as routing prompt)
- `core.py`: History context sanitized before replay into general chat prompt
- `core.py`: Capability string validated against `adapter.capabilities` whitelist before dispatch
- `server.py`: Bind address changed from `0.0.0.0` to `127.0.0.1`
- `server.py`: CORS restricted to `JARVIS_CORS_ORIGINS` env var (default: `localhost:3000`)
- `server.py`: `ollama_host` removed from `/api/status` response
- `server.py`: `ChatRequest.message` capped at `max_length=4000`
