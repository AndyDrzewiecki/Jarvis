from __future__ import annotations
import sys, types, pytest
from unittest.mock import patch, MagicMock


def _fake_chromadb():
    class _FakeCol:
        def __init__(self):
            self._store = {}
        def add(self, ids, documents, metadatas):
            for i, d, m in zip(ids, documents, metadatas):
                self._store[i] = {"document": d, "metadata": m}
        def query(self, query_texts, n_results, where=None):
            items = list(self._store.items())[:n_results]
            return {"ids": [[i for i, _ in items]],
                    "documents": [[v["document"] for _, v in items]],
                    "metadatas": [[v["metadata"] for _, v in items]]}
        def get(self, **kwargs):
            return {"ids": [], "documents": [], "metadatas": []}
    class _FakeClient:
        def __init__(self): self._cols = {}
        def get_or_create_collection(self, name):
            if name not in self._cols: self._cols[name] = _FakeCol()
            return self._cols[name]
    mod = types.ModuleType("chromadb")
    client = _FakeClient()
    mod.Client = lambda: client
    mod.PersistentClient = lambda path: client
    return mod


@pytest.fixture(autouse=True)
def reset(tmp_path, monkeypatch):
    fake_chroma = _fake_chromadb()
    with patch.dict(sys.modules, {"chromadb": fake_chroma}):
        import jarvis.memory_bus as mb
        mb.reset_bus()
        monkeypatch.setattr(mb, "_DATA_DIR", str(tmp_path))
        yield
        mb.reset_bus()


def test_record_message_returns_id():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    mid = bus.record_message("user", "hello")
    assert isinstance(mid, str) and len(mid) == 36


def test_record_message_appears_in_working_memory():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    bus.record_message("user", "hello world")
    msgs = bus.working.recent()
    assert any("hello world" in m["text"] for m in msgs)


def test_recall_searches_working_memory():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    bus.record_message("user", "what is the weather")
    recall = bus.recall("weather")
    assert len(recall.working) > 0


def test_context_for_prompt_returns_string():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    bus.record_message("user", "test message")
    ctx = bus.context_for_prompt("test")
    assert isinstance(ctx, str)


def test_context_for_prompt_respects_budget():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    for i in range(10):
        bus.record_message("user", f"message {i} " * 50)
    ctx = bus.context_for_prompt("test", token_budget=100)
    assert len(ctx) <= 100 * 4 + 200  # small overhead allowance


def test_hook_fires_on_message_recorded():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    fired = []
    class Hook:
        def on_event(self, event, **kwargs):
            fired.append(event)
    bus.register_hook(Hook())
    bus.record_message("user", "test")
    assert "message_recorded" in fired


def test_hook_fires_on_decision_recorded(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    fired = []
    class Hook:
        def on_event(self, event, **kwargs):
            fired.append(event)
    bus.register_hook(Hook())
    bus.record_decision("router", "route_message", decision="test", reasoning="r")
    assert "decision_recorded" in fired


def test_start_episode_sets_working_episode_id():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    eid = bus.start_episode()
    assert bus.working.current_episode_id == eid


def test_end_episode_clears_episode_id():
    from jarvis.memory_bus import get_bus
    bus = get_bus()
    bus.start_episode()
    bus.end_episode(summary="done")
    assert bus.working.current_episode_id is None


def test_get_bus_returns_singleton():
    from jarvis.memory_bus import get_bus
    b1 = get_bus()
    b2 = get_bus()
    assert b1 is b2


def test_reset_bus_creates_fresh_instance():
    from jarvis.memory_bus import get_bus, reset_bus
    b1 = get_bus()
    reset_bus()
    b2 = get_bus()
    assert b1 is not b2
