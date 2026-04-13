from __future__ import annotations
import sys, types, pytest
from unittest.mock import patch


def _fake_chromadb():
    class _FakeCol:
        def __init__(self): self._store = {}
        def add(self, ids, documents, metadatas):
            for i, d, m in zip(ids, documents, metadatas):
                self._store[i] = {"document": d, "metadata": m}
        def query(self, query_texts, n_results, where=None):
            items = list(self._store.items())[:n_results]
            return {"ids": [[i for i,_ in items]],
                    "documents": [[v["document"] for _,v in items]],
                    "metadatas": [[v["metadata"] for _,v in items]]}
        def get(self, **kwargs):
            return {"ids": [], "documents": [], "metadatas": []}
    class _FakeClient:
        def __init__(self): self._cols = {}
        def get_or_create_collection(self, name):
            if name not in self._cols: self._cols[name] = _FakeCol()
            return self._cols[name]
    mod = types.ModuleType("chromadb")
    c = _FakeClient()
    mod.Client = lambda: c
    mod.PersistentClient = lambda path: c
    return mod


@pytest.fixture(autouse=True)
def setup(tmp_path, monkeypatch):
    fake_chroma = _fake_chromadb()
    with patch.dict(sys.modules, {"chromadb": fake_chroma}):
        import jarvis.memory_bus as mb
        mb.reset_bus()
        monkeypatch.setattr(mb, "_DATA_DIR", str(tmp_path))
        yield
        mb.reset_bus()


def test_store_fact_returns_id():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    fid = lake.store_fact("grocery", "price", "chicken $2/lb", "test")
    assert isinstance(fid, str) and len(fid) == 36


def test_query_facts_returns_stored():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    lake.store_fact("grocery", "price", "milk $3", "test")
    results = lake.query_facts(domain="grocery", min_confidence=0.0)
    assert len(results) >= 1


def test_effective_confidence_decays_old_price():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    # Simulate a fact with an old timestamp
    old_fact = {"fact_type": "price", "confidence": 1.0,
                "updated_at": "2020-01-01T00:00:00+00:00"}
    conf = lake.effective_confidence(old_fact)
    assert conf < 0.01  # price decays fast over ~6 years


def test_effective_confidence_stable_for_fresh_fact():
    from jarvis.knowledge_lake import KnowledgeLake
    from datetime import datetime, timezone
    lake = KnowledgeLake()
    fresh_fact = {"fact_type": "price", "confidence": 0.9,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
    conf = lake.effective_confidence(fresh_fact)
    assert conf > 0.85  # barely decayed


def test_effective_confidence_note_decays_slower():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    # 30 days old price vs note — note should have higher effective confidence
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    price_fact = {"fact_type": "price", "confidence": 1.0, "updated_at": ts}
    note_fact = {"fact_type": "note", "confidence": 1.0, "updated_at": ts}
    assert lake.effective_confidence(price_fact) < lake.effective_confidence(note_fact)


def test_store_price_persists():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    pid = lake.store_price("milk", "Aldi", 2.89)
    assert isinstance(pid, str)


def test_store_budget_persists():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    bid = lake.store_budget("grocery", "2026-04", 800.0)
    assert isinstance(bid, str)


def test_recent_by_domain_returns_dict():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    lake.store_fact("grocery", "note", "prefer organic", "test")
    result = lake.recent_by_domain()
    assert isinstance(result, dict)
    assert "grocery" in result


def test_search_returns_list():
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    lake.store_fact("home", "note", "furnace filter", "test")
    results = lake.search("furnace")
    assert isinstance(results, list)
