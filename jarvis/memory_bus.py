from __future__ import annotations
import logging, os
from typing import Any, Protocol
from jarvis.memory_tiers.types import MemoryRecall
from jarvis.memory_tiers.working import WorkingMemory
from jarvis.memory_tiers.episodic import EpisodicStore
from jarvis.memory_tiers.semantic import SemanticStore
from jarvis.memory_tiers.procedural import ProceduralStore
from jarvis.memory_tiers.attention import AttentionGate

logger = logging.getLogger(__name__)
_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

class MemoryHook(Protocol):
    def on_event(self, event: str, **kwargs: Any) -> None: ...

class MemoryBus:
    def __init__(self, data_dir: str | None = None):
        d = data_dir or _DATA_DIR
        self.working = WorkingMemory()
        self.episodic = EpisodicStore(os.path.join(d, "episodes.db"))
        self.semantic = SemanticStore(data_dir=d)
        self.procedural = ProceduralStore(os.path.join(d, "procedures.db"))
        self._attention = AttentionGate()
        self._hooks: list[MemoryHook] = []

    def record_message(self, role: str, content: str, adapter: str | None = None) -> str:
        msg_id = self.working.add(role, content, adapter)
        episode_id = self.working.current_episode_id
        if episode_id:
            self.episodic.add_message(episode_id, role, content, adapter)
        self._emit("message_recorded", role=role, msg_id=msg_id, adapter=adapter)
        return msg_id

    def record_decision(self, agent: str, capability: str, **kwargs: Any) -> str:
        import jarvis.agent_memory as am
        decision_id = am.log_decision(agent=agent, capability=capability, **kwargs)
        episode_id = self.working.current_episode_id
        if episode_id:
            self.episodic.link_decision(episode_id, decision_id)
        self._emit("decision_recorded", agent=agent, capability=capability, decision_id=decision_id)
        return decision_id

    def recall(self, query: str, context: dict | None = None) -> MemoryRecall:
        result = MemoryRecall()
        result.working = self.working.search(query) or self.working.recent(5)
        try: result.episodic = self.episodic.search(query, limit=5)
        except Exception: pass
        try: result.semantic = self.semantic.search(query, n=5)
        except Exception: pass
        try:
            proc = self.procedural.match(query)
            if proc: result.procedural = [proc]
        except Exception: pass
        return result

    def context_for_prompt(self, user_message: str, token_budget: int = 2000) -> str:
        recall = self.recall(user_message)
        return self._attention.gate(user_message, recall, budget=token_budget)

    def start_episode(self, domain: str | None = None) -> str:
        eid = self.episodic.start_episode(domain)
        self.working.current_episode_id = eid
        return eid

    def end_episode(self, summary: str = "", satisfaction: float = 0.5) -> None:
        eid = self.working.current_episode_id
        if eid:
            self.episodic.end_episode(eid, summary, satisfaction)
            self.working.current_episode_id = None

    def register_hook(self, hook: MemoryHook) -> None:
        self._hooks.append(hook)

    def _emit(self, event: str, **kwargs: Any) -> None:
        for hook in self._hooks:
            try: hook.on_event(event, **kwargs)
            except Exception as e: logger.warning("Hook error %s: %s", event, e)

_bus: MemoryBus | None = None

def get_bus(data_dir: str | None = None) -> MemoryBus:
    global _bus
    if _bus is None:
        _bus = MemoryBus(data_dir=data_dir)
    return _bus

def reset_bus() -> None:
    global _bus
    _bus = None
