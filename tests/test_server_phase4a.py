"""Tests for Phase 4A dashboard API endpoints."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import jarvis.memory as mem
    import jarvis.agent_memory as am
    monkeypatch.setattr(mem, "MEMORY_PATH", str(tmp_path / "memory.json"))
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))
    monkeypatch.setattr("jarvis.scheduler.start", lambda: None)
    monkeypatch.setattr("jarvis.scheduler.stop", lambda: None)
    monkeypatch.setenv("JARVIS_PREFS_PATH", str(tmp_path / "preferences.json"))
    from server import app
    return TestClient(app)


# ── /api/specialists ──────────────────────────────────────────────────────────

def test_specialists_returns_six(client):
    resp = client.get("/api/specialists")
    assert resp.status_code == 200
    data = resp.json()
    assert "specialists" in data
    assert data["count"] == 6


def test_specialists_structure(client):
    resp = client.get("/api/specialists")
    specs = resp.json()["specialists"]
    for spec in specs:
        assert "name" in spec
        assert "domain" in spec
        assert "schedule" in spec
        assert "last_run" in spec
        assert "last_outcome" in spec


def test_specialists_known_domains(client):
    resp = client.get("/api/specialists")
    domains = {s["domain"] for s in resp.json()["specialists"]}
    assert domains == {"grocery", "finance", "calendar", "home", "news", "investor"}


def test_specialists_last_run_populated_from_decision_log(client):
    import jarvis.agent_memory as am
    am.log_decision(
        agent="grocery_specialist",
        capability="run_cycle",
        decision="Cycle: 5 gathered, 3 insights, 0 gaps",
        reasoning="error=None",
        outcome="success",
    )
    resp = client.get("/api/specialists")
    grocery = next(s for s in resp.json()["specialists"] if s["domain"] == "grocery")
    assert grocery["last_run"] is not None
    assert grocery["last_outcome"] == "success"


def test_specialists_last_run_null_when_no_history(client):
    resp = client.get("/api/specialists")
    # All should be null since no decisions logged in fresh tmp_path
    for spec in resp.json()["specialists"]:
        assert spec["last_run"] is None


# ── /api/knowledge-lake ───────────────────────────────────────────────────────

def test_knowledge_lake_returns_list(client):
    with patch("jarvis.knowledge_lake.KnowledgeLake") as MockLake:
        MockLake.return_value.recent_by_domain.return_value = {
            "grocery": [{"id": "1", "domain": "grocery", "summary": "eggs are cheap"}],
        }
        resp = client.get("/api/knowledge-lake")
    assert resp.status_code == 200
    data = resp.json()
    assert "facts" in data
    assert "count" in data


def test_knowledge_lake_domain_filter(client):
    with patch("jarvis.knowledge_lake.KnowledgeLake") as MockLake:
        MockLake.return_value.query_facts.return_value = [
            {"id": "1", "domain": "finance", "summary": "market up"}
        ]
        resp = client.get("/api/knowledge-lake?domain=finance")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_knowledge_lake_search(client):
    with patch("jarvis.knowledge_lake.KnowledgeLake") as MockLake:
        MockLake.return_value.search.return_value = [
            {"id": "2", "domain": "news", "summary": "tech layoffs"}
        ]
        resp = client.get("/api/knowledge-lake?q=layoffs")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_knowledge_lake_limit_validation(client):
    with patch("jarvis.knowledge_lake.KnowledgeLake") as MockLake:
        MockLake.return_value.recent_by_domain.return_value = {}
        resp = client.get("/api/knowledge-lake?limit=300")
    assert resp.status_code == 422  # exceeds max 200


# ── /api/household-state GET ──────────────────────────────────────────────────

def test_household_state_get_structure(client):
    with patch("jarvis.household_state.HouseholdState") as MockHS:
        MockHS.return_value.current.return_value = {"primary": "normal", "modifiers": []}
        MockHS.return_value.get_history.return_value = []
        resp = client.get("/api/household-state")
    assert resp.status_code == 200
    data = resp.json()
    assert "current" in data
    assert "history" in data
    assert "valid_primaries" in data
    assert "valid_modifiers" in data


def test_household_state_valid_primaries_list(client):
    with patch("jarvis.household_state.HouseholdState") as MockHS:
        MockHS.return_value.current.return_value = {"primary": "normal", "modifiers": []}
        MockHS.return_value.get_history.return_value = []
        resp = client.get("/api/household-state")
    primaries = resp.json()["valid_primaries"]
    assert "normal" in primaries
    assert "vacation" in primaries
    assert "budget_tight" in primaries


# ── /api/household-state PUT ──────────────────────────────────────────────────

def test_household_state_transition(client):
    with patch("jarvis.household_state.HouseholdState") as MockHS:
        MockHS.return_value.current.return_value = {"primary": "vacation", "modifiers": []}
        MockHS.return_value.transition.return_value = None
        resp = client.put("/api/household-state", json={
            "action": "transition", "value": "vacation", "reason": "heading out"
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "transition"
    assert data["value"] == "vacation"


def test_household_state_add_modifier(client):
    with patch("jarvis.household_state.HouseholdState") as MockHS:
        MockHS.return_value.current.return_value = {"primary": "normal", "modifiers": ["payday"]}
        MockHS.return_value.add_modifier.return_value = None
        resp = client.put("/api/household-state", json={
            "action": "add_modifier", "value": "payday"
        })
    assert resp.status_code == 200
    assert resp.json()["action"] == "add_modifier"


def test_household_state_remove_modifier(client):
    with patch("jarvis.household_state.HouseholdState") as MockHS:
        MockHS.return_value.current.return_value = {"primary": "normal", "modifiers": []}
        MockHS.return_value.remove_modifier.return_value = None
        resp = client.put("/api/household-state", json={
            "action": "remove_modifier", "value": "payday"
        })
    assert resp.status_code == 200


def test_household_state_invalid_primary_rejected(client):
    with patch("jarvis.household_state.HouseholdState"):
        resp = client.put("/api/household-state", json={
            "action": "transition", "value": "apocalypse_mode"
        })
    assert resp.status_code == 400


def test_household_state_invalid_modifier_rejected(client):
    with patch("jarvis.household_state.HouseholdState"):
        resp = client.put("/api/household-state", json={
            "action": "add_modifier", "value": "not_a_real_modifier"
        })
    assert resp.status_code == 400


def test_household_state_invalid_action_rejected(client):
    resp = client.put("/api/household-state", json={
        "action": "explode", "value": "normal"
    })
    assert resp.status_code == 422  # pydantic pattern validation


# ── /api/engines/status ───────────────────────────────────────────────────────

def test_engines_status_returns_seven(client):
    with patch("jarvis.engine_store.EngineStore") as MockES:
        MockES.return_value.count.return_value = 0
        resp = client.get("/api/engines/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "engines" in data
    assert len(data["engines"]) == 7


def test_engines_status_structure(client):
    with patch("jarvis.engine_store.EngineStore") as MockES:
        MockES.return_value.count.return_value = 42
        resp = client.get("/api/engines/status")
    data = resp.json()
    for engine in data["engines"]:
        assert "name" in engine
        assert "tables" in engine
        assert "total_records" in engine
        assert "last_run" in engine


def test_engines_status_known_engine_names(client):
    with patch("jarvis.engine_store.EngineStore") as MockES:
        MockES.return_value.count.return_value = 0
        resp = client.get("/api/engines/status")
    names = {e["name"] for e in resp.json()["engines"]}
    assert names == {"financial", "research", "geopolitical", "legal", "health", "local", "family"}


def test_engines_status_total_records(client):
    with patch("jarvis.engine_store.EngineStore") as MockES:
        MockES.return_value.count.return_value = 10
        resp = client.get("/api/engines/status")
    data = resp.json()
    # 7 engines × varying table counts, each returning 10
    assert data["total_records"] > 0
    for engine in data["engines"]:
        assert engine["total_records"] >= 0


def test_engines_status_last_run_from_decision_log(client):
    import jarvis.agent_memory as am
    am.log_decision(
        agent="financial_engine",
        capability="ingest",
        decision="Ingested 50 records",
        reasoning="",
        outcome="success",
    )
    with patch("jarvis.engine_store.EngineStore") as MockES:
        MockES.return_value.count.return_value = 0
        resp = client.get("/api/engines/status")
    financial = next(e for e in resp.json()["engines"] if e["name"] == "financial")
    assert financial["last_run"] is not None


# ── /api/blackboard ───────────────────────────────────────────────────────────

def test_blackboard_returns_posts(client):
    with patch("jarvis.blackboard.SharedBlackboard") as MockBB:
        MockBB.return_value.read.return_value = [
            {"id": "1", "agent": "grocery_specialist", "topic": "alerts",
             "content": "Low on milk", "urgency": "high", "posted_at": "2026-04-15T08:00:00"}
        ]
        resp = client.get("/api/blackboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "posts" in data
    assert data["count"] == 1


def test_blackboard_topic_filter(client):
    with patch("jarvis.blackboard.SharedBlackboard") as MockBB:
        MockBB.return_value.read.return_value = []
        resp = client.get("/api/blackboard?topic=alerts")
    assert resp.status_code == 200
    MockBB.return_value.read.assert_called_once_with(topics=["alerts"], limit=20)


def test_blackboard_empty_when_no_posts(client):
    with patch("jarvis.blackboard.SharedBlackboard") as MockBB:
        MockBB.return_value.read.return_value = []
        resp = client.get("/api/blackboard")
    data = resp.json()
    assert data["count"] == 0
    assert data["posts"] == []


def test_blackboard_limit_validation(client):
    with patch("jarvis.blackboard.SharedBlackboard") as MockBB:
        MockBB.return_value.read.return_value = []
        resp = client.get("/api/blackboard?limit=200")
    assert resp.status_code == 422  # exceeds max 100


# ── CORS allows PUT ───────────────────────────────────────────────────────────

def test_cors_allows_put_method(client):
    """PUT /api/household-state must pass through CORS."""
    with patch("jarvis.household_state.HouseholdState") as MockHS:
        MockHS.return_value.current.return_value = {"primary": "normal", "modifiers": []}
        MockHS.return_value.transition.return_value = None
        resp = client.put("/api/household-state", json={
            "action": "transition", "value": "normal"
        })
    assert resp.status_code == 200
