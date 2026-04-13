"""
Conversation memory — SQLite-backed rolling window.
Keeps the same public API as the original JSON version.
Schema: messages(id, role, text, adapter, timestamp)
"""
from __future__ import annotations
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

# Keep MEMORY_PATH name for backward compat with tests that monkeypatch it
MEMORY_PATH = os.getenv("JARVIS_MEMORY_DB",
    os.path.join(os.path.dirname(__file__), "..", "data", "memory.db"))

MAX_MESSAGES = int(os.getenv("JARVIS_MEMORY_MAX", "100"))

_DDL = """
CREATE TABLE IF NOT EXISTS messages (
    id        TEXT PRIMARY KEY,
    role      TEXT NOT NULL,
    text      TEXT NOT NULL,
    adapter   TEXT,
    timestamp TEXT NOT NULL
);
"""


def _open(db_path: str = MEMORY_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(_DDL)
    conn.commit()
    return conn


def add(role: str, text: str, adapter: Optional[str] = None) -> str:
    """Append a message and return its unique id."""
    entry_id = str(uuid.uuid4())
    try:
        conn = _open(MEMORY_PATH)
        conn.execute(
            "INSERT INTO messages (id, role, text, adapter, timestamp) VALUES (?,?,?,?,?)",
            (entry_id, role, text, adapter, datetime.now().isoformat()),
        )
        conn.commit()
        # Trim to MAX_MESSAGES (keep newest)
        conn.execute(
            """DELETE FROM messages WHERE id NOT IN (
               SELECT id FROM messages ORDER BY timestamp DESC LIMIT ?
            )""",
            (MAX_MESSAGES,),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return entry_id


def recent(n: int = 10) -> list[dict]:
    """Return the last n messages in chronological order."""
    try:
        conn = _open(MEMORY_PATH)
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]
    except Exception:
        return []


def all_messages() -> list[dict]:
    """Return all messages in chronological order."""
    try:
        conn = _open(MEMORY_PATH)
        rows = conn.execute(
            "SELECT * FROM messages ORDER BY timestamp"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def clear() -> None:
    """Delete all messages."""
    try:
        conn = _open(MEMORY_PATH)
        conn.execute("DELETE FROM messages")
        conn.commit()
        conn.close()
    except Exception:
        pass
