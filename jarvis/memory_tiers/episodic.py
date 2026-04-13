from __future__ import annotations
import os, sqlite3, uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "episodes.db")

_DDL = """
CREATE TABLE IF NOT EXISTS episodes (
    id TEXT PRIMARY KEY, started_at TEXT NOT NULL, ended_at TEXT,
    summary TEXT, domain TEXT, satisfaction REAL DEFAULT 0.5, consolidated INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS episode_messages (
    id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, role TEXT NOT NULL,
    content TEXT NOT NULL, timestamp TEXT NOT NULL, adapter TEXT, entities TEXT
);
CREATE TABLE IF NOT EXISTS episode_decisions (
    id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, decision_id TEXT NOT NULL
);
"""

_inited: set[str] = set()

def _open(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    _inited.add(db_path)
    return conn

class EpisodicStore:
    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path

    def start_episode(self, domain: str | None = None) -> str:
        eid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO episodes (id, started_at, domain) VALUES (?,?,?)",
                         (eid, datetime.now().isoformat(), domain))
            conn.commit(); conn.close()
        except Exception: pass
        return eid

    def end_episode(self, episode_id: str, summary: str = "", satisfaction: float = 0.5) -> None:
        try:
            conn = _open(self._db_path)
            conn.execute("UPDATE episodes SET ended_at=?, summary=?, satisfaction=? WHERE id=?",
                         (datetime.now().isoformat(), summary, satisfaction, episode_id))
            conn.commit(); conn.close()
        except Exception: pass

    def add_message(self, episode_id: str, role: str, content: str,
                    adapter: str | None = None, entities: str | None = None) -> str:
        mid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO episode_messages (id,episode_id,role,content,timestamp,adapter,entities) VALUES (?,?,?,?,?,?,?)",
                         (mid, episode_id, role, content, datetime.now().isoformat(), adapter, entities))
            conn.commit(); conn.close()
        except Exception: pass
        return mid

    def link_decision(self, episode_id: str, decision_id: str) -> None:
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT OR IGNORE INTO episode_decisions (id,episode_id,decision_id) VALUES (?,?,?)",
                         (str(uuid.uuid4()), episode_id, decision_id))
            conn.commit(); conn.close()
        except Exception: pass

    def search(self, query: str, limit: int = 10) -> list[dict]:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("""SELECT DISTINCT e.* FROM episodes e
                LEFT JOIN episode_messages m ON e.id=m.episode_id
                WHERE m.content LIKE ? OR e.summary LIKE ?
                ORDER BY e.started_at DESC LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []

    def get_unconsolidated(self, limit: int = 20) -> list[dict]:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("SELECT * FROM episodes WHERE consolidated=0 AND ended_at IS NOT NULL ORDER BY started_at LIMIT ?", (limit,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []

    def mark_consolidated(self, episode_id: str) -> None:
        try:
            conn = _open(self._db_path)
            conn.execute("UPDATE episodes SET consolidated=1 WHERE id=?", (episode_id,))
            conn.commit(); conn.close()
        except Exception: pass

    def get_messages(self, episode_id: str) -> list[dict]:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("SELECT * FROM episode_messages WHERE episode_id=? ORDER BY timestamp", (episode_id,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []

    def prune(self, older_than_days: int = 90, min_satisfaction: float = 0.3) -> int:
        try:
            conn = _open(self._db_path)
            result = conn.execute(
                "DELETE FROM episodes WHERE started_at < datetime('now', ?) AND satisfaction < ? AND consolidated=1",
                (f"-{older_than_days} days", min_satisfaction))
            conn.commit(); count = result.rowcount; conn.close()
            return count
        except Exception: return 0
