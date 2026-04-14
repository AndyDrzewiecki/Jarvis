from __future__ import annotations
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS library_catalog (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_url TEXT,
    summary TEXT,
    quality_score REAL DEFAULT 0.5,
    last_verified TEXT,
    added_at TEXT NOT NULL,
    tags TEXT DEFAULT '',
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS research_queue (
    id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    topic TEXT NOT NULL,
    priority TEXT DEFAULT 'normal',
    requested_by TEXT,
    status TEXT DEFAULT 'queued',
    queued_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    result_summary TEXT,
    result_catalog_ids TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LibraryCatalog:
    """Manages the Library of Alexandria catalog — tracks all research artifacts."""

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "library", "catalog.db")

    def _open(self) -> sqlite3.Connection:
        """Open DB connection, create tables if needed."""
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_CATALOG_DDL)
        conn.commit()
        return conn

    def add_entry(self, domain: str, title: str, source_type: str,
                  source_url: str | None = None, summary: str | None = None,
                  quality_score: float = 0.5, tags: str = "") -> str:
        """Add a new catalog entry. Returns entry ID."""
        entry_id = str(uuid.uuid4())
        try:
            conn = self._open()
            conn.execute(
                """INSERT INTO library_catalog
                   (id, domain, title, source_type, source_url, summary,
                    quality_score, last_verified, added_at, tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entry_id, domain, title, source_type, source_url, summary,
                 quality_score, _now(), _now(), tags),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Failed to add catalog entry: %s", exc)
        return entry_id

    def search(self, query: str, domain: str | None = None, limit: int = 20) -> list[dict]:
        """Search catalog entries by title/summary."""
        try:
            conn = self._open()
            sql = "SELECT * FROM library_catalog WHERE (title LIKE ? OR summary LIKE ?) AND status = 'active'"
            params: list = [f"%{query}%", f"%{query}%"]
            if domain:
                sql += " AND domain = ?"
                params.append(domain)
            sql += " ORDER BY quality_score DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_by_domain(self, domain: str, limit: int = 50) -> list[dict]:
        """Get all active catalog entries for a domain, newest first."""
        try:
            conn = self._open()
            rows = conn.execute(
                "SELECT * FROM library_catalog WHERE domain = ? AND status = 'active' ORDER BY added_at DESC LIMIT ?",
                (domain, limit),
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def queue_research(self, domain: str, topic: str, priority: str = "normal",
                       requested_by: str = "system") -> str:
        """Queue a research topic for investigation. Returns queue item ID."""
        rid = str(uuid.uuid4())
        try:
            conn = self._open()
            conn.execute(
                """INSERT INTO research_queue
                   (id, domain, topic, priority, requested_by, queued_at)
                   VALUES (?,?,?,?,?,?)""",
                (rid, domain, topic, priority, requested_by, _now()),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Failed to queue research: %s", exc)
        return rid

    def get_queue(self, domain: str | None = None, status: str = "queued") -> list[dict]:
        """Get research queue items ordered by priority."""
        try:
            conn = self._open()
            sql = "SELECT * FROM research_queue WHERE status = ?"
            params: list = [status]
            if domain:
                sql += " AND domain = ?"
                params.append(domain)
            sql += " ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, queued_at"
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def complete_research(self, research_id: str, result_summary: str,
                          catalog_ids: list[str] | None = None) -> None:
        """Mark a research queue item as completed."""
        try:
            conn = self._open()
            conn.execute(
                """UPDATE research_queue
                   SET status = 'completed', completed_at = ?, result_summary = ?,
                       result_catalog_ids = ?
                   WHERE id = ?""",
                (_now(), result_summary,
                 ",".join(catalog_ids) if catalog_ids else "", research_id),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Failed to complete research: %s", exc)
