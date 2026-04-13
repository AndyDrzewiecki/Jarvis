"""
Device registry for JarvisOS nodes.

Stores device registrations in data/devices.json.
Provides profile-based context injection for LLM prompts.

Device profiles: kitchen | garage | phone | bedroom | default
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any

_DEVICES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "devices.json"
)

PROFILE_CONTEXTS: dict[str, str] = {
    "kitchen": "This request comes from the kitchen tablet. Prioritize food, grocery, cooking, and recipe responses.",
    "garage": "This request comes from the garage tablet. Prioritize tools, how-to guides, parts lookup, and maintenance responses.",
    "phone": "This request comes from Andy's phone (companion mode). Standard responses, consider mobile context.",
    "bedroom": "This request comes from the bedroom tablet. Use calm, ambient tone. Prioritize sleep, alarms, and gentle morning content.",
    "default": "Standard Jarvis node.",
}


def _devices_path() -> str:
    return os.environ.get("JARVIS_DEVICES_PATH", _DEVICES_PATH)


def _load() -> dict[str, Any]:
    path = _devices_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"devices": {}}


def _save(data: dict[str, Any]) -> None:
    path = _devices_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def register(device_id: str, profile: str, display_name: str) -> dict[str, Any]:
    """Register or update a device. Returns the device record."""
    profile = profile if profile in PROFILE_CONTEXTS else "default"
    data = _load()
    record = {
        "device_id": device_id,
        "profile": profile,
        "display_name": display_name,
        "last_seen": datetime.now(timezone.utc).isoformat(),
    }
    data["devices"][device_id] = record
    _save(data)
    return record


def list_devices() -> list[dict[str, Any]]:
    """Return all registered devices as a list."""
    data = _load()
    return list(data.get("devices", {}).values())


def get_profile(device_id: str) -> str:
    """Return the profile name for a device_id. Returns 'default' if unknown."""
    data = _load()
    device = data.get("devices", {}).get(device_id)
    if device:
        return device.get("profile", "default")
    return "default"


def get_context_injection(device_id: str | None) -> str:
    """Return the LLM context string for a device profile."""
    if not device_id:
        return PROFILE_CONTEXTS["default"]
    profile = get_profile(device_id)
    return PROFILE_CONTEXTS.get(profile, PROFILE_CONTEXTS["default"])
