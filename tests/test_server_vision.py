"""Tests for vision API endpoints in server.py — Phase 5 Computer Vision"""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


def make_mock_analysis():
    from jarvis.vision.models import DetectedObject, SceneAnalysis
    return SceneAnalysis(
        scene_description="A kitchen counter with apples",
        detected_objects=[
            DetectedObject(label="apple", confidence=0.9, bounding_box=None, attributes={})
        ],
        context="kitchen",
        confidence=0.85,
        raw_response="{}",
        model_used="llava",
        analyzed_at="2026-04-15T10:00:00",
    )


def make_mock_event(event_id="evt-test"):
    from jarvis.vision.models import VisionEvent
    return VisionEvent(
        event_id=event_id,
        session_id=None,
        device_id="tablet-kitchen",
        image_hash="abc123",
        analysis=make_mock_analysis(),
        knowledge_lake_ids=["kl-001"],
        routed_to=["grocery", "knowledge_lake"],
        created_at="2026-04-15T10:00:00",
    )


@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock()
    event = make_mock_event()
    pipeline.submit_frame.return_value = event
    pipeline.start_session.return_value = {
        "session_id": "sess-test",
        "device_id": "tablet-garage",
        "status": "started",
        "started_at": "2026-04-15T10:00:00",
    }
    pipeline.stop_session.return_value = {
        "session_id": "sess-test",
        "status": "stopped",
        "stats": {"frames_processed": 5, "started_at": "2026-04-15T10:00:00"},
    }
    return pipeline


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.recent_events.return_value = [make_mock_event("e1"), make_mock_event("e2")]
    return store


@pytest.fixture
def client(mock_pipeline, mock_store):
    import server
    # Patch the pipeline and store at module level
    with patch.object(server, "_get_vision_pipeline", return_value=mock_pipeline), \
         patch.object(server, "_get_vision_store", return_value=mock_store):
        with TestClient(server.app) as c:
            yield c


class TestVisionAnalyzeEndpoint:
    def test_analyze_valid_payload(self, client):
        resp = client.post("/api/vision/analyze", json={
            "image_b64": "base64data",
            "context_hint": "kitchen",
            "device_id": "tablet-kitchen",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "event_id" in data
        assert "scene_description" in data
        assert "detected_objects" in data
        assert "context" in data
        assert "routed_to" in data

    def test_analyze_missing_image_b64(self, client):
        resp = client.post("/api/vision/analyze", json={
            "context_hint": "kitchen",
        })
        assert resp.status_code == 422

    def test_analyze_default_context(self, client):
        resp = client.post("/api/vision/analyze", json={
            "image_b64": "base64data",
        })
        assert resp.status_code == 200

    def test_analyze_returns_knowledge_lake_ids(self, client):
        resp = client.post("/api/vision/analyze", json={
            "image_b64": "base64data",
            "context_hint": "kitchen",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "knowledge_lake_ids" in data

    def test_analyze_response_has_event_id(self, client):
        resp = client.post("/api/vision/analyze", json={
            "image_b64": "somedata",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["event_id"] == "evt-test"


class TestVisionStreamEndpoint:
    def test_stream_start_action(self, client):
        resp = client.post("/api/vision/stream", json={
            "action": "start",
            "session_id": "sess-test",
            "device_id": "tablet-garage",
            "context": "garage",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert "session_id" in data

    def test_stream_stop_action(self, client):
        resp = client.post("/api/vision/stream", json={
            "action": "stop",
            "session_id": "sess-test",
            "device_id": "tablet-garage",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "stopped"

    def test_stream_invalid_action(self, client):
        resp = client.post("/api/vision/stream", json={
            "action": "invalid_action",
            "session_id": "sess-test",
            "device_id": "tablet-garage",
        })
        assert resp.status_code == 400

    def test_stream_missing_action(self, client):
        resp = client.post("/api/vision/stream", json={
            "session_id": "sess-test",
            "device_id": "tablet-garage",
        })
        assert resp.status_code == 422


class TestVisionEventsEndpoint:
    def test_events_returns_200(self, client):
        resp = client.get("/api/vision/events")
        assert resp.status_code == 200

    def test_events_returns_list(self, client):
        resp = client.get("/api/vision/events")
        data = resp.json()
        assert "events" in data
        assert "total" in data
        assert isinstance(data["events"], list)

    def test_events_default_limit(self, client, mock_store):
        client.get("/api/vision/events")
        mock_store.recent_events.assert_called_once()
        call_kwargs = mock_store.recent_events.call_args
        limit = call_kwargs[1].get("limit") if call_kwargs[1] else (call_kwargs[0][0] if call_kwargs[0] else 20)
        assert limit == 20

    def test_events_custom_limit(self, client, mock_store):
        client.get("/api/vision/events?limit=5")
        call_kwargs = mock_store.recent_events.call_args
        limit = call_kwargs[1].get("limit") if call_kwargs[1] else None
        assert limit == 5

    def test_events_device_id_filter(self, client, mock_store):
        client.get("/api/vision/events?device_id=tablet-1")
        call_kwargs = mock_store.recent_events.call_args
        device_id = call_kwargs[1].get("device_id") if call_kwargs[1] else None
        assert device_id == "tablet-1"

    def test_events_context_filter(self, client, mock_store):
        client.get("/api/vision/events?context=kitchen")
        call_kwargs = mock_store.recent_events.call_args
        context = call_kwargs[1].get("context") if call_kwargs[1] else None
        assert context == "kitchen"

    def test_events_total_matches_list(self, client):
        resp = client.get("/api/vision/events")
        data = resp.json()
        assert data["total"] == len(data["events"])
