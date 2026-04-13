"""Tests for the SSE streaming endpoint GET /api/chat/stream."""
from __future__ import annotations
import json
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from jarvis.adapters.base import AdapterResult


@pytest.fixture
def client(tmp_path, monkeypatch):
    import jarvis.memory as mem
    import jarvis.agent_memory as am
    monkeypatch.setattr(mem, "MEMORY_PATH", str(tmp_path / "memory.json"))
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))
    # Prevent scheduler from starting during tests
    monkeypatch.setattr("jarvis.scheduler.start", lambda: None)
    monkeypatch.setattr("jarvis.scheduler.stop", lambda: None)
    from server import app
    return TestClient(app)


def _parse_sse(text: str) -> list[dict]:
    """Parse raw SSE text into a list of event data dicts."""
    events = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    events.append(json.loads(payload))
                except Exception:
                    pass
    return events


# ── basic SSE behaviour ───────────────────────────────────────────────────────

def test_stream_endpoint_returns_200(client):
    with patch("server.chat") as mock_chat:
        mock_chat.return_value = AdapterResult(success=True, text="Hello!", adapter="jarvis")
        resp = client.get("/api/chat/stream", params={"message": "hello"})
    assert resp.status_code == 200


def test_stream_endpoint_content_type(client):
    with patch("server.chat") as mock_chat:
        mock_chat.return_value = AdapterResult(success=True, text="Hi", adapter="jarvis")
        resp = client.get("/api/chat/stream", params={"message": "hi"})
    assert "text/event-stream" in resp.headers.get("content-type", "")


def test_stream_endpoint_emits_done_event(client):
    with patch("server.chat") as mock_chat:
        mock_chat.return_value = AdapterResult(success=True, text="Done!", adapter="jarvis")
        resp = client.get("/api/chat/stream", params={"message": "test"})
    events = _parse_sse(resp.text)
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1


def test_stream_endpoint_emits_result_event(client):
    with patch("jarvis.personality.PersonalityLayer") as MockPL:
        MockPL.return_value.process.return_value = AdapterResult(success=True, text="Market update!", adapter="investor")
        resp = client.get("/api/chat/stream", params={"message": "market update"})
    events = _parse_sse(resp.text)
    result_events = [e for e in events if e.get("type") == "result"]
    assert len(result_events) == 1
    assert result_events[0]["success"] is True
    assert result_events[0]["text"] == "Market update!"
    assert result_events[0]["adapter"] == "investor"


def test_stream_endpoint_emits_status_events(client):
    with patch("server.chat") as mock_chat:
        mock_chat.return_value = AdapterResult(success=True, text="ok", adapter="jarvis")
        resp = client.get("/api/chat/stream", params={"message": "hello"})
    events = _parse_sse(resp.text)
    status_events = [e for e in events if e.get("type") == "status"]
    assert len(status_events) >= 1


def test_stream_endpoint_missing_message_param(client):
    resp = client.get("/api/chat/stream")
    assert resp.status_code == 422


def test_stream_endpoint_handles_chat_exception(client):
    with patch("jarvis.personality.PersonalityLayer") as MockPL:
        MockPL.return_value.process.side_effect = Exception("LLM exploded")
        resp = client.get("/api/chat/stream", params={"message": "crash"})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert "LLM exploded" in error_events[0]["text"]
