"""Tests for jarvis.agent_memory — SQLite decision audit log."""
from __future__ import annotations
import pytest
import jarvis.agent_memory as am


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect DB to a fresh temp file for each test."""
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    # Reset migration cache so each test gets a clean state
    am._inited.discard(str(tmp_path / "decisions.db"))


# ── log_decision ─────────────────────────────────────────────────────────────

def test_log_decision_returns_id():
    entry_id = am.log_decision(
        agent="router", capability="route_message",
        decision="Routing to grocery.meal_plan", reasoning="LLM said grocery",
    )
    assert isinstance(entry_id, str)
    assert len(entry_id) == 36  # UUID4


def test_log_decision_persists_to_db(tmp_path, monkeypatch):
    path = str(tmp_path / "d2.db")
    monkeypatch.setattr(am, "DB_PATH", path)
    am._inited.discard(path)
    am.log_decision(agent="test", capability="cap", decision="d1", reasoning="r1")
    am.log_decision(agent="test", capability="cap", decision="d2", reasoning="r2")
    entries = am._load_all()
    assert len(entries) == 2
    assert entries[0]["decision"] == "d1"
    assert entries[1]["decision"] == "d2"


def test_log_decision_schema_fields():
    am.log_decision(
        agent="grocery", capability="meal_plan",
        decision="Executed meal_plan — success", reasoning="Here is your meal plan",
        confidence=0.9, outcome="success",
        linked_message_id="abc-123",
        params_summary="week=this", duration_ms=42,
    )
    entries = am._load_all()
    assert len(entries) == 1
    e = entries[0]
    assert e["agent"] == "grocery"
    assert e["capability"] == "meal_plan"
    assert e["outcome"] == "success"
    assert e["confidence"] == pytest.approx(0.9)
    assert e["linked_message_id"] == "abc-123"
    assert e["duration_ms"] == 42
    assert "timestamp" in e
    assert "id" in e


def test_log_decision_truncates_reasoning():
    long_reasoning = "x" * 2000
    am.log_decision(agent="a", capability="b", decision="d", reasoning=long_reasoning)
    e = am._load_all()[0]
    assert len(e["reasoning"]) == 1000


def test_log_decision_defaults():
    am.log_decision(agent="a", capability="b", decision="d", reasoning="r")
    e = am._load_all()[0]
    assert e["outcome"] == "unknown"
    assert e["confidence"] is None
    assert e["linked_message_id"] is None
    assert e["params_summary"] is None
    assert e["duration_ms"] is None


def test_log_decision_does_not_raise_on_bad_path(monkeypatch):
    monkeypatch.setattr(am, "DB_PATH", "/nonexistent/path/decisions.db")
    am._inited.discard("/nonexistent/path/decisions.db")
    result = am.log_decision(agent="a", capability="b", decision="d", reasoning="r")
    assert isinstance(result, str)


# ── query ────────────────────────────────────────────────────────────────────

def test_query_no_filter_returns_all():
    am.log_decision(agent="router", capability="route_message", decision="d1", reasoning="r")
    am.log_decision(agent="grocery", capability="meal_plan", decision="d2", reasoning="r")
    results = am.query()
    assert len(results) == 2


def test_query_filter_by_agent():
    am.log_decision(agent="router", capability="route_message", decision="d1", reasoning="r")
    am.log_decision(agent="grocery", capability="meal_plan", decision="d2", reasoning="r")
    results = am.query(agent="router")
    assert len(results) == 1
    assert results[0]["agent"] == "router"


def test_query_filter_by_capability():
    am.log_decision(agent="router", capability="route_message", decision="d1", reasoning="r")
    am.log_decision(agent="grocery", capability="meal_plan", decision="d2", reasoning="r")
    results = am.query(capability="meal_plan")
    assert len(results) == 1
    assert results[0]["capability"] == "meal_plan"


def test_query_limit():
    for i in range(10):
        am.log_decision(agent="router", capability="route_message",
                        decision=f"d{i}", reasoning="r")
    results = am.query(limit=3)
    assert len(results) == 3


def test_query_since_iso():
    am.log_decision(agent="a", capability="b", decision="old", reasoning="r")
    from datetime import datetime
    cutoff = datetime.now().isoformat()
    am.log_decision(agent="a", capability="b", decision="new", reasoning="r")
    results = am.query(since_iso=cutoff)
    assert len(results) == 1
    assert results[0]["decision"] == "new"


def test_query_returns_chronological_order():
    for i in range(5):
        am.log_decision(agent="a", capability="b", decision=f"d{i}", reasoning="r")
    results = am.query(limit=50)
    decisions = [r["decision"] for r in results]
    assert decisions == ["d0", "d1", "d2", "d3", "d4"]


# ── recent_decisions ──────────────────────────────────────────────────────────

def test_recent_decisions_returns_last_n():
    for i in range(5):
        am.log_decision(agent="a", capability="b", decision=f"d{i}", reasoning="r")
    results = am.recent_decisions(n=3)
    assert len(results) == 3
    assert results[-1]["decision"] == "d4"


def test_recent_decisions_empty_db():
    results = am.recent_decisions(n=20)
    assert results == []


# ── JSONL migration ───────────────────────────────────────────────────────────

def test_migrate_jsonl_on_first_open(tmp_path, monkeypatch):
    """Existing decisions.jsonl is imported into SQLite on first access."""
    import json
    import uuid
    from datetime import datetime

    jsonl = tmp_path / "decisions.jsonl"
    db = tmp_path / "decisions.db"
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "agent": "migrated_agent",
        "capability": "old_cap",
        "decision": "migrated decision",
        "reasoning": "from jsonl",
        "confidence": None,
        "outcome": "success",
        "linked_message_id": None,
        "params_summary": None,
        "duration_ms": None,
    }
    jsonl.write_text(json.dumps(entry) + "\n", encoding="utf-8")

    monkeypatch.setattr(am, "DB_PATH", str(db))
    am._inited.discard(str(db))

    entries = am._load_all()
    assert len(entries) == 1
    assert entries[0]["agent"] == "migrated_agent"
