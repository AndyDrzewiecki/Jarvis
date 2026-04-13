"""
Lightweight ambient context provider — no LLM call, no blocking I/O.

Provides time-of-day bucket, day-of-week, workday status, and weather summary
read from data/ambient_cache.json (written by WeatherAdapter on success).

Falls back gracefully: missing/stale cache → weather_summary = "".

Controlled by JARVIS_AMBIENT_ENABLED (default true).
Disable in tests: monkeypatch.setenv("JARVIS_AMBIENT_ENABLED", "false")
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone

_WEATHER_CACHE = os.getenv("JARVIS_AMBIENT_CACHE", "data/ambient_cache.json")
_CACHE_MAX_AGE_S = 3600  # 1 hour


def _ambient_enabled() -> bool:
    return os.getenv("JARVIS_AMBIENT_ENABLED", "true").lower() in ("true", "1", "yes")


def _time_of_day(hour: int) -> str:
    """Map local hour to human-readable bucket.
    00-05 = Night | 06-11 = Morning | 12-16 = Afternoon | 17-20 = Evening | 21-23 = Night
    """
    if 6 <= hour <= 11:
        return "Morning"
    if 12 <= hour <= 16:
        return "Afternoon"
    if 17 <= hour <= 20:
        return "Evening"
    return "Night"


def _weather_summary() -> str:
    """Read weather from cache. Returns '' if missing, unreadable, or stale."""
    try:
        with open(_WEATHER_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        updated = data.get("updated_at", "")
        if updated:
            age = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(updated)
            ).total_seconds()
            if age > _CACHE_MAX_AGE_S:
                return ""
        return data.get("summary", "")
    except Exception:
        return ""


def get_context() -> dict:
    """Return ambient context dict. Always succeeds (no I/O that can crash)."""
    now = datetime.now()
    hour = now.hour
    return {
        "time_of_day": _time_of_day(hour),
        "day_of_week": now.strftime("%A"),
        "is_workday": now.weekday() < 5,  # Mon=0 … Fri=4
        "local_hour": hour,
        "weather_summary": _weather_summary(),
        "date_str": now.strftime("%Y-%m-%d"),
    }


def format_for_prompt() -> str:
    """Return XML-tagged ambient context block for LLM injection.
    Returns '' if JARVIS_AMBIENT_ENABLED is false.
    """
    if not _ambient_enabled():
        return ""
    ctx = get_context()
    now = datetime.now()
    # Cross-platform hour formatting (no %-I which is Linux-only)
    hour_12 = now.strftime("%I").lstrip("0") or "12"
    time_str = f"{ctx['time_of_day']} ({hour_12}:{now.strftime('%M%p').lower()})"
    workday_str = "Workday" if ctx["is_workday"] else "Weekend"
    weather_line = (
        f"\n  Weather: {ctx['weather_summary']}"
        if ctx["weather_summary"] else ""
    )
    return (
        f"<ambient_context>\n"
        f"  Time: {time_str} | {ctx['day_of_week']} | {workday_str}"
        f"{weather_line}\n"
        f"</ambient_context>"
    )
