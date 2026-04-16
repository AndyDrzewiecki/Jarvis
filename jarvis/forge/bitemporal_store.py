"""BitemporalStore — knowledge store with two time axes for backtesting.

Two orthogonal timestamps are tracked for every fact:

  valid_from / valid_to   — when the fact is TRUE in the real world
                            (null valid_to = still true today)

  known_from / known_to   — when Jarvis became/ceased to be AWARE of this fact
                            (null known_to = currently known)

This enables:
  - Backtesting: "What did Jarvis know about X as of 2024-01-01?"
  - Temporal queries: "What financial facts were valid in Q3 2024?"
  - Audit trail: "When did we first learn that the prime rate changed?"

Schema example:
  A fact "prime_rate = 5.25%" learned on 2024-07-15, valid since 2023-07-26:
    key="prime_rate"
    value="5.25"
    valid_from="2023-07-26"
    valid_to=NULL          (still the current rate)
    known_from="2024-07-15"
    known_to=NULL          (we still know this)

  When the rate changes to 4.75%:
    Old fact: valid_to = "2024-11-07", known_to = NULL (we still know the old rate was valid)
    New fact: key="prime_rate" value="4.75" valid_from="2024-11-07" known_from="2024-11-07"
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "bitemporal.db"
)

_DDL = """
CREATE TABLE IF NOT EXISTS facts (
    id          TEXT PRIMARY KEY,
    domain      TEXT NOT NULL,       -- e.g. "finance", "smarthome", "security"
    key         TEXT NOT NULL,       -- fact name / entity
    value       TEXT NOT NULL,       -- fact value (JSON-encoded)
    source      TEXT,                -- where this fact came from
    confidence  REAL DEFAULT 1.0,   -- 0-1 confidence in this fact
    tags        TEXT DEFAULT '[]',   -- JSON list of tags for filtering
    -- Valid time (real-world truth period)
    valid_from  TEXT NOT NULL,
    valid_to    TEXT,                -- NULL = currently valid
    -- Transaction time (when Jarvis knew it)
    known_from  TEXT NOT NULL,
    known_to    TEXT,                -- NULL = currently known
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_domain_key  ON facts(domain, key);
CREATE INDEX IF NOT EXISTS idx_facts_valid_from  ON facts(valid_from);
CREATE INDEX IF NOT EXISTS idx_facts_known_from  ON facts(known_from);
CREATE INDEX IF NOT EXISTS idx_facts_valid_range  ON facts(valid_from, valid_to);
"""


@dataclass
class Fact:
    """A bitemporal fact record."""
    id: str
    domain: str
    key: str
    value: Any
    source: str
    confidence: float
    tags: list[str]
    valid_from: str
    valid_to: str | None
    known_from: str
    known_to: str | None
    created_at: str


class BitemporalStore:
    """Stores and queries facts with two independent time axes.

    Usage::

        store = BitemporalStore()

        # Record a fact
        fact_id = store.record(
            domain="finance",
            key="prime_rate",
            value=5.25,
            valid_from="2023-07-26",
            source="federal_reserve_api",
        )

        # Query current known facts
        facts = store.query_current(domain="finance", key="prime_rate")

        # Backtest: what did we know about prime_rate on 2024-01-01?
        facts = store.query_as_of(
            key="prime_rate",
            valid_at="2024-01-01",
            known_at="2024-01-01",
        )

        # Expire old fact when rate changes
        store.expire_fact(fact_id, valid_to="2024-11-07")
    """

    def __init__(self, db_path: str | None = None):
        self._db = db_path or _DEFAULT_DB
        os.makedirs(os.path.dirname(self._db), exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def record(
        self,
        domain: str,
        key: str,
        value: Any,
        valid_from: str,
        source: str = "",
        valid_to: str | None = None,
        confidence: float = 1.0,
        tags: list[str] | None = None,
        known_from: str | None = None,
    ) -> str:
        """Record a new fact.

        Args:
            domain:     Fact category (e.g. "finance", "security").
            key:        Fact name / entity identifier.
            value:      Fact value (any JSON-serializable type).
            valid_from: ISO date/datetime when the fact became true.
            source:     Where the fact came from.
            valid_to:   ISO date when the fact stopped being true (None = ongoing).
            confidence: How confident we are (0.0–1.0).
            tags:       Optional tags for filtering.
            known_from: When Jarvis became aware of this fact (default: now).

        Returns:
            Fact ID.
        """
        now = datetime.now(timezone.utc).isoformat()
        known_from = known_from or now
        fact_id = str(uuid.uuid4())
        conn = self._open()
        conn.execute(
            "INSERT INTO facts (id, domain, key, value, source, confidence, tags,"
            " valid_from, valid_to, known_from, known_to, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                fact_id, domain, key, json.dumps(value), source, confidence,
                json.dumps(tags or []), valid_from, valid_to, known_from, None, now,
            ),
        )
        conn.commit()
        conn.close()
        return fact_id

    def expire_fact(
        self,
        fact_id: str,
        valid_to: str | None = None,
        known_to: str | None = None,
    ) -> None:
        """Mark a fact as no longer valid or no longer known.

        Args:
            fact_id:  ID of the fact to expire.
            valid_to: When the fact stopped being true in the world.
            known_to: When we stopped knowing about this fact (rarely used).
        """
        now = datetime.now(timezone.utc).isoformat()
        updates: list[tuple] = []
        if valid_to is not None:
            updates.append(("valid_to", valid_to))
        if known_to is not None:
            updates.append(("known_to", known_to))
        if not updates:
            updates.append(("valid_to", now))

        conn = self._open()
        for col, val in updates:
            conn.execute(f"UPDATE facts SET {col} = ? WHERE id = ?", (val, fact_id))
        conn.commit()
        conn.close()

    def supersede(
        self,
        domain: str,
        key: str,
        new_value: Any,
        valid_from: str,
        source: str = "",
        confidence: float = 1.0,
    ) -> tuple[str, list[str]]:
        """Close all currently-valid facts for domain+key, then record a new one.

        Returns:
            (new_fact_id, list of expired_fact_ids)
        """
        now = datetime.now(timezone.utc).isoformat()

        # Expire all currently valid facts for this key
        conn = self._open()
        rows = conn.execute(
            "SELECT id FROM facts WHERE domain = ? AND key = ? AND valid_to IS NULL",
            (domain, key),
        ).fetchall()
        expired_ids = [r[0] for r in rows]
        for eid in expired_ids:
            conn.execute(
                "UPDATE facts SET valid_to = ? WHERE id = ?", (valid_from, eid)
            )
        conn.commit()
        conn.close()

        new_id = self.record(
            domain=domain,
            key=key,
            value=new_value,
            valid_from=valid_from,
            source=source,
            confidence=confidence,
        )
        return new_id, expired_ids

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def query_current(
        self,
        domain: str | None = None,
        key: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        """Return all facts currently valid AND currently known.

        This is the primary query for day-to-day operation.
        """
        now = datetime.now(timezone.utc).isoformat()
        return self._query(
            valid_at=now, known_at=now,
            domain=domain, key=key, tags=tags, limit=limit,
        )

    def query_as_of(
        self,
        valid_at: str,
        known_at: str | None = None,
        domain: str | None = None,
        key: str | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        """Backtest query: what did we know at a specific point in time?

        Args:
            valid_at:  ISO timestamp — return facts valid at this point.
            known_at:  ISO timestamp — return facts we knew at this point.
                       If None, defaults to valid_at (same-time query).
            domain:    Optional domain filter.
            key:       Optional key filter.

        Returns:
            List of facts that were both valid and known at the given timestamps.

        Example::
            # What was the prime rate in Q3 2024?
            facts = store.query_as_of(
                valid_at="2024-09-01",
                key="prime_rate",
            )
        """
        known = known_at or valid_at
        return self._query(
            valid_at=valid_at, known_at=known,
            domain=domain, key=key, limit=limit,
        )

    def history(
        self,
        domain: str,
        key: str,
        limit: int = 50,
    ) -> list[Fact]:
        """Return all versions of a fact (full history, not filtered by time)."""
        conn = self._open()
        rows = conn.execute(
            "SELECT * FROM facts WHERE domain = ? AND key = ?"
            " ORDER BY valid_from ASC LIMIT ?",
            (domain, key, limit),
        ).fetchall()
        conn.close()
        return [self._row_to_fact(dict(r)) for r in rows]

    def domains(self) -> list[str]:
        """Return all distinct domains in the store."""
        conn = self._open()
        rows = conn.execute("SELECT DISTINCT domain FROM facts ORDER BY domain").fetchall()
        conn.close()
        return [r[0] for r in rows]

    def summary(self) -> dict[str, Any]:
        """Return counts and coverage summary."""
        conn = self._open()
        total = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        current = conn.execute(
            "SELECT COUNT(*) FROM facts WHERE valid_to IS NULL AND known_to IS NULL"
        ).fetchone()[0]
        domains = conn.execute("SELECT COUNT(DISTINCT domain) FROM facts").fetchone()[0]
        keys = conn.execute("SELECT COUNT(DISTINCT key) FROM facts").fetchone()[0]
        oldest = conn.execute("SELECT MIN(valid_from) FROM facts").fetchone()[0]
        conn.close()
        return {
            "total_facts": total,
            "current_facts": current,
            "domains": domains,
            "unique_keys": keys,
            "oldest_valid_from": oldest,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _query(
        self,
        valid_at: str,
        known_at: str,
        domain: str | None = None,
        key: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        clauses = [
            "valid_from <= ?",
            "(valid_to IS NULL OR valid_to > ?)",
            "known_from <= ?",
            "(known_to IS NULL OR known_to > ?)",
        ]
        params: list[Any] = [valid_at, valid_at, known_at, known_at]

        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if key:
            clauses.append("key = ?")
            params.append(key)

        where = " AND ".join(clauses)
        conn = self._open()
        rows = conn.execute(
            f"SELECT * FROM facts WHERE {where} ORDER BY valid_from DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        conn.close()

        results = [self._row_to_fact(dict(r)) for r in rows]

        # Tag filter (post-query, since SQLite doesn't have native array contains)
        if tags:
            results = [
                f for f in results
                if any(t in f.tags for t in tags)
            ]

        return results

    def _row_to_fact(self, d: dict) -> Fact:
        return Fact(
            id=d["id"],
            domain=d["domain"],
            key=d["key"],
            value=json.loads(d["value"]),
            source=d.get("source") or "",
            confidence=d.get("confidence") or 1.0,
            tags=json.loads(d.get("tags") or "[]"),
            valid_from=d["valid_from"],
            valid_to=d.get("valid_to"),
            known_from=d["known_from"],
            known_to=d.get("known_to"),
            created_at=d["created_at"],
        )

    def _init_db(self) -> None:
        conn = self._open()
        conn.executescript(_DDL)
        conn.commit()
        conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn
