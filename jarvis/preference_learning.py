from __future__ import annotations
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "data", "preference_learning.db")

_DDL = """
CREATE TABLE IF NOT EXISTS signals (
    id          TEXT PRIMARY KEY,
    domain      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    content     TEXT NOT NULL,
    context     TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preferences (
    id             TEXT PRIMARY KEY,
    domain         TEXT NOT NULL,
    rule           TEXT NOT NULL,
    confidence     REAL NOT NULL DEFAULT 0.5,
    conditions     TEXT,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
"""

_inited: set[str] = set()


def _open(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    for stmt in _DDL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    _inited.add(db_path)
    return conn


class PreferenceMiner:
    """Mines user preference rules from interaction signals.

    Signals are raw observations (explicit or implicit) about user behaviour.
    Rules are extracted via LLM and stored with confidence scores.
    """

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path

    def record_signal(
        self,
        domain: str,
        signal_type: str,
        content: str,
        context: str = "",
    ) -> str:
        """Record a raw preference signal. Returns signal id."""
        sig_id = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute(
                "INSERT INTO signals (id, domain, signal_type, content, context, created_at) VALUES (?,?,?,?,?,?)",
                (sig_id, domain, signal_type, content, context, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("PreferenceMiner.record_signal error: %s", exc)
        return sig_id

    def mine(self, domain: str | None = None, limit: int = 50) -> int:
        """Extract preference rules from recent signals via LLM. Returns count of rules upserted."""
        try:
            conn = _open(self._db_path)
            sql = "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?"
            params: list = [limit]
            if domain:
                sql = "SELECT * FROM signals WHERE domain=? ORDER BY created_at DESC LIMIT ?"
                params = [domain, limit]
            rows = conn.execute(sql, params).fetchall()
            conn.close()
        except Exception as exc:
            logger.warning("PreferenceMiner.mine: DB read error: %s", exc)
            return 0

        if not rows:
            return 0

        signals_text = "\n".join(
            f"- [{dict(r)['domain']}] {dict(r)['signal_type']}: {dict(r)['content']}"
            for r in rows[:30]
        )

        domain_ctx = f" in domain '{domain}'" if domain else ""
        prompt = (
            f"Analyze these user interaction signals{domain_ctx} and extract preference rules.\n\n"
            f"Signals:\n{signals_text}\n\n"
            "For each rule, respond on its own line:\n"
            "RULE: <rule description> | <confidence 0.0-1.0> | <conditions>\n\n"
            "If no clear preferences, respond: NONE\n"
            "Rules:"
        )

        try:
            from jarvis.core import _ask_ollama
            from jarvis import config
            raw = _ask_ollama(prompt, model=config.FALLBACK_MODEL)
        except Exception as exc:
            logger.warning("PreferenceMiner.mine LLM error: %s", exc)
            return 0

        rules = self._parse_rules(raw)
        count = 0
        for rule_dict in rules:
            try:
                self._upsert_preference(
                    domain=domain or "general",
                    rule=rule_dict["rule"],
                    confidence=rule_dict["confidence"],
                    conditions=rule_dict.get("conditions", ""),
                )
                count += 1
            except Exception as exc:
                logger.warning("PreferenceMiner.mine: upsert error: %s", exc)

        return count

    def _parse_rules(self, raw: str) -> list[dict]:
        """Parse 'RULE: rule | confidence | conditions' lines."""
        rules = []
        if not raw or raw.strip().upper() == "NONE":
            return rules

        for line in raw.strip().splitlines():
            line = line.strip()
            if not line.upper().startswith("RULE:"):
                continue
            rest = line[5:].strip()
            parts = [p.strip() for p in rest.split("|")]
            if len(parts) < 2:
                continue
            rule_text = parts[0]
            try:
                confidence = max(0.0, min(1.0, float(parts[1])))
            except (ValueError, IndexError):
                confidence = 0.5
            conditions = parts[2] if len(parts) > 2 else ""
            if rule_text:
                rules.append({
                    "rule": rule_text,
                    "confidence": confidence,
                    "conditions": conditions,
                })

        return rules

    def _upsert_preference(
        self,
        domain: str,
        rule: str,
        confidence: float,
        conditions: str = "",
    ) -> str:
        """Insert new preference or reinforce existing one. Returns preference id."""
        pref_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = _open(self._db_path)
            # Check for similar existing rule in same domain
            existing = conn.execute(
                "SELECT id, evidence_count FROM preferences WHERE domain=? AND rule=?",
                (domain, rule),
            ).fetchone()
            if existing:
                pref_id = existing["id"]
                new_count = existing["evidence_count"] + 1
                # Average the confidence
                old_conf = conn.execute(
                    "SELECT confidence FROM preferences WHERE id=?", (pref_id,)
                ).fetchone()["confidence"]
                avg_conf = (old_conf * (new_count - 1) + confidence) / new_count
                conn.execute(
                    "UPDATE preferences SET confidence=?, evidence_count=?, conditions=?, updated_at=? WHERE id=?",
                    (round(avg_conf, 4), new_count, conditions, now, pref_id),
                )
            else:
                conn.execute(
                    "INSERT INTO preferences (id, domain, rule, confidence, conditions, evidence_count, created_at, updated_at) "
                    "VALUES (?,?,?,?,?,1,?,?)",
                    (pref_id, domain, rule, confidence, conditions, now, now),
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("PreferenceMiner._upsert_preference error: %s", exc)
        return pref_id

    def get_preferences(
        self,
        domain: str | None = None,
        min_confidence: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        """Return stored preferences, optionally filtered by domain and confidence."""
        try:
            conn = _open(self._db_path)
            sql = "SELECT * FROM preferences WHERE confidence >= ?"
            params: list = [min_confidence]
            if domain:
                sql += " AND domain = ?"
                params.append(domain)
            sql += " ORDER BY confidence DESC, evidence_count DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("PreferenceMiner.get_preferences error: %s", exc)
            return []
