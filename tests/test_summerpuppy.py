"""Tests for SummerPuppyAdapter — mocked HTTP, auth header injection verified."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock, call
import requests

from jarvis.adapters.summerpuppy import SummerPuppyAdapter


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setenv("SUMMERPUPPY_TOKEN", "test-jwt-token")
    monkeypatch.setenv("SUMMERPUPPY_CUSTOMER_ID", "cust-001")
    return SummerPuppyAdapter()


def _ok(data):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = data
    m.raise_for_status = lambda: None
    return m


# ── metadata ─────────────────────────────────────────────────────────────────

def test_adapter_metadata(adapter):
    assert adapter.name == "summerpuppy"
    assert "dashboard_summary" in adapter.capabilities
    assert "trust_score" in adapter.capabilities
    assert len(adapter.capabilities) == 9


# ── auth header injection ─────────────────────────────────────────────────────

def test_dashboard_summary_sends_auth_header(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get", return_value=_ok({})) as mock_get:
        adapter.run("dashboard_summary", {})
    _, kwargs = mock_get.call_args
    assert "Authorization" in kwargs["headers"]
    assert kwargs["headers"]["Authorization"] == "Bearer test-jwt-token"


def test_trust_score_sends_auth_header(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get", return_value=_ok({"score": 88})) as mock_get:
        result = adapter.run("trust_score", {})
    assert result.success is True
    _, kwargs = mock_get.call_args
    assert "Bearer test-jwt-token" in kwargs["headers"]["Authorization"]


# ── successful capabilities ───────────────────────────────────────────────────

def test_dashboard_summary(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get", return_value=_ok({"alerts": 2})):
        result = adapter.run("dashboard_summary", {})
    assert result.success is True
    assert result.adapter == "summerpuppy"


def test_submit_event(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.post", return_value=_ok({"event_id": "ev-1"})):
        result = adapter.run("submit_event", {"type": "login", "ip": "1.2.3.4"})
    assert result.success is True
    assert "ev-1" in result.text


def test_event_status(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get", return_value=_ok({"status": "processed"})):
        result = adapter.run("event_status", {"event_id": "ev-1"})
    assert result.success is True


def test_event_status_missing_event_id(adapter):
    result = adapter.run("event_status", {})
    assert result.success is False
    assert "event_id" in result.text


def test_pending_approvals(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get", return_value=_ok([])):
        result = adapter.run("pending_approvals", {})
    assert result.success is True


# ── service-down fallback ─────────────────────────────────────────────────────

def test_service_down(adapter):
    with patch(
        "jarvis.adapters.summerpuppy.requests.get",
        side_effect=requests.exceptions.ConnectionError(),
    ):
        result = adapter.run("dashboard_summary", {})
    assert result.success is False
    assert "not reachable" in result.text


# ── missing config ────────────────────────────────────────────────────────────

def test_missing_token_returns_config_error(monkeypatch):
    monkeypatch.setenv("SUMMERPUPPY_TOKEN", "")
    monkeypatch.setenv("SUMMERPUPPY_CUSTOMER_ID", "cust-001")
    adapter = SummerPuppyAdapter()
    result = adapter.run("dashboard_summary", {})
    assert result.success is False
    assert "Configuration error" in result.text or "SUMMERPUPPY_TOKEN" in result.text


# ── new Sprint 3 capabilities ─────────────────────────────────────────────────

def test_approve_event_success(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.post",
               return_value=_ok({"approved": True})):
        result = adapter.run("approve_event", {"event_id": "ev-99", "approved": True, "reason": "ok"})
    assert result.success is True
    assert "ev-99" in result.text
    assert "approved" in result.text


def test_approve_event_missing_event_id(adapter):
    result = adapter.run("approve_event", {"approved": True})
    assert result.success is False
    assert "event_id" in result.text


def test_approve_event_reject(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.post",
               return_value=_ok({"approved": False})):
        result = adapter.run("approve_event", {"event_id": "ev-42", "approved": False, "reason": "no"})
    assert result.success is True
    assert "rejected" in result.text


def test_event_history(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get",
               return_value=_ok([{"id": "ev-1", "status": "processed"}])):
        result = adapter.run("event_history", {"hours": 12})
    assert result.success is True


def test_notification_channels(adapter):
    with patch("jarvis.adapters.summerpuppy.requests.get",
               return_value=_ok({"slack": True, "email": True})):
        result = adapter.run("notification_channels", {})
    assert result.success is True


def test_submit_and_wait_completes(adapter):
    """submit_and_wait polls until status is not RUNNING."""
    post_resp = _ok({"event_id": "ev-w1"})
    poll_running = _ok({"status": "RUNNING", "id": "ev-w1"})
    poll_done = _ok({"status": "COMPLETED", "id": "ev-w1"})

    with patch("jarvis.adapters.summerpuppy.requests.post", return_value=post_resp), \
         patch("jarvis.adapters.summerpuppy.requests.get",
               side_effect=[poll_running, poll_done]), \
         patch("jarvis.adapters.summerpuppy.time.sleep"):
        result = adapter.run("submit_and_wait", {"type": "scan"})

    assert result.success is True
    assert "COMPLETED" in result.text


def test_submit_and_wait_no_event_id(adapter):
    """If submit returns no event_id, return success immediately."""
    post_resp = _ok({"message": "queued"})  # no event_id
    with patch("jarvis.adapters.summerpuppy.requests.post", return_value=post_resp):
        result = adapter.run("submit_and_wait", {"type": "scan"})
    assert result.success is True
