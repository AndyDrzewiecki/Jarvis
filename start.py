#!/usr/bin/env python3
"""
Jarvis Startup Script — boots all systems on the local machine.

Usage:
    python start.py              # Full startup: API server + specialists + engines
    python start.py --cli        # CLI mode only (no background server)
    python start.py --api-only   # API server without specialists/engines
    python start.py --check      # Health check: verify Ollama, DBs, config

Environment:
    Copy .env.example to .env and fill in your API keys.
    All keys are optional — Jarvis runs fine without them (engines skip missing sources).
"""
from __future__ import annotations
import argparse
import logging
import os
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a readable format."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_dotenv() -> None:
    """Load .env file if it exists (no external dependency required)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Don't override existing env vars (e.g. set in shell before starting)
            if not os.environ.get(key):
                os.environ[key] = value


def check_ollama() -> bool:
    """Verify Ollama is running and at least one model is available."""
    from jarvis import config
    import urllib.request
    try:
        url = f"{config.OLLAMA_HOST}/api/tags"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json
            data = json.loads(resp.read())
            models = [m.get("name", "") for m in data.get("models", [])]
            has_main = any(config.MODEL in m for m in models)
            has_fallback = any(config.FALLBACK_MODEL in m for m in models)
            return has_main or has_fallback
    except Exception:
        return False


def check_health() -> dict:
    """Run full health check. Returns a dict of status items."""
    results: dict = {}

    # Ollama connectivity
    results["ollama"] = check_ollama()

    # Configuration snapshot
    from jarvis import config
    results["model"] = config.MODEL
    results["fallback_model"] = config.FALLBACK_MODEL
    results["specialists_enabled"] = config.SPECIALISTS_ENABLED
    results["engines_enabled"] = config.ENGINES_ENABLED

    # Data directory
    results["data_dir_exists"] = os.path.isdir(config.DATA_DIR)

    # API key readiness (boolean — never log the values)
    results["api_keys"] = {
        "fred": bool(config.FRED_API_KEY),
        "github": bool(config.GITHUB_TOKEN),
        "congress": bool(config.CONGRESS_API_KEY),
        "airnow": bool(config.AIRNOW_API_KEY),
        "eventbrite": bool(config.EVENTBRITE_TOKEN),
        "nps": bool(config.NPS_API_KEY),
    }

    # Specialist registry
    try:
        from jarvis.specialists import SPECIALIST_REGISTRY
        results["specialists"] = len(SPECIALIST_REGISTRY)
    except Exception as exc:
        results["specialists"] = f"error: {exc}"

    # Engine registry
    try:
        from jarvis.engines import ENGINE_REGISTRY
        # Trigger imports of all registered engines
        import jarvis.engines.financial  # noqa: F401
        import jarvis.engines.research   # noqa: F401
        import jarvis.engines.geopolitical  # noqa: F401
        import jarvis.engines.legal      # noqa: F401
        import jarvis.engines.health     # noqa: F401
        import jarvis.engines.local_intel  # noqa: F401
        import jarvis.engines.family     # noqa: F401
        results["engines"] = len(ENGINE_REGISTRY)
        results["engine_names"] = [
            cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")
        ]
    except Exception as exc:
        results["engines"] = f"error: {exc}"
        results["engine_names"] = []

    return results


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the FastAPI server with background scheduler."""
    from jarvis import config

    # Start background scheduler (specialists + engines)
    try:
        from jarvis.scheduler import start as start_scheduler
        start_scheduler()
        logging.getLogger("jarvis.startup").info(
            "Scheduler started (specialists=%s, engines=%s)",
            config.SPECIALISTS_ENABLED,
            config.ENGINES_ENABLED,
        )
    except Exception as exc:
        logging.getLogger("jarvis.startup").warning("Scheduler failed to start: %s", exc)

    # Start FastAPI server via uvicorn
    import uvicorn
    uvicorn.run("server:app", host=host, port=port, reload=False)


def run_cli() -> None:
    """Start the interactive CLI."""
    from main import main
    main()


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate startup mode."""
    parser = argparse.ArgumentParser(description="Jarvis — Local Household Operating System")
    parser.add_argument("--cli", action="store_true", help="CLI mode (no server)")
    parser.add_argument("--api-only", action="store_true", help="API server without specialists/engines")
    parser.add_argument("--check", action="store_true", help="Health check only")
    parser.add_argument("--host", default="127.0.0.1", help="Server bind address")
    parser.add_argument("--port", type=int, default=8000, help="Server port")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    args = parser.parse_args()

    load_dotenv()
    setup_logging(args.log_level)
    logger = logging.getLogger("jarvis.startup")

    if args.check:
        results = check_health()
        print("\n=== Jarvis Health Check ===")
        for key, val in results.items():
            if key == "api_keys" and isinstance(val, dict):
                print("  api_keys:")
                for k, v in val.items():
                    marker = "YES" if v else "no"
                    print(f"    {k}: {marker}")
            elif key == "engine_names" and isinstance(val, list):
                print(f"  engine_names: {val}")
            elif isinstance(val, bool):
                print(f"  {key}: {'YES' if val else 'no'}")
            else:
                print(f"  {key}: {val}")
        print()
        if not results.get("ollama"):
            model = results.get("model", "gemma3:27b")
            print("  Ollama is not running! Start it with:  ollama serve")
            print(f"  Then pull the model:                  ollama pull {model}")
        return

    # Pre-flight check — warn but don't block startup
    if not check_ollama():
        logger.warning("Ollama not detected — chat will fail until Ollama is started")

    if args.api_only:
        os.environ["JARVIS_SPECIALISTS_ENABLED"] = "false"
        os.environ["JARVIS_ENGINES_ENABLED"] = "false"

    if args.cli:
        run_cli()
    else:
        logger.info("Starting Jarvis server on %s:%d", args.host, args.port)
        run_server(args.host, args.port)


if __name__ == "__main__":
    main()
