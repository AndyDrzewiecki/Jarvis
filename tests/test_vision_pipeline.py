"""Tests for jarvis/vision/pipeline.py — Phase 5 Computer Vision"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def make_mock_analysis(context="unknown"):
    from jarvis.vision.models import SceneAnalysis, DetectedObject
    return SceneAnalysis(
        scene_description="A test scene",
        detected_objects=[DetectedObject(label="apple", confidence=0.9, bounding_box=None, attributes={})],
        context=context,
        confidence=0.8,
        raw_response="{}",
        model_used="llava",
        analyzed_at="2026-04-15T10:00:00",
    )


@pytest.fixture
def mock_analyzer():
    analyzer = MagicMock()
    analyzer.analyze.return_value = make_mock_analysis()
    return analyzer


@pytest.fixture
def mock_router():
    router = MagicMock()
    router.route.return_value = ["knowledge_lake"]
    router._store_to_knowledge_lake.return_value = ["kl-001"]
    return router


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.save_event.return_value = "evt-001"
    return store


@pytest.fixture
def pipeline(mock_analyzer, mock_router, mock_store):
    from jarvis.vision.pipeline import VisionPipeline
    return VisionPipeline(analyzer=mock_analyzer, router=mock_router, store=mock_store)


class TestStartSession:
    def test_start_returns_session_info(self, pipeline):
        result = pipeline.start_session("sess-1", "tablet-kitchen", context="kitchen")
        assert result["session_id"] == "sess-1"
        assert result["device_id"] == "tablet-kitchen"
        assert result["status"] == "started"

    def test_start_appears_in_active_sessions(self, pipeline):
        pipeline.start_session("sess-1", "tablet-kitchen")
        assert "sess-1" in pipeline.active_sessions

    def test_active_sessions_has_device_id(self, pipeline):
        pipeline.start_session("sess-2", "tablet-garage", context="garage")
        session = pipeline.active_sessions["sess-2"]
        assert session["device_id"] == "tablet-garage"

    def test_active_sessions_has_context(self, pipeline):
        pipeline.start_session("sess-3", "tablet-1", context="workbench")
        session = pipeline.active_sessions["sess-3"]
        assert session["context"] == "workbench"

    def test_start_initializes_frames_processed(self, pipeline):
        pipeline.start_session("sess-4", "tablet-1")
        session = pipeline.active_sessions["sess-4"]
        assert session["frames_processed"] == 0


class TestStopSession:
    def test_stop_returns_stats(self, pipeline):
        pipeline.start_session("sess-1", "tablet-1")
        result = pipeline.stop_session("sess-1")
        assert result["session_id"] == "sess-1"
        assert result["status"] == "stopped"

    def test_stop_removes_from_active(self, pipeline):
        pipeline.start_session("sess-1", "tablet-1")
        pipeline.stop_session("sess-1")
        assert "sess-1" not in pipeline.active_sessions

    def test_stop_returns_frame_count(self, pipeline, mock_analyzer, mock_store):
        pipeline.start_session("sess-1", "tablet-1")
        pipeline.submit_frame("sess-1", "img1")
        pipeline.submit_frame("sess-1", "img2")
        result = pipeline.stop_session("sess-1")
        assert result["stats"]["frames_processed"] == 2


class TestSubmitFrame:
    def test_submit_frame_returns_vision_event(self, pipeline):
        from jarvis.vision.models import VisionEvent
        pipeline.start_session("sess-1", "tablet-1")
        event = pipeline.submit_frame("sess-1", "base64imgdata")
        assert isinstance(event, VisionEvent)

    def test_submit_frame_increments_count(self, pipeline):
        pipeline.start_session("sess-1", "tablet-1")
        pipeline.submit_frame("sess-1", "img1")
        pipeline.submit_frame("sess-1", "img2")
        assert pipeline.active_sessions["sess-1"]["frames_processed"] == 2

    def test_submit_frame_calls_analyzer(self, pipeline, mock_analyzer):
        pipeline.start_session("sess-1", "tablet-1")
        pipeline.submit_frame("sess-1", "myimage")
        mock_analyzer.analyze.assert_called_once()

    def test_submit_frame_calls_store(self, pipeline, mock_store):
        pipeline.start_session("sess-1", "tablet-1")
        pipeline.submit_frame("sess-1", "myimage")
        mock_store.save_event.assert_called_once()

    def test_submit_to_nonexistent_session_raises(self, pipeline):
        with pytest.raises(ValueError):
            pipeline.submit_frame("nonexistent-sess", "img")

    def test_submit_frame_event_has_device_id(self, pipeline):
        pipeline.start_session("sess-1", "tablet-garage")
        event = pipeline.submit_frame("sess-1", "img1")
        assert event.device_id == "tablet-garage"

    def test_submit_frame_event_has_session_id(self, pipeline):
        pipeline.start_session("sess-1", "tablet-1")
        event = pipeline.submit_frame("sess-1", "img1")
        assert event.session_id == "sess-1"

    def test_submit_frame_event_has_image_hash(self, pipeline):
        pipeline.start_session("sess-1", "tablet-1")
        event = pipeline.submit_frame("sess-1", "img1")
        assert event.image_hash is not None
        assert len(event.image_hash) > 0


class TestGetSessionStats:
    def test_stats_for_active_session(self, pipeline):
        pipeline.start_session("sess-1", "tablet-1")
        stats = pipeline.get_session_stats("sess-1")
        assert stats["session_id"] == "sess-1"
        assert "frames_processed" in stats
        assert "started_at" in stats

    def test_stats_nonexistent_session_returns_none(self, pipeline):
        stats = pipeline.get_session_stats("nonexistent")
        assert stats is None


class TestMultipleSessions:
    def test_multiple_concurrent_sessions(self, pipeline):
        pipeline.start_session("sess-a", "tablet-1")
        pipeline.start_session("sess-b", "tablet-2")
        assert "sess-a" in pipeline.active_sessions
        assert "sess-b" in pipeline.active_sessions

    def test_stop_one_keeps_other(self, pipeline):
        pipeline.start_session("sess-a", "tablet-1")
        pipeline.start_session("sess-b", "tablet-2")
        pipeline.stop_session("sess-a")
        assert "sess-a" not in pipeline.active_sessions
        assert "sess-b" in pipeline.active_sessions

    def test_frames_tracked_per_session(self, pipeline):
        pipeline.start_session("sess-a", "tablet-1")
        pipeline.start_session("sess-b", "tablet-2")
        pipeline.submit_frame("sess-a", "img1")
        pipeline.submit_frame("sess-a", "img2")
        pipeline.submit_frame("sess-b", "img3")
        assert pipeline.active_sessions["sess-a"]["frames_processed"] == 2
        assert pipeline.active_sessions["sess-b"]["frames_processed"] == 1
