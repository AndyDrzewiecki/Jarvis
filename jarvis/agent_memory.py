"""
Agent Decision Memory — append-only audit log of every agent reasoning step.

Storage: data/decisions.db (SQLite3, stdlib). Migrates from decisions.jsonl on
first access if the JSONL file exists alongside the database.

Same public API as the original JSONL version — callers see no difference.

Schema per entry:
  id, timestamp, agent, capability, decision, reasoning (max 1000 chars),
  confidence (0.0-1.0 or null), outcome (success|failure|unknown),
  linked_message_id, params_summary, duration_ms
"""
from __future__ import annotations
import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "decisions.db")

_DDL = """
CREATE TABLE IF NOT EXISTS decisions (
    id                TEXT PRIMARY KEY,
    timestamp         TEXT NOT NULL,
    agent             TEXT NOT NULL,
    capability        TEXT NOT NULL,
    decision          TEXT NOT NULL,
    reasoning         TEXT NOT NULL,
    confidence        REAL,
    outcome           TEXT NOT NULL DEFAULT 'unknown',
    linked_message_id TEXT,
    params_summary    TEXT,
    duration_ms       INTEGER
)
"""

# Track which DB paths have been initialised (and migrated) this process.
_inited: set[str] = set()


def _open(db_path: str) -> sqlite3.Connection:
    """Open the SQLite DB, run DDL, and migrate JSONL once per path."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    if db_path not in _inited:
        _inited.add(db_path)
        _migrate_jsonl(db_path, conn)
    return conn


def _migrate_jsonl(db_path: str, conn: sqlite3.Connection) -> None:
    """Import any decisions.jsonl found next to the DB file (one-time migration)."""
    jsonl = os.path.join(os.path.dirname(os.path.abspath(db_path)), "decisions.jsonl")
    if not os.path.exists(jsonl):
        return
    try:
        with open(jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    conn.execute(
                        """INSERT OR IGNORE INTO decisions
                           (id, timestamp, agent, capability, decision, reasoning,
                            confidence, outcome, linked_message_id, params_summary, duration_ms)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            e.get("id") or str(uuid.uuid4()),
                            e.get("timestamp", datetime.now().isoformat()),
                            e.get("agent", ""),
                            e.get("capability", ""),
                            e.get("decision", ""),
                            (e.get("reasoning") or "")[:1000],
                            e.get("confidence"),
                            e.get("outcome", "unknown"),
                            e.get("linked_message_id"),
                            e.get("params_summary"),
                            e.get("duration_ms"),
                        ),
                    )
                except Exception:
                    pass
        conn.commit()
    except Exception:
        pass


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


# ── public API ────────────────────────────────────────────────────────────────

def log_decision(
    agent: str,
    capability: str,
    decision: str,
    reasoning: str,
    confidence: Optional[float] = None,
    outcome: str = "unknown",
    linked_message_id: Optional[str] = None,
    params_summary: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> str:
    """Append one decision entry. Returns the new entry's id. Never raises."""
    entry_id = str(uuid.uuid4())
    try:
        conn = _open(DB_PATH)
        conn.execute(
            """INSERT INTO decisions
               (id, timestamp, agent, capability, decision, reasoning,
                confidence, outcome, linked_message_id, params_summary, duration_ms)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                entry_id,
                datetime.now().isoformat(),
                agent,
                capability,
                decision,
                reasoning[:1000],
                confidence,
                outcome,
                linked_message_id,
                params_summary,
                duration_ms,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return entry_id


def _load_all() -> list[dict]:
    """Load all entries in chronological order."""
    try:
        conn = _open(DB_PATH)
        rows = conn.execute(
            "SELECT * FROM decisions ORDER BY timestamp"
        ).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def query(
    agent: Optional[str] = None,
    capability: Optional[str] = None,
    since_iso: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Filter decisions. Returns up to `limit` most recent matching entries."""
    try:
        conn = _open(DB_PATH)
        sql = "SELECT * FROM decisions WHERE 1=1"
        params: list = []
        if agent:
            sql += " AND agent = ?"
            params.append(agent)
        if capability:
            sql += " AND capability = ?"
            params.append(capability)
        if since_iso:
            sql += " AND timestamp >= ?"
            params.append(since_iso)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        conn.close()
        # reverse so returned list is chronological (oldest first)
        return [_row_to_dict(r) for r in reversed(rows)]
    except Exception:
        return []


def recent_decisions(n: int = 20) -> list[dict]:
    """Return the last N decisions across all agents (chronological order)."""
    try:
        conn = _open(DB_PATH)
        rows = conn.execute(
            "SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in reversed(rows)]
    except Exception:
        return []
