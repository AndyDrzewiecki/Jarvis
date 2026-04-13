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

_GRADES_DDL = """
CREATE TABLE IF NOT EXISTS decision_grades (
    id                   TEXT PRIMARY KEY,
    decision_id          TEXT NOT NULL,
    short_term_grade     TEXT,
    short_term_score     REAL,
    short_term_reason    TEXT,
    short_term_graded_at TEXT,
    long_term_grade      TEXT,
    long_term_score      REAL,
    long_term_reason     TEXT,
    long_term_graded_at  TEXT,
    grading_model        TEXT,
    revised              INTEGER DEFAULT 0
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
    conn.execute(_GRADES_DDL)
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


def save_grade(
    decision_id: str,
    short_term_grade: str,
    short_term_score: float,
    short_term_reason: str,
    model: str = "",
) -> str:
    """Insert or update a short-term grade for a decision. Returns grade id."""
    grade_id = str(uuid.uuid4())
    try:
        conn = _open(DB_PATH)
        # Check if grade already exists
        existing = conn.execute(
            "SELECT id FROM decision_grades WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE decision_grades
                   SET short_term_grade=?, short_term_score=?, short_term_reason=?,
                       short_term_graded_at=?, grading_model=?
                   WHERE decision_id=?""",
                (short_term_grade, short_term_score, short_term_reason,
                 datetime.now().isoformat(), model, decision_id),
            )
            grade_id = existing["id"]
        else:
            conn.execute(
                """INSERT INTO decision_grades
                   (id, decision_id, short_term_grade, short_term_score,
                    short_term_reason, short_term_graded_at, grading_model)
                   VALUES (?,?,?,?,?,?,?)""",
                (grade_id, decision_id, short_term_grade, short_term_score,
                 short_term_reason, datetime.now().isoformat(), model),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return grade_id


def get_ungraded_decisions(since_hours: int = 24) -> list[dict]:
    """Return decisions from the last N hours that have no grade row yet."""
    try:
        conn = _open(DB_PATH)
        from datetime import timedelta
        since_dt = datetime.now() - timedelta(hours=since_hours)
        rows = conn.execute(
            """SELECT d.* FROM decisions d
               LEFT JOIN decision_grades g ON d.id = g.decision_id
               WHERE g.id IS NULL
               AND d.timestamp >= ?
               ORDER BY d.timestamp""",
            (since_dt.isoformat(),),
        ).fetchall()
        conn.close()
        return [_row_to_dict(r) for r in rows]
    except Exception:
        return []


def get_grade(decision_id: str) -> dict | None:
    """Retrieve grade record for a decision. Returns None if not graded."""
    try:
        conn = _open(DB_PATH)
        row = conn.execute(
            "SELECT * FROM decision_grades WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        conn.close()
        return _row_to_dict(row) if row else None
    except Exception:
        return None


def get_decisions_for_long_term_grading(
    min_age_days: int = 7, max_age_days: int = 30
) -> list[tuple[dict, dict]]:
    """Return (decision, grade) pairs eligible for long-term grading.

    Criteria:
    - decision was made between min_age_days and max_age_days ago
    - short-term grade exists (short_term_grade IS NOT NULL)
    - long-term grade does not yet exist (long_term_grade IS NULL)
    """
    from datetime import timedelta
    try:
        conn = _open(DB_PATH)
        min_ts = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        max_ts = (datetime.now() - timedelta(days=min_age_days)).isoformat()
        rows = conn.execute(
            """SELECT d.*, g.id AS grade_id, g.short_term_grade, g.short_term_score,
                      g.short_term_reason, g.short_term_graded_at, g.long_term_grade,
                      g.long_term_score, g.long_term_reason, g.long_term_graded_at,
                      g.grading_model
               FROM decisions d
               JOIN decision_grades g ON d.id = g.decision_id
               WHERE d.timestamp >= ?
                 AND d.timestamp <= ?
                 AND g.short_term_grade IS NOT NULL
                 AND g.long_term_grade IS NULL
               ORDER BY d.timestamp""",
            (min_ts, max_ts),
        ).fetchall()
        conn.close()
        result = []
        for row in rows:
            d = _row_to_dict(row)
            decision = {k: d[k] for k in (
                "id", "timestamp", "agent", "capability", "decision",
                "reasoning", "confidence", "outcome", "linked_message_id",
                "params_summary", "duration_ms",
            ) if k in d}
            grade = {k: d[k] for k in (
                "short_term_grade", "short_term_score", "short_term_reason",
                "short_term_graded_at", "long_term_grade", "long_term_score",
                "long_term_reason", "long_term_graded_at", "grading_model",
            ) if k in d}
            result.append((decision, grade))
        return result
    except Exception:
        return []


def update_long_term_grade(
    decision_id: str,
    long_term_grade: str,
    long_term_score: float,
    long_term_reason: str,
    model: str = "",
) -> None:
    """Update the long_term_* columns on an existing decision_grades row."""
    try:
        conn = _open(DB_PATH)
        conn.execute(
            """UPDATE decision_grades
               SET long_term_grade=?, long_term_score=?, long_term_reason=?,
                   long_term_graded_at=?, grading_model=?
               WHERE decision_id=?""",
            (long_term_grade, long_term_score, long_term_reason,
             datetime.now().isoformat(), model, decision_id),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
