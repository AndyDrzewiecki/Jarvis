from __future__ import annotations
import sys, types, pytest
from unittest.mock import patch


class _FakeCollection:
    def __init__(self):
        self._store: dict = {}
    def add(self, ids, documents, metadatas):
        for id_, doc, meta in zip(ids, documents, metadatas):
            self._store[id_] = {"document": doc, "metadata": dict(meta)}
    def query(self, query_texts, n_results, where=None):
        items = list(self._store.items())
        if where:
            items = [(id_, v) for id_, v in items
                     if all(v["metadata"].get(k) == val for k, val in where.items())]
        items = items[:n_results]
        return {"ids": [[i for i, _ in items]],
                "documents": [[v["document"] for _, v in items]],
                "metadatas": [[v["metadata"] for _, v in items]]}
    def get(self, ids=None, limit=None, offset=None, where=None):
        items = list(self._store.items())
        if ids:
            items = [(id_, v) for id_, v in items if id_ in ids]
        return {"ids": [i for i, _ in items],
                "documents": [v["document"] for _, v in items],
                "metadatas": [v["metadata"] for _, v in items]}
    def delete(self, ids):
        for id_ in ids: self._store.pop(id_, None)

class _FakeClient:
    def __init__(self):
        self._cols: dict = {}
    def get_or_create_collection(self, name):
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]

def _fake_chromadb():
    mod = types.ModuleType("chromadb")
    client = _FakeClient()
    mod.Client = lambda: client
    mod.PersistentClient = lambda path: client
    return mod, client


@pytest.fixture
def store(tmp_path):
    fake_chroma, fake_client = _fake_chromadb()
    with patch.dict(sys.modules, {"chromadb": fake_chroma}):
        from jarvis.memory_tiers.semantic import SemanticStore
        s = SemanticStore(data_dir=str(tmp_path), chromadb_path=":memory:")
        s._chroma_client = fake_client
        s._collection = fake_client.get_or_create_collection("jarvis_knowledge")
        yield s


def test_add_fact_returns_id(store):
    fid = store.add_fact("grocery", "price", "chicken $2/lb", "test_agent")
    assert isinstance(fid, str) and len(fid) == 36


def test_add_fact_creates_kb_index_row(store):
    fid = store.add_fact("grocery", "price", "milk $3/gal", "test_agent")
    facts = store.query_facts(domain="grocery")
    assert any(f["id"] == fid for f in facts)


def test_add_fact_creates_provenance_row(store):
    fid = store.add_fact("finance", "budget", "budget set $800", "finance_spec")
    prov = store.get_provenance(fid)
    assert len(prov) >= 1
    assert prov[0]["fact_id"] == fid


def test_search_returns_results(store):
    store.add_fact("grocery", "price", "chicken breast on sale", "test")
    results = store.search("chicken")
    assert len(results) >= 1


def test_query_facts_filters_by_domain(store):
    store.add_fact("grocery", "price", "apple $1", "test")
    store.add_fact("finance", "budget", "budget $800", "test")
    results = store.query_facts(domain="grocery")
    assert all(r["domain"] == "grocery" for r in results)


def test_query_facts_filters_by_type(store):
    store.add_fact("grocery", "price", "banana $0.5", "test")
    store.add_fact("grocery", "note", "prefer organic", "test")
    results = store.query_facts(fact_type="price")
    assert all(r["fact_type"] == "price" for r in results)


def test_query_facts_respects_min_confidence(store):
    store.add_fact("home", "note", "low confidence note", "test", confidence=0.2)
    results = store.query_facts(min_confidence=0.5)
    assert all(r["confidence"] >= 0.5 for r in results)


def test_add_link_persists(store):
    fid1 = store.add_fact("grocery", "price", "chicken $2", "test")
    fid2 = store.add_fact("finance", "budget", "budget $800", "test")
    lid = store.add_link(fid1, fid2, "affects", strength=0.7)
    assert isinstance(lid, str)


def test_get_links_returns_both_directions(store):
    fid1 = store.add_fact("a", "note", "fact1", "test")
    fid2 = store.add_fact("b", "note", "fact2", "test")
    store.add_link(fid1, fid2, "supports")
    links1 = store.get_links(fid1)
    links2 = store.get_links(fid2)
    assert len(links1) >= 1
    assert len(links2) >= 1


def test_store_price_persists(store):
    pid = store.store_price("milk", "Aldi", 2.89)
    assert isinstance(pid, str) and len(pid) == 36


def test_store_schedule_persists(store):
    sid = store.store_schedule("Soccer practice", "Emma", "2026-04-15T16:00:00")
    assert isinstance(sid, str)


def test_store_budget_persists(store):
    bid = store.store_budget("grocery", "2026-04", 800.0)
    assert isinstance(bid, str)


def test_store_inventory_persists(store):
    iid = store.store_inventory("milk", category="fridge", quantity=1)
    assert isinstance(iid, str)


def test_store_maintenance_persists(store):
    mid = store.store_maintenance("furnace filter", interval_days=90)
    assert isinstance(mid, str)


def test_recent_by_domain_groups_correctly(store):
    store.add_fact("grocery", "price", "chicken", "test")
    store.add_fact("finance", "budget", "budget", "test")
    store.add_fact("grocery", "note", "prefer organic", "test")
    result = store.recent_by_domain(limit_per_domain=5)
    assert "grocery" in result
    assert "finance" in result
    assert len(result["grocery"]) == 2
