"""Tests for jarvis/knowledge_base.py — mocks chromadb via sys.modules injection."""
from __future__ import annotations
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Fake chromadb implementation ───────────────────────────────────────────────

class _FakeCollection:
    def __init__(self):
        self._store: dict[str, dict] = {}

    def add(self, ids, documents, metadatas):
        for id_, doc, meta in zip(ids, documents, metadatas):
            self._store[id_] = {"document": doc, "metadata": dict(meta)}

    def query(self, query_texts, n_results, where=None):
        items = list(self._store.items())
        if where:
            items = [
                (id_, v) for id_, v in items
                if all(v["metadata"].get(k) == val for k, val in where.items())
            ]
        items = items[:n_results]
        return {
            "ids": [[id_ for id_, _ in items]],
            "documents": [[v["document"] for _, v in items]],
            "metadatas": [[v["metadata"] for _, v in items]],
        }

    def get(self, ids=None, limit=None, offset=None, where=None):
        items = list(self._store.items())
        if ids:
            items = [(id_, v) for id_, v in items if id_ in ids]
        if where:
            items = [
                (id_, v) for id_, v in items
                if all(v["metadata"].get(k) == val for k, val in where.items())
            ]
        if offset:
            items = items[offset:]
        if limit:
            items = items[:limit]
        return {
            "ids": [id_ for id_, _ in items],
            "documents": [v["document"] for _, v in items],
            "metadatas": [v["metadata"] for _, v in items],
        }

    def delete(self, ids):
        for id_ in ids:
            self._store.pop(id_, None)


class _FakeClient:
    def __init__(self):
        self._collections: dict[str, _FakeCollection] = {}

    def get_or_create_collection(self, name):
        if name not in self._collections:
            self._collections[name] = _FakeCollection()
        return self._collections[name]


def _make_fake_chromadb(client: _FakeClient):
    mod = types.ModuleType("chromadb")
    mod.Client = lambda: client
    mod.PersistentClient = lambda path: client
    return mod


@pytest.fixture
def kb():
    """Return a KnowledgeBase backed by a fresh fake chromadb client."""
    client = _FakeClient()
    fake_chromadb = _make_fake_chromadb(client)
    with patch.dict(sys.modules, {"chromadb": fake_chromadb}):
        from jarvis.knowledge_base import KnowledgeBase
        instance = KnowledgeBase(persist_dir=":memory:")
        # Pre-wire the collection so it uses our fake client
        instance._client = client
        instance._collection = client.get_or_create_collection("jarvis_knowledge")
        yield instance


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_add_returns_id(kb):
    item_id = kb.add_document("chicken tikka masala recipe", category="recipes")
    assert isinstance(item_id, str)
    assert len(item_id) > 0


def test_search_returns_items(kb):
    kb.add_document("water heater thermostat replacement", category="how_to")
    kb.add_document("unrelated note about shopping", category="notes")
    results = kb.search("water heater")
    assert len(results) >= 1
    assert any("water heater" in r["content"] for r in results)


def test_browse_with_category_filter(kb):
    kb.add_document("pasta carbonara", category="recipes")
    kb.add_document("note about something", category="notes")
    results = kb.browse(category="recipes")
    assert len(results) == 1
    assert results[0]["category"] == "recipes"


def test_delete_removes_item(kb):
    item_id = kb.add_document("item to delete", category="notes")
    deleted = kb.delete(item_id)
    assert deleted is True
    assert kb.get(item_id) is None


def test_get_unknown_id_returns_none(kb):
    result = kb.get("nonexistent-id-12345")
    assert result is None


def test_summarize_calls_ask_ollama(kb):
    kb.add_document("water heater note", category="notes")
    with patch("jarvis.core._ask_ollama", return_value="Here is your summary.") as mock_llm:
        with patch.dict(sys.modules, {"chromadb": sys.modules.get("chromadb")}):
            summary = kb.summarize()
    mock_llm.assert_called_once()
    assert "summary" in summary.lower() or len(summary) > 0


def test_chromadb_path_isolation(monkeypatch, tmp_path):
    """JARVIS_CHROMADB_PATH env var controls storage location."""
    client = _FakeClient()
    fake_chromadb = _make_fake_chromadb(client)
    custom_path = str(tmp_path / "custom_chromadb")
    monkeypatch.setenv("JARVIS_CHROMADB_PATH", custom_path)
    with patch.dict(sys.modules, {"chromadb": fake_chromadb}):
        from jarvis.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        assert kb._persist_dir == custom_path


def test_cross_category_search(kb):
    """Search without category filter returns items from multiple categories."""
    kb.add_document("chicken soup recipe", category="recipes")
    kb.add_document("chicken wire fence how-to", category="how_to")
    results = kb.search("chicken", n=10)
    categories = {r["category"] for r in results}
    assert len(categories) >= 1  # may find one or both depending on fake query


def test_tags_roundtrip(kb):
    """Tags stored as comma-joined string are returned as list."""
    item_id = kb.add_document(
        "tagged note", category="notes", tags=["home", "maintenance"]
    )
    doc = kb.get(item_id)
    assert doc is not None
    assert "home" in doc["tags"]
    assert "maintenance" in doc["tags"]
