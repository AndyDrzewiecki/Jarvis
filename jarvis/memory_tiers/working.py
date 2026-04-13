from __future__ import annotations
import threading
import uuid
from datetime import datetime

class WorkingMemory:
    MAX_MESSAGES = 20

    def __init__(self):
        self._lock = threading.Lock()
        self._messages: list[dict] = []
        self._episode_id: str | None = None

    def add(self, role: str, text: str, adapter: str | None = None) -> str:
        entry_id = str(uuid.uuid4())
        with self._lock:
            self._messages.append({"id": entry_id, "role": role, "text": text,
                                    "adapter": adapter, "timestamp": datetime.now().isoformat()})
            if len(self._messages) > self.MAX_MESSAGES:
                self._messages = self._messages[-self.MAX_MESSAGES:]
        return entry_id

    def recent(self, n: int = 10) -> list[dict]:
        with self._lock:
            return list(self._messages[-n:])

    def search(self, query: str) -> list[dict]:
        q = query.lower()
        with self._lock:
            return [m for m in self._messages if q in m["text"].lower()]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()
            self._episode_id = None

    @property
    def current_episode_id(self) -> str | None:
        with self._lock:
            return self._episode_id

    @current_episode_id.setter
    def current_episode_id(self, value: str | None) -> None:
        with self._lock:
            self._episode_id = value
