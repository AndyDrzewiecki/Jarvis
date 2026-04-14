from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import jarvis.agent_memory as am


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db = str(tmp_path / "decisions.db")
    monkeypatch.setattr(am, "DB_PATH", db)
    am._inited.discard(db)


@pytest.fixture
def mock_lake():
    lake = MagicMock()
    lake.search.return_value = []
    lake.query_facts.return_value = []
    return lake


@pytest.fixture
def inspector(tmp_path, mock_lake):
    from jarvis.introspection import MemoryIntrospector
    insp = MemoryIntrospector()
    insp._lake = mock_lake
    return insp


def test_explain_recommendation_found(tmp_path, inspector, mock_lake):
    """Seed a decision → explain_recommendation returns dict with 'decision' key."""
    decision_id = am.log_decision(
        agent="router",
        capability="route_message",
        decision="Routing to grocery.shopping_list",
        reasoning="user asked for shopping list",
        outcome="success",
    )
    mock_lake.search.return_value = [{"id": "f1", "summary": "grocery preference"}]

    result = inspector.explain_recommendation(decision_id)
    assert "decision" in result
    assert result["decision"]["id"] == decision_id


def test_explain_recommendation_not_found(inspector):
    """No matching decision → returns dict with 'error' key."""
    result = inspector.explain_recommendation("nonexistent-id-12345")
    assert "error" in result


def test_knowledge_audit_empty(inspector, mock_lake):
    """No facts → returns status='empty'."""
    mock_lake.query_facts.return_value = []
    result = inspector.knowledge_audit()
    assert result.get("status") == "empty"


def test_knowledge_audit_counts(tmp_path, inspector, mock_lake):
    """3 facts with varying confidence → fact_count=3, confidence_distribution correct."""
    now = datetime.now(timezone.utc).isoformat()
    facts = [
        {"id": "f1", "domain": "grocery", "fact_type": "price", "confidence": 0.9, "updated_at": now},
        {"id": "f2", "domain": "grocery", "fact_type": "inventory", "confidence": 0.6, "updated_at": now},
        {"id": "f3", "domain": "finance", "fact_type": "budget", "confidence": 0.4, "updated_at": now},
    ]
    mock_lake.query_facts.return_value = facts

    result = inspector.knowledge_audit()
    assert result.get("fact_count") == 3
    dist = result.get("confidence_distribution", {})
    # 2 facts >= 0.5 → high_confidence, 1 fact < 0.5 → low_confidence
    assert dist.get("high_confidence", 0) == 2
    assert dist.get("low_confidence", 0) == 1


def test_knowledge_audit_stale_count(tmp_path, inspector, mock_lake):
    """2 facts updated 8 days ago → stale_count=2."""
    old_ts = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    facts = [
        {"id": f"f{i}", "domain": "grocery", "fact_type": "price", "confidence": 0.8, "updated_at": old_ts}
        for i in range(2)
    ]
    mock_lake.query_facts.return_value = facts

    result = inspector.knowledge_audit()
    assert result.get("stale_count", 0) == 2


def test_memory_diff_new_facts(tmp_path, inspector, mock_lake):
    """2 facts added after 'since' → new_count=2."""
    since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    now = datetime.now(timezone.utc).isoformat()
    facts = [
        {"id": f"f{i}", "domain": "grocery", "fact_type": "price", "confidence": 0.8,
         "created_at": now, "updated_at": now}
        for i in range(2)
    ]
    mock_lake.query_facts.return_value = facts

    result = inspector.memory_diff(since)
    assert result.get("new_count") == 2


def test_memory_diff_no_changes(tmp_path, inspector, mock_lake):
    """All facts before 'since' → new_count=0."""
    since = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    facts = [
        {"id": "f1", "domain": "grocery", "fact_type": "price", "confidence": 0.8,
         "created_at": old, "updated_at": old}
    ]
    mock_lake.query_facts.return_value = facts

    result = inspector.memory_diff(since)
    assert result.get("new_count") == 0
