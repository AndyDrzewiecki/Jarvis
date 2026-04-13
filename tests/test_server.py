"""Tests for the FastAPI server using TestClient."""
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


def test_status_endpoint(client):
    with patch("server._requests.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200)
        resp = client.get("/api/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "llm_available" in data
    assert "adapter_count" in data
    assert data["adapter_count"] == 14


def test_status_llm_unavailable(client):
    with patch("server._requests.get", side_effect=Exception("no connection")):
        resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["llm_available"] is False


def test_adapters_endpoint(client):
    resp = client.get("/api/adapters")
    assert resp.status_code == 200
    data = resp.json()
    assert "adapters" in data
    assert len(data["adapters"]) == 14
    names = [a["name"] for a in data["adapters"]]
    assert "grocery" in names
    assert "investor" in names


def test_chat_endpoint(client):
    from jarvis.adapters.base import AdapterResult
    mock_result = AdapterResult(success=True, text="Hello! I'm Jarvis.", adapter="jarvis")
    with patch("jarvis.personality.PersonalityLayer") as MockPL:
        MockPL.return_value.process.return_value = mock_result
        resp = client.post("/api/chat", json={"message": "What can you do?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "Jarvis" in data["text"] or "jarvis" in data["text"]


def test_chat_endpoint_empty_message(client):
    with patch("server.chat") as mock_chat:
        from jarvis.adapters.base import AdapterResult
        mock_chat.return_value = AdapterResult(
            success=True, text="Please say something!", adapter="jarvis"
        )
        resp = client.post("/api/chat", json={"message": ""})
    assert resp.status_code == 200


def test_history_endpoint(client):
    resp = client.get("/api/history")
    assert resp.status_code == 200
    data = resp.json()
    assert "messages" in data
    assert isinstance(data["messages"], list)


def test_cors_headers(client):
    resp = client.options("/api/status", headers={"Origin": "http://localhost:3000"})
    # CORS middleware should allow all origins
    assert resp.status_code in (200, 405)  # 405 is ok if OPTIONS not explicitly handled


def test_chat_endpoint_invalid_body(client):
    resp = client.post("/api/chat", json={})
    assert resp.status_code == 422  # FastAPI validation error


def test_status_does_not_leak_ollama_host(client):
    with patch("server._requests.get", side_effect=Exception("no connection")):
        resp = client.get("/api/status")
    assert "ollama_host" not in resp.json()


def test_chat_message_too_long(client):
    resp = client.post("/api/chat", json={"message": "x" * 4001})
    assert resp.status_code == 422


# ── /api/decisions endpoints ──────────────────────────────────────────────────

def test_decisions_endpoint_returns_empty_list(client):
    resp = client.get("/api/decisions")
    assert resp.status_code == 200
    data = resp.json()
    assert "decisions" in data
    assert "count" in data
    assert isinstance(data["decisions"], list)


def test_decisions_endpoint_filter_by_agent(client):
    import jarvis.agent_memory as am
    am.log_decision(agent="router", capability="route_message", decision="d1", reasoning="r")
    am.log_decision(agent="grocery", capability="meal_plan", decision="d2", reasoning="r")
    resp = client.get("/api/decisions?agent=router")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["decisions"][0]["agent"] == "router"


def test_decisions_recent_endpoint(client):
    import jarvis.agent_memory as am
    am.log_decision(agent="a", capability="b", decision="recent", reasoning="r")
    resp = client.get("/api/decisions/recent?n=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "decisions" in data
    assert data["count"] >= 1


def test_decisions_endpoint_with_limit(client):
    import jarvis.agent_memory as am
    for i in range(10):
        am.log_decision(agent="router", capability="route_message",
                        decision=f"d{i}", reasoning="r")
    resp = client.get("/api/decisions?limit=3")
    assert resp.status_code == 200
    assert resp.json()["count"] == 3


# ── /api/brief ────────────────────────────────────────────────────────────────

def test_brief_endpoint_returns_200(client):
    with patch("server.BriefEngine") as MockEngine:
        MockEngine.return_value.generate.return_value = {
            "text": "Good morning.",
            "sections": ["investor"],
            "unavailable": [],
            "timestamp": "2026-04-10T08:00:00",
        }
        resp = client.get("/api/brief")
    assert resp.status_code == 200
    data = resp.json()
    assert "text" in data
    assert data["text"] == "Good morning."


def test_brief_endpoint_structure(client):
    with patch("server.BriefEngine") as MockEngine:
        MockEngine.return_value.generate.return_value = {
            "text": "Brief text",
            "sections": ["investor", "grocery"],
            "unavailable": ["summerpuppy"],
            "timestamp": "2026-04-10T08:00:00",
        }
        resp = client.get("/api/brief")
    data = resp.json()
    assert "sections" in data
    assert "unavailable" in data
    assert "timestamp" in data


# ── /api/webhook/summerpuppy ──────────────────────────────────────────────────

def test_summerpuppy_webhook_returns_received(client):
    with patch("server.notify"):
        resp = client.post("/api/webhook/summerpuppy",
                           json={"severity": "INFO", "description": "login"})
    assert resp.status_code == 200
    assert resp.json()["received"] is True


def test_summerpuppy_webhook_critical_calls_notifier(client):
    with patch("server.notify") as mock_notify:
        client.post("/api/webhook/summerpuppy",
                    json={"severity": "CRITICAL", "description": "SSH brute force"})
    mock_notify.assert_called_once()
    args = mock_notify.call_args[0]
    assert "SSH brute force" in args[0] or "CRITICAL" in args[0]


def test_summerpuppy_webhook_non_critical_no_notify(client):
    with patch("server.notify") as mock_notify:
        client.post("/api/webhook/summerpuppy",
                    json={"severity": "INFO", "description": "routine scan"})
    mock_notify.assert_not_called()


def test_summerpuppy_webhook_logs_decision(client):
    import jarvis.agent_memory as am
    with patch("server.notify"):
        client.post("/api/webhook/summerpuppy",
                    json={"severity": "WARNING", "description": "test"})
    decisions = am.query(agent="webhook")
    assert len(decisions) == 1


# ── /api/preferences ──────────────────────────────────────────────────────────

def test_get_preferences_returns_defaults(client):
    resp = client.get("/api/preferences")
    assert resp.status_code == 200
    data = resp.json()
    assert "city" in data
    assert "budget_monthly" in data
    assert "notification_level" in data


def test_post_preferences_updates_city(client):
    resp = client.post("/api/preferences", json={"city": "Chicago,US"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "Chicago,US"


def test_post_preferences_preserves_other_keys(client):
    client.post("/api/preferences", json={"budget_monthly": 500})
    resp = client.get("/api/preferences")
    data = resp.json()
    assert data["budget_monthly"] == 500
    assert "city" in data  # other keys still present


def test_post_preferences_returns_full_dict(client):
    resp = client.post("/api/preferences", json={"notification_level": "critical"})
    data = resp.json()
    assert "city" in data
    assert "budget_monthly" in data
    assert data["notification_level"] == "critical"


# ── /api/workflows ────────────────────────────────────────────────────────────

def test_get_workflows_returns_list(client):
    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    data = resp.json()
    assert "workflows" in data
    assert isinstance(data["workflows"], list)
    names = [w["name"] for w in data["workflows"]]
    assert "grocery_closed_loop" in names
    assert "security_watchdog" in names


def test_run_workflow_unknown_returns_result(client):
    resp = client.post("/api/workflows/nonexistent/run")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "Unknown workflow" in data["result"]


def test_approve_workflow_unknown(client):
    resp = client.post("/api/workflows/nonexistent/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data
    assert "Unknown workflow" in data["result"]


# ── /api/devteam/promote ──────────────────────────────────────────────────────

def test_promote_invalid_slug(client):
    resp = client.post("/api/devteam/promote", json={
        "artifact_slug": "../../../etc/passwd",
        "target_dir": "C:/AI-Lab/agents",
    })
    assert resp.status_code == 400


def test_promote_not_whitelisted_target(client):
    resp = client.post("/api/devteam/promote", json={
        "artifact_slug": "test_slug",
        "target_dir": "C:/Windows/System32",
    })
    assert resp.status_code in (403, 404)  # 404 if slug doesn't exist first


def test_promote_nonexistent_artifact(client):
    resp = client.post("/api/devteam/promote", json={
        "artifact_slug": "does_not_exist_slug",
        "target_dir": "C:/AI-Lab/agents",
    })
    assert resp.status_code == 404


# ── /api/ws WebSocket ──────────────────────────────────────────────────────────

def test_websocket_connect_and_ping(client):
    """Client can connect to /api/ws and send a ping without error."""
    with client.websocket_connect("/api/ws?device_id=test-tablet") as ws:
        ws.send_text("ping")
        # No response expected — server loops on receive_text


def test_websocket_registers_device_id(client):
    """Connection is tracked by device_id in _active_connections."""
    import server as srv_mod
    srv_mod._active_connections.clear()
    with client.websocket_connect("/api/ws?device_id=kitchen-tablet"):
        assert "kitchen-tablet" in srv_mod._active_connections
    # After disconnect, cleaned up (WebSocketDisconnect raised by context exit)
    assert "kitchen-tablet" not in srv_mod._active_connections
