from __future__ import annotations
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS blackboard_posts (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    urgency TEXT DEFAULT 'normal',
    posted_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    read_by TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS blackboard_subscriptions (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    topic TEXT NOT NULL,
    subscribed_at TEXT NOT NULL,
    UNIQUE(agent, topic)
);
"""


class SharedBlackboard:
    """Real-time cross-specialist signals: events, alerts, requests.

    Specialists post signals and subscribe to topics. Entries expire after ttl_days.
    """

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "blackboard.db")

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        conn.commit()
        return conn

    def post(self, agent: str, topic: str, content: str,
             urgency: str = "normal", ttl_days: int = 7) -> str:
        """Post a signal to the blackboard. Returns post ID."""
        post_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        try:
            conn = self._open()
            conn.execute(
                "INSERT INTO blackboard_posts (id,agent,topic,content,urgency,posted_at,expires_at) VALUES (?,?,?,?,?,?,?)",
                (post_id, agent, topic, content, urgency,
                 now.isoformat(), (now + timedelta(days=ttl_days)).isoformat()),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Blackboard post failed: %s", exc)
        return post_id

    def read(self, topics: list[str] | None = None, since: str | None = None,
             agents: list[str] | None = None, limit: int = 50) -> list[dict]:
        """Read non-expired posts, optionally filtered by topic/agent/time."""
        try:
            conn = self._open()
            self._cleanup_expired(conn)
            now_str = datetime.now(timezone.utc).isoformat()
            sql = "SELECT * FROM blackboard_posts WHERE expires_at > ?"
            params: list = [now_str]
            if topics:
                sql += f" AND topic IN ({','.join('?'*len(topics))})"
                params.extend(topics)
            if agents:
                sql += f" AND agent IN ({','.join('?'*len(agents))})"
                params.extend(agents)
            if since:
                sql += " AND posted_at >= ?"
                params.append(since)
            sql += " ORDER BY CASE urgency WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 WHEN 'normal' THEN 2 ELSE 3 END, posted_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def subscribe(self, agent: str, topics: list[str]) -> None:
        """Subscribe an agent to one or more topics."""
        try:
            conn = self._open()
            now = datetime.now(timezone.utc).isoformat()
            for topic in topics:
                conn.execute(
                    "INSERT OR IGNORE INTO blackboard_subscriptions (id,agent,topic,subscribed_at) VALUES (?,?,?,?)",
                    (str(uuid.uuid4()), agent, topic, now),
                )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.warning("Blackboard subscribe failed: %s", exc)

    def get_subscriptions(self, agent: str) -> list[str]:
        """Get all topics an agent is subscribed to."""
        try:
            conn = self._open()
            rows = conn.execute("SELECT topic FROM blackboard_subscriptions WHERE agent=?", (agent,)).fetchall()
            conn.close()
            return [r["topic"] for r in rows]
        except Exception:
            return []

    def get_subscribers(self, topic: str) -> list[str]:
        """Get all agents subscribed to a topic."""
        try:
            conn = self._open()
            rows = conn.execute("SELECT agent FROM blackboard_subscriptions WHERE topic=?", (topic,)).fetchall()
            conn.close()
            return [r["agent"] for r in rows]
        except Exception:
            return []

    def _cleanup_expired(self, conn: sqlite3.Connection) -> int:
        """Remove expired posts. Returns count removed."""
        try:
            result = conn.execute(
                "DELETE FROM blackboard_posts WHERE expires_at < ?",
                (datetime.now(timezone.utc).isoformat(),),
            )
            conn.commit()
            return result.rowcount
        except Exception:
            return 0
