"""
Unified configuration — single source of truth for all Jarvis settings.
Reads environment variables with sensible defaults.
Everything else should import from here rather than calling os.getenv directly.
"""
from __future__ import annotations
import os
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR   = os.path.join(_ROOT, "data")
STATIC_DIR = os.path.join(_ROOT, "static")

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_HOST    = os.getenv("OLLAMA_HOST",           "http://localhost:11434")
MODEL          = os.getenv("JARVIS_MODEL",           "gemma3:27b")
FALLBACK_MODEL = os.getenv("JARVIS_FALLBACK_MODEL",  "qwen2.5:0.5b")

# ── Storage paths ─────────────────────────────────────────────────────────────
MEMORY_DB_PATH    = os.getenv("JARVIS_MEMORY_DB",    os.path.join(DATA_DIR, "memory.db"))
DECISIONS_DB_PATH = os.getenv("JARVIS_DECISIONS_DB", os.path.join(DATA_DIR, "decisions.db"))
EPISODES_DB_PATH  = os.getenv("JARVIS_EPISODES_DB",  os.path.join(DATA_DIR, "episodes.db"))
SEMANTIC_DB_PATH  = os.getenv("JARVIS_SEMANTIC_DB",  os.path.join(DATA_DIR, "semantic.db"))
CHROMADB_PATH     = os.getenv("JARVIS_CHROMADB_PATH", os.path.join(DATA_DIR, "chromadb"))
PREFS_PATH        = os.getenv("JARVIS_PREFS_PATH",    os.path.join(DATA_DIR, "preferences.json"))
HOUSEHOLD_STATE_PATH = os.getenv("JARVIS_HOUSEHOLD_STATE", os.path.join(DATA_DIR, "household_state.json"))
LIBRARY_ROOT = os.getenv("JARVIS_LIBRARY_ROOT", os.path.join(DATA_DIR, "library"))

# ── Behaviour ─────────────────────────────────────────────────────────────────
ADAPTER_TIMEOUT_S        = int(os.getenv("JARVIS_ADAPTER_TIMEOUT",  "30"))
MEMORY_MAX_MESSAGES      = int(os.getenv("JARVIS_MEMORY_MAX",       "100"))
ENTITY_EXTRACTION_ENABLED = os.getenv("JARVIS_ENTITY_EXTRACTION", "false").lower() in ("true", "1", "yes")
SPECIALISTS_ENABLED      = os.getenv("JARVIS_SPECIALISTS_ENABLED", "false").lower() in ("true", "1", "yes")

# ── Integrations ──────────────────────────────────────────────────────────────
# Maps integration name → filesystem path for sys.path injection
INTEGRATION_PATHS: dict[str, str] = {
    "grocery_agent":  os.getenv("JARVIS_INTEGRATION_GROCERY",    r"C:/AI-Lab/agents"),
    "investor":       os.getenv("JARVIS_INTEGRATION_INVESTOR",   r"C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group"),
    "orchestrator":   os.getenv("JARVIS_INTEGRATION_INVESTOR",   r"C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group"),
    "summerpuppy":    os.getenv("JARVIS_INTEGRATION_SUMMERPUPPY", r"C:/AI-Lab/SummerPuppy"),
    "sales_agent":    os.getenv("JARVIS_INTEGRATION_SALES",      r"C:/AI-Lab/agents"),
}

# ── Notifications ─────────────────────────────────────────────────────────────
DISCORD_WEBHOOK_URL = os.getenv("JARVIS_DISCORD_WEBHOOK", "")
NOTIFICATION_LEVEL  = os.getenv("JARVIS_NOTIFICATION_LEVEL", "important")

# ── Feature flags ─────────────────────────────────────────────────────────────
PERSONALITY_ENABLED = os.getenv("JARVIS_PERSONALITY", "true").lower() in ("true", "1", "yes")
BRIEF_VOICE_ENABLED = os.getenv("JARVIS_BRIEF_VOICE", "true").lower() in ("true", "1", "yes")
PROCEDURAL_FASTPATH = os.getenv("JARVIS_PROCEDURAL_FASTPATH", "false").lower() in ("true", "1", "yes")


GOOGLE_CREDENTIALS_PATH = os.getenv("JARVIS_GOOGLE_CREDS", os.path.join(DATA_DIR, "google_credentials.json"))
NEWS_FEED_URLS: list[str] = [u.strip() for u in os.getenv("JARVIS_NEWS_FEEDS", "").split(",") if u.strip()]


# ── Helper ────────────────────────────────────────────────────────────────────
def get(key: str, default: Any = None) -> Any:
    """Read a config value by name. Allows runtime override in tests."""
    return globals().get(key, default)
