"""
TUTORIAL: Memory stores conversation history as a JSON file.
- Keeps a rolling window of the last 100 messages.
- Each message has id, role (user/assistant), text, timestamp, and optional adapter tag.
- add() appends and returns the entry id; recent() returns the last N; clear() resets.
"""
from __future__ import annotations
import json
import os
import uuid
from datetime import datetime
from typing import Optional

MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "memory.json")


def _load() -> list:
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    if not os.path.exists(MEMORY_PATH):
        return []
    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(history: list) -> None:
    os.makedirs(os.path.dirname(MEMORY_PATH), exist_ok=True)
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history[-100:], f, indent=2, ensure_ascii=False)


def add(role: str, text: str, adapter: Optional[str] = None) -> str:
    """Append a message and return its unique id."""
    history = _load()
    entry_id = str(uuid.uuid4())
    history.append({
        "id": entry_id,
        "role": role,
        "text": text,
        "adapter": adapter,
        "timestamp": datetime.now().isoformat(),
    })
    _save(history)
    return entry_id


def recent(n: int = 10) -> list:
    return _load()[-n:]


def all_messages() -> list:
    return _load()


def clear() -> None:
    _save([])
