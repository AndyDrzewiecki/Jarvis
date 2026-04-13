from __future__ import annotations
import os, sqlite3, uuid
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "procedures.db")

_DDL = """
CREATE TABLE IF NOT EXISTS procedures (
    id TEXT PRIMARY KEY, trigger_pattern TEXT NOT NULL, action_sequence TEXT NOT NULL,
    confidence REAL DEFAULT 0.5, execution_count INTEGER DEFAULT 0, success_rate REAL DEFAULT 1.0,
    compiled_from TEXT, created_at TEXT NOT NULL, last_used TEXT
);
"""

_inited: set[str] = set()

def _open(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL)
    conn.commit()
    _inited.add(db_path)
    return conn

class ProceduralStore:
    def __init__(self, db_path: str = DB_PATH):
        self._db_path = db_path

    def add(self, trigger_pattern: str, action_sequence: str,
            confidence: float = 0.5, compiled_from: str | None = None) -> str:
        pid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO procedures (id,trigger_pattern,action_sequence,confidence,compiled_from,created_at) VALUES (?,?,?,?,?,?)",
                         (pid, trigger_pattern, action_sequence, confidence, compiled_from, datetime.now(timezone.utc).isoformat()))
            conn.commit(); conn.close()
        except Exception: pass
        return pid

    def match(self, user_message: str) -> dict | None:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("SELECT * FROM procedures WHERE confidence > 0.9 AND execution_count > 5 ORDER BY confidence DESC").fetchall()
            conn.close()
            msg_lower = user_message.lower()
            for row in rows:
                if row["trigger_pattern"].lower() in msg_lower:
                    return dict(row)
        except Exception: pass
        return None

    def reinforce(self, proc_id: str, success: bool = True) -> None:
        try:
            conn = _open(self._db_path)
            proc = conn.execute("SELECT * FROM procedures WHERE id=?", (proc_id,)).fetchone()
            if proc:
                new_count = proc["execution_count"] + 1
                new_rate = ((proc["success_rate"] * proc["execution_count"]) + (1.0 if success else 0.0)) / new_count
                conn.execute("UPDATE procedures SET execution_count=?, success_rate=?, last_used=? WHERE id=?",
                             (new_count, new_rate, datetime.now(timezone.utc).isoformat(), proc_id))
                conn.commit()
            conn.close()
        except Exception: pass

    def all(self) -> list[dict]:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("SELECT * FROM procedures ORDER BY confidence DESC").fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []
