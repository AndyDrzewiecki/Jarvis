from __future__ import annotations
import logging
import os, sqlite3, uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

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

    def compile_from_episodes(self, episodes: list[dict], messages_by_episode: dict[str, list[dict]]) -> str | None:
        """Analyze similar episodes → extract common action sequence → create procedure."""
        transcripts = []
        for ep in episodes[:5]:
            msgs = messages_by_episode.get(ep["id"], [])
            lines = [f"{m['role']}: {m.get('content', '')[:100]}" for m in msgs[:10]]
            transcripts.append(f"Episode ({ep.get('domain', '?')}):\n" + "\n".join(lines))
        combined = "\n---\n".join(transcripts)
        prompt = (
            "These episodes show a repeated user pattern.\n\n"
            f"{combined}\n\n"
            "Extract the common trigger pattern and action sequence.\n"
            "TRIGGER: <what the user typically says/asks>\n"
            "ACTION: <what Jarvis should do — adapter:capability>\n"
            "CONFIDENCE: <0.0-1.0>\n"
            "If no clear pattern, output: NONE\n"
        )
        try:
            from jarvis.core import _ask_ollama
            from jarvis import config
            raw = _ask_ollama(prompt, model=config.FALLBACK_MODEL)
            return self._parse_compilation(raw, [ep["id"] for ep in episodes])
        except Exception as exc:
            logger.warning("Procedural compilation failed: %s", exc)
            return None

    def _parse_compilation(self, raw: str, episode_ids: list[str]) -> str | None:
        """Parse compilation response and create procedure if valid."""
        trigger = action = None
        confidence = 0.5
        for line in raw.strip().splitlines():
            line = line.strip()
            if line.startswith("TRIGGER:"):
                trigger = line[8:].strip()
            elif line.startswith("ACTION:"):
                action = line[7:].strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = max(0.0, min(1.0, float(line[11:].strip())))
                except ValueError:
                    pass
        if trigger and action and confidence >= 0.5:
            return self.add(
                trigger_pattern=trigger,
                action_sequence=action,
                confidence=confidence,
                compiled_from=",".join(episode_ids[:5]),
            )
        return None
