"""Forge Shared Memory — SQLite-backed knowledge lake for Project Forge agents.

7-Layer Introspection Memory (all stored here):
  Layer 1: Raw interaction logs         → table: interactions
  Layer 2: Decision audit trail         → table: routing_decisions
  Layer 3: User correction pairs        → table: corrections   (LoRA training data)
  Layer 4: Hallucination registry       → table: hallucinations
  Layer 5: Routing accuracy tracking    → embedded in routing_decisions
  Layer 6: Prompt evolution history     → table: prompt_versions
  Layer 7: Meta-patterns                → table: meta_patterns

All agents read before acting, write after completing.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "forge.db")

_DDL = """
CREATE TABLE IF NOT EXISTS interactions (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    task_id     TEXT,
    input_text  TEXT NOT NULL,
    output_text TEXT NOT NULL,
    model       TEXT,
    duration_ms INTEGER,
    layer       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS routing_decisions (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    task_id     TEXT,
    routed_to   TEXT NOT NULL,
    reason      TEXT,
    confidence  REAL,
    outcome     TEXT DEFAULT 'unknown',
    layer       INTEGER DEFAULT 2
);

CREATE TABLE IF NOT EXISTS corrections (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    bad_output  TEXT NOT NULL,
    good_output TEXT NOT NULL,
    correction_source TEXT DEFAULT 'user',
    used_for_training INTEGER DEFAULT 0,
    layer       INTEGER DEFAULT 3
);

CREATE TABLE IF NOT EXISTS hallucinations (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    interaction_id TEXT,
    claim       TEXT NOT NULL,
    evidence_against TEXT,
    severity    TEXT DEFAULT 'medium',
    layer       INTEGER DEFAULT 4
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    version     INTEGER NOT NULL,
    prompt_text TEXT NOT NULL,
    change_reason TEXT,
    changed_by  TEXT DEFAULT 'system',
    delta_summary TEXT,
    layer       INTEGER DEFAULT 6
);

CREATE TABLE IF NOT EXISTS agent_skills (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    agent       TEXT NOT NULL,
    skill_name  TEXT NOT NULL,
    score       REAL NOT NULL DEFAULT 0.5,
    evidence    TEXT,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta_patterns (
    id          TEXT PRIMARY KEY,
    ts          TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    source_layers TEXT,
    frequency   INTEGER DEFAULT 1,
    impact      TEXT DEFAULT 'medium',
    action_taken TEXT,
    layer       INTEGER DEFAULT 7
);
"""

_inited: set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _open(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure(db_path: str) -> None:
    if db_path in _inited:
        return
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = _open(db_path)
    conn.executescript(_DDL)
    conn.commit()
    conn.close()
    _inited.add(db_path)


class ForgeMemoryStore:
    """Shared memory layer for all Project Forge agents.

    Usage::

        store = ForgeMemoryStore()
        store.log_interaction(agent="critic", input_text="...", output_text="...")
        rows = store.query_interactions(agent="critic", limit=20)
    """

    def __init__(self, db_path: str | None = None):
        self._db = db_path or _DEFAULT_DB
        _ensure(self._db)

    # ------------------------------------------------------------------
    # Layer 1 — Raw interaction logs
    # ------------------------------------------------------------------

    def log_interaction(
        self,
        agent: str,
        input_text: str,
        output_text: str,
        task_id: str | None = None,
        model: str | None = None,
        duration_ms: int | None = None,
    ) -> str:
        row_id = str(uuid.uuid4())
        conn = _open(self._db)
        conn.execute(
            "INSERT INTO interactions (id, ts, agent, task_id, input_text, output_text, model, duration_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, _now(), agent, task_id, input_text, output_text, model, duration_ms),
        )
        conn.commit()
        conn.close()
        return row_id

    def query_interactions(
        self,
        agent: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        conn = _open(self._db)
        clauses, params = [], []
        if agent:
            clauses.append("agent = ?"); params.append(agent)
        if task_id:
            clauses.append("task_id = ?"); params.append(task_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM interactions {where} ORDER BY ts DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Layer 2 — Routing decision audit trail
    # ------------------------------------------------------------------

    def log_routing(
        self,
        agent: str,
        routed_to: str,
        reason: str | None = None,
        task_id: str | None = None,
        confidence: float | None = None,
        outcome: str = "unknown",
    ) -> str:
        row_id = str(uuid.uuid4())
        conn = _open(self._db)
        conn.execute(
            "INSERT INTO routing_decisions (id, ts, agent, task_id, routed_to, reason, confidence, outcome)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row_id, _now(), agent, task_id, routed_to, reason, confidence, outcome),
        )
        conn.commit()
        conn.close()
        return row_id

    def update_routing_outcome(self, routing_id: str, outcome: str) -> None:
        conn = _open(self._db)
        conn.execute(
            "UPDATE routing_decisions SET outcome = ? WHERE id = ?", (outcome, routing_id)
        )
        conn.commit()
        conn.close()

    def query_routing(
        self, agent: str | None = None, routed_to: str | None = None, limit: int = 50
    ) -> list[dict]:
        conn = _open(self._db)
        clauses, params = [], []
        if agent:
            clauses.append("agent = ?"); params.append(agent)
        if routed_to:
            clauses.append("routed_to = ?"); params.append(routed_to)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM routing_decisions {where} ORDER BY ts DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Layer 3 — User correction pairs (LoRA training data)
    # ------------------------------------------------------------------

    def log_correction(
        self,
        agent: str,
        bad_output: str,
        good_output: str,
        correction_source: str = "user",
    ) -> str:
        row_id = str(uuid.uuid4())
        conn = _open(self._db)
        conn.execute(
            "INSERT INTO corrections (id, ts, agent, bad_output, good_output, correction_source)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, _now(), agent, bad_output, good_output, correction_source),
        )
        conn.commit()
        conn.close()
        return row_id

    def get_training_pairs(self, agent: str | None = None, limit: int = 200) -> list[dict]:
        """Return correction pairs not yet used for training."""
        conn = _open(self._db)
        params: list[Any] = [0]  # used_for_training = 0
        where = "WHERE used_for_training = ?"
        if agent:
            where += " AND agent = ?"
            params.append(agent)
        rows = conn.execute(
            f"SELECT * FROM corrections {where} ORDER BY ts ASC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def mark_training_used(self, correction_ids: list[str]) -> None:
        conn = _open(self._db)
        conn.executemany(
            "UPDATE corrections SET used_for_training = 1 WHERE id = ?",
            [(cid,) for cid in correction_ids],
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # Layer 4 — Hallucination registry
    # ------------------------------------------------------------------

    def log_hallucination(
        self,
        agent: str,
        claim: str,
        interaction_id: str | None = None,
        evidence_against: str | None = None,
        severity: str = "medium",
    ) -> str:
        row_id = str(uuid.uuid4())
        conn = _open(self._db)
        conn.execute(
            "INSERT INTO hallucinations (id, ts, agent, interaction_id, claim, evidence_against, severity)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (row_id, _now(), agent, interaction_id, claim, evidence_against, severity),
        )
        conn.commit()
        conn.close()
        return row_id

    def query_hallucinations(
        self, agent: str | None = None, severity: str | None = None, limit: int = 50
    ) -> list[dict]:
        conn = _open(self._db)
        clauses, params = [], []
        if agent:
            clauses.append("agent = ?"); params.append(agent)
        if severity:
            clauses.append("severity = ?"); params.append(severity)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT * FROM hallucinations {where} ORDER BY ts DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Layer 6 — Prompt evolution history
    # ------------------------------------------------------------------

    def save_prompt_version(
        self,
        agent: str,
        prompt_text: str,
        change_reason: str | None = None,
        changed_by: str = "system",
        delta_summary: str | None = None,
    ) -> int:
        conn = _open(self._db)
        row = conn.execute(
            "SELECT MAX(version) FROM prompt_versions WHERE agent = ?", (agent,)
        ).fetchone()
        next_version = (row[0] or 0) + 1
        conn.execute(
            "INSERT INTO prompt_versions (id, ts, agent, version, prompt_text, change_reason, changed_by, delta_summary)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), _now(), agent, next_version, prompt_text,
             change_reason, changed_by, delta_summary),
        )
        conn.commit()
        conn.close()
        return next_version

    def get_prompt_history(self, agent: str, limit: int = 20) -> list[dict]:
        conn = _open(self._db)
        rows = conn.execute(
            "SELECT * FROM prompt_versions WHERE agent = ? ORDER BY version DESC LIMIT ?",
            (agent, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_current_prompt(self, agent: str) -> dict | None:
        conn = _open(self._db)
        row = conn.execute(
            "SELECT * FROM prompt_versions WHERE agent = ? ORDER BY version DESC LIMIT 1",
            (agent,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Agent skills
    # ------------------------------------------------------------------

    def update_skill(
        self, agent: str, skill_name: str, score: float, evidence: str | None = None
    ) -> str:
        conn = _open(self._db)
        row = conn.execute(
            "SELECT id FROM agent_skills WHERE agent = ? AND skill_name = ?",
            (agent, skill_name),
        ).fetchone()
        now = _now()
        if row:
            conn.execute(
                "UPDATE agent_skills SET score = ?, evidence = ?, updated_at = ? WHERE id = ?",
                (score, evidence, now, row[0]),
            )
            skill_id = row[0]
        else:
            skill_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO agent_skills (id, ts, agent, skill_name, score, evidence, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (skill_id, now, agent, skill_name, score, evidence, now),
            )
        conn.commit()
        conn.close()
        return skill_id

    def get_skills(self, agent: str) -> list[dict]:
        conn = _open(self._db)
        rows = conn.execute(
            "SELECT * FROM agent_skills WHERE agent = ? ORDER BY skill_name", (agent,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_skills(self) -> dict[str, list[dict]]:
        conn = _open(self._db)
        rows = conn.execute("SELECT * FROM agent_skills ORDER BY agent, skill_name").fetchall()
        conn.close()
        result: dict[str, list[dict]] = {}
        for r in rows:
            d = dict(r)
            result.setdefault(d["agent"], []).append(d)
        return result

    # ------------------------------------------------------------------
    # Layer 7 — Meta-patterns
    # ------------------------------------------------------------------

    def log_meta_pattern(
        self,
        pattern: str,
        source_layers: list[int] | None = None,
        impact: str = "medium",
        action_taken: str | None = None,
    ) -> str:
        row_id = str(uuid.uuid4())
        conn = _open(self._db)
        existing = conn.execute(
            "SELECT id, frequency FROM meta_patterns WHERE pattern = ?", (pattern,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE meta_patterns SET frequency = frequency + 1, action_taken = ? WHERE id = ?",
                (action_taken, existing[0]),
            )
            conn.commit()
            conn.close()
            return existing[0]
        layers_str = json.dumps(source_layers or [])
        conn.execute(
            "INSERT INTO meta_patterns (id, ts, pattern, source_layers, impact, action_taken)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (row_id, _now(), pattern, layers_str, impact, action_taken),
        )
        conn.commit()
        conn.close()
        return row_id

    def query_meta_patterns(self, impact: str | None = None, limit: int = 50) -> list[dict]:
        conn = _open(self._db)
        where = ("WHERE impact = ?" if impact else "")
        params = ([impact] if impact else []) + [limit]
        rows = conn.execute(
            f"SELECT * FROM meta_patterns {where} ORDER BY frequency DESC LIMIT ?", params
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Stats / summary
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        """Layer counts and skill overview."""
        conn = _open(self._db)
        result = {
            "interactions": conn.execute("SELECT COUNT(*) FROM interactions").fetchone()[0],
            "routing_decisions": conn.execute("SELECT COUNT(*) FROM routing_decisions").fetchone()[0],
            "corrections": conn.execute("SELECT COUNT(*) FROM corrections").fetchone()[0],
            "hallucinations": conn.execute("SELECT COUNT(*) FROM hallucinations").fetchone()[0],
            "prompt_versions": conn.execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0],
            "agent_skills": conn.execute("SELECT COUNT(*) FROM agent_skills").fetchone()[0],
            "meta_patterns": conn.execute("SELECT COUNT(*) FROM meta_patterns").fetchone()[0],
        }
        conn.close()
        return result
