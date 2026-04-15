"""Tests for jarvis/vision/store.py — Phase 5 Computer Vision"""
from __future__ import annotations

import os
import tempfile
import pytest


def make_analysis(desc="A scene", context="unknown", obj_label=None):
    from jarvis.vision.models import DetectedObject, SceneAnalysis
    objects = []
    if obj_label:
        objects = [DetectedObject(label=obj_label, confidence=0.8, bounding_box=None, attributes={})]
    return SceneAnalysis(
        scene_description=desc,
        detected_objects=objects,
        context=context,
        confidence=0.7,
        raw_response="{}",
        model_used="llava",
        analyzed_at="2026-04-15T10:00:00",
    )


def make_event(event_id="evt-001", session_id=None, device_id="tablet-1", image_hash="hash001",
               context="unknown", obj_label=None):
    from jarvis.vision.models import VisionEvent
    return VisionEvent(
        event_id=event_id,
        session_id=session_id,
        device_id=device_id,
        image_hash=image_hash,
        analysis=make_analysis(context=context, obj_label=obj_label),
        knowledge_lake_ids=[],
        routed_to=[],
        created_at="2026-04-15T10:00:00",
    )


@pytest.fixture
def store(tmp_path):
    from jarvis.vision.store import VisionStore
    db_path = str(tmp_path / "test_vision.db")
    return VisionStore(db_path=db_path)


class TestVisionStoreInit:
    def test_creates_db(self, tmp_path):
        from jarvis.vision.store import VisionStore
        db_path = str(tmp_path / "new.db")
        store = VisionStore(db_path=db_path)
        assert os.path.exists(db_path)

    def test_creates_data_dir_if_missing(self, tmp_path):
        from jarvis.vision.store import VisionStore
        nested = str(tmp_path / "nested" / "subdir" / "vision.db")
        store = VisionStore(db_path=nested)
        assert os.path.exists(nested)

    def test_env_var_path(self, tmp_path, monkeypatch):
        from jarvis.vision.store import VisionStore
        db_path = str(tmp_path / "env_vision.db")
        monkeypatch.setenv("JARVIS_VISION_DB", db_path)
        store = VisionStore()
        assert os.path.exists(db_path)


class TestSaveAndGet:
    def test_save_returns_event_id(self, store):
        event = make_event()
        returned_id = store.save_event(event)
        assert returned_id == "evt-001"

    def test_get_existing_event(self, store):
        event = make_event(event_id="evt-get-1")
        store.save_event(event)
        retrieved = store.get_event("evt-get-1")
        assert retrieved is not None
        assert retrieved.event_id == "evt-get-1"

    def test_get_nonexistent_returns_none(self, store):
        result = store.get_event("nonexistent-id")
        assert result is None

    def test_save_preserves_device_id(self, store):
        event = make_event(event_id="evt-dev", device_id="tablet-kitchen")
        store.save_event(event)
        retrieved = store.get_event("evt-dev")
        assert retrieved.device_id == "tablet-kitchen"

    def test_save_preserves_session_id(self, store):
        event = make_event(event_id="evt-sess", session_id="session-abc")
        store.save_event(event)
        retrieved = store.get_event("evt-sess")
        assert retrieved.session_id == "session-abc"

    def test_save_preserves_analysis_context(self, store):
        event = make_event(event_id="evt-ctx", context="garage")
        store.save_event(event)
        retrieved = store.get_event("evt-ctx")
        assert retrieved.analysis.context == "garage"

    def test_save_preserves_detected_objects(self, store):
        event = make_event(event_id="evt-obj", obj_label="apple")
        store.save_event(event)
        retrieved = store.get_event("evt-obj")
        assert len(retrieved.analysis.detected_objects) == 1
        assert retrieved.analysis.detected_objects[0].label == "apple"


class TestRecentEvents:
    def test_empty_db_returns_empty_list(self, store):
        result = store.recent_events()
        assert result == []

    def test_returns_saved_events(self, store):
        for i in range(3):
            store.save_event(make_event(event_id=f"evt-{i}", image_hash=f"hash-{i}"))
        result = store.recent_events()
        assert len(result) == 3

    def test_respects_limit(self, store):
        for i in range(10):
            store.save_event(make_event(event_id=f"evt-{i}", image_hash=f"hash-{i}"))
        result = store.recent_events(limit=5)
        assert len(result) == 5

    def test_filters_by_device_id(self, store):
        store.save_event(make_event(event_id="e1", image_hash="h1", device_id="tablet-kitchen"))
        store.save_event(make_event(event_id="e2", image_hash="h2", device_id="tablet-garage"))
        store.save_event(make_event(event_id="e3", image_hash="h3", device_id="tablet-kitchen"))
        result = store.recent_events(device_id="tablet-kitchen")
        assert len(result) == 2
        assert all(e.device_id == "tablet-kitchen" for e in result)

    def test_filters_by_context(self, store):
        store.save_event(make_event(event_id="e1", image_hash="h1", context="kitchen"))
        store.save_event(make_event(event_id="e2", image_hash="h2", context="garage"))
        store.save_event(make_event(event_id="e3", image_hash="h3", context="kitchen"))
        result = store.recent_events(context="kitchen")
        assert len(result) == 2
        assert all(e.analysis.context == "kitchen" for e in result)

    def test_duplicate_image_hash_saves_both(self, store):
        """Dedup is upstream responsibility — store should save both."""
        store.save_event(make_event(event_id="e1", image_hash="samehash"))
        store.save_event(make_event(event_id="e2", image_hash="samehash"))
        result = store.recent_events()
        assert len(result) == 2


class TestEventsBySession:
    def test_empty_session_returns_empty(self, store):
        result = store.events_by_session("nonexistent-session")
        assert result == []

    def test_returns_events_for_session(self, store):
        store.save_event(make_event(event_id="e1", image_hash="h1", session_id="sess-1"))
        store.save_event(make_event(event_id="e2", image_hash="h2", session_id="sess-1"))
        store.save_event(make_event(event_id="e3", image_hash="h3", session_id="sess-2"))
        result = store.events_by_session("sess-1")
        assert len(result) == 2
        assert all(e.session_id == "sess-1" for e in result)

    def test_null_session_events_not_returned(self, store):
        store.save_event(make_event(event_id="e1", image_hash="h1", session_id=None))
        store.save_event(make_event(event_id="e2", image_hash="h2", session_id="sess-1"))
        result = store.events_by_session("sess-1")
        assert len(result) == 1
