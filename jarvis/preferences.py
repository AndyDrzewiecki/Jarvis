"""
User Preferences Store — persistent JSON at data/preferences.json.

First access creates the file with sensible defaults.

API:
    load()            → full dict
    get(key, default) → single value
    set(key, value)   → save one key
    update(dict)      → merge-update multiple keys, return full dict
"""
from __future__ import annotations
import json
import os
from typing import Any

_PREFS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "preferences.json"
)

DEFAULTS: dict[str, Any] = {
    "city": "Minneapolis,US",
    "budget_monthly": 800,
    "dietary_restrictions": [],
    "preferred_stores": ["aldi", "walmart"],
    "notification_level": "important",  # all | important | critical
    "brief_include_weather": True,
    "personality_enabled": True,
    "personality_mode": "professional",   # professional | witty | minimal
    "address_name": "Sir",
    "tts_voice": "en-GB-RyanNeural",
    "tts_rate": "-5%",
    "tts_pitch": "-10Hz",
    "brief_voice_enabled": True,
}


def _prefs_path() -> str:
    return os.environ.get("JARVIS_PREFS_PATH", _PREFS_PATH)


def load() -> dict[str, Any]:
    """Load preferences; creates file with defaults on first access."""
    path = _prefs_path()
    try:
        with open(path, encoding="utf-8") as f:
            stored = json.load(f)
        # Merge defaults for any missing keys
        merged = {**DEFAULTS, **stored}
        if merged != stored:
            _write(merged, path)
        return merged
    except FileNotFoundError:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        _write(DEFAULTS.copy(), path)
        return DEFAULTS.copy()
    except (json.JSONDecodeError, OSError):
        return DEFAULTS.copy()


def get(key: str, default: Any = None) -> Any:
    """Get a single preference value."""
    return load().get(key, default)


def set(key: str, value: Any) -> None:
    """Set a single preference and persist."""
    prefs = load()
    prefs[key] = value
    _write(prefs, _prefs_path())


def update(updates: dict[str, Any]) -> dict[str, Any]:
    """Merge-update multiple preferences and return the full updated dict."""
    prefs = load()
    prefs.update(updates)
    _write(prefs, _prefs_path())
    return prefs


def _write(prefs: dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(prefs, f, indent=2, ensure_ascii=False)
