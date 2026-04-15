"""Tests for jarvis/vision/models.py — Phase 5 Computer Vision"""
from __future__ import annotations

import pytest
from dataclasses import asdict


# ---------------------------------------------------------------------------
# DetectedObject
# ---------------------------------------------------------------------------

class TestDetectedObject:
    def test_basic_creation(self):
        from jarvis.vision.models import DetectedObject
        obj = DetectedObject(label="apple", confidence=0.9, bounding_box=None, attributes={})
        assert obj.label == "apple"
        assert obj.confidence == 0.9
        assert obj.bounding_box is None
        assert obj.attributes == {}

    def test_with_bounding_box(self):
        from jarvis.vision.models import DetectedObject
        bb = {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}
        obj = DetectedObject(label="car_battery", confidence=0.85, bounding_box=bb, attributes={"color": "black"})
        assert obj.bounding_box == bb
        assert obj.attributes["color"] == "black"

    def test_to_dict(self):
        from jarvis.vision.models import DetectedObject
        obj = DetectedObject(label="wrench", confidence=0.75, bounding_box=None, attributes={"size": "large"})
        d = obj.to_dict()
        assert d["label"] == "wrench"
        assert d["confidence"] == 0.75
        assert d["bounding_box"] is None
        assert d["attributes"]["size"] == "large"

    def test_to_dict_with_bounding_box(self):
        from jarvis.vision.models import DetectedObject
        bb = {"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}
        obj = DetectedObject(label="milk", confidence=0.95, bounding_box=bb, attributes={})
        d = obj.to_dict()
        assert d["bounding_box"] == bb

    def test_confidence_range(self):
        from jarvis.vision.models import DetectedObject
        obj_low = DetectedObject(label="item", confidence=0.0, bounding_box=None, attributes={})
        obj_high = DetectedObject(label="item", confidence=1.0, bounding_box=None, attributes={})
        assert obj_low.confidence == 0.0
        assert obj_high.confidence == 1.0


# ---------------------------------------------------------------------------
# SceneAnalysis
# ---------------------------------------------------------------------------

class TestSceneAnalysis:
    def test_basic_creation(self):
        from jarvis.vision.models import SceneAnalysis
        sa = SceneAnalysis(
            scene_description="A kitchen counter",
            detected_objects=[],
            context="kitchen",
            confidence=0.8,
            raw_response="{}",
            model_used="llava",
            analyzed_at="2026-04-15T10:00:00",
        )
        assert sa.scene_description == "A kitchen counter"
        assert sa.context == "kitchen"
        assert sa.detected_objects == []
        assert sa.model_used == "llava"

    def test_with_objects(self):
        from jarvis.vision.models import DetectedObject, SceneAnalysis
        objs = [
            DetectedObject(label="apple", confidence=0.9, bounding_box=None, attributes={}),
            DetectedObject(label="bread", confidence=0.8, bounding_box=None, attributes={}),
        ]
        sa = SceneAnalysis(
            scene_description="Fruit on counter",
            detected_objects=objs,
            context="kitchen",
            confidence=0.85,
            raw_response="raw",
            model_used="llava",
            analyzed_at="2026-04-15T10:00:00",
        )
        assert len(sa.detected_objects) == 2
        assert sa.detected_objects[0].label == "apple"

    def test_to_dict(self):
        from jarvis.vision.models import DetectedObject, SceneAnalysis
        objs = [DetectedObject(label="wrench", confidence=0.7, bounding_box=None, attributes={})]
        sa = SceneAnalysis(
            scene_description="Workbench scene",
            detected_objects=objs,
            context="workbench",
            confidence=0.75,
            raw_response="...",
            model_used="bakllava",
            analyzed_at="2026-04-15T12:00:00",
        )
        d = sa.to_dict()
        assert d["scene_description"] == "Workbench scene"
        assert d["context"] == "workbench"
        assert d["confidence"] == 0.75
        assert d["model_used"] == "bakllava"
        assert len(d["detected_objects"]) == 1
        assert d["detected_objects"][0]["label"] == "wrench"

    def test_to_dict_includes_all_fields(self):
        from jarvis.vision.models import SceneAnalysis
        sa = SceneAnalysis(
            scene_description="desc",
            detected_objects=[],
            context="garage",
            confidence=0.5,
            raw_response="raw_text",
            model_used="llava",
            analyzed_at="2026-04-15T09:00:00",
        )
        d = sa.to_dict()
        for key in ["scene_description", "detected_objects", "context", "confidence", "raw_response", "model_used", "analyzed_at"]:
            assert key in d


# ---------------------------------------------------------------------------
# VisionEvent
# ---------------------------------------------------------------------------

class TestVisionEvent:
    def _make_analysis(self):
        from jarvis.vision.models import SceneAnalysis
        return SceneAnalysis(
            scene_description="A scene",
            detected_objects=[],
            context="unknown",
            confidence=0.6,
            raw_response="",
            model_used="llava",
            analyzed_at="2026-04-15T10:00:00",
        )

    def test_basic_creation(self):
        from jarvis.vision.models import VisionEvent
        event = VisionEvent(
            event_id="evt-001",
            session_id=None,
            device_id="tablet-kitchen",
            image_hash="abc123",
            analysis=self._make_analysis(),
            knowledge_lake_ids=[],
            routed_to=[],
            created_at="2026-04-15T10:00:00",
        )
        assert event.event_id == "evt-001"
        assert event.session_id is None
        assert event.device_id == "tablet-kitchen"
        assert event.image_hash == "abc123"

    def test_with_session(self):
        from jarvis.vision.models import VisionEvent
        event = VisionEvent(
            event_id="evt-002",
            session_id="session-123",
            device_id="tablet-garage",
            image_hash="def456",
            analysis=self._make_analysis(),
            knowledge_lake_ids=["kl-1", "kl-2"],
            routed_to=["grocery", "knowledge_lake"],
            created_at="2026-04-15T11:00:00",
        )
        assert event.session_id == "session-123"
        assert len(event.knowledge_lake_ids) == 2
        assert "grocery" in event.routed_to

    def test_to_dict(self):
        from jarvis.vision.models import VisionEvent
        event = VisionEvent(
            event_id="evt-003",
            session_id="sess-1",
            device_id="tablet-1",
            image_hash="hash123",
            analysis=self._make_analysis(),
            knowledge_lake_ids=["kl-1"],
            routed_to=["knowledge_lake"],
            created_at="2026-04-15T10:00:00",
        )
        d = event.to_dict()
        assert d["event_id"] == "evt-003"
        assert d["session_id"] == "sess-1"
        assert d["device_id"] == "tablet-1"
        assert d["image_hash"] == "hash123"
        assert "analysis" in d
        assert isinstance(d["analysis"], dict)
        assert d["knowledge_lake_ids"] == ["kl-1"]
        assert d["routed_to"] == ["knowledge_lake"]

    def test_to_dict_includes_all_fields(self):
        from jarvis.vision.models import VisionEvent
        event = VisionEvent(
            event_id="evt-004",
            session_id=None,
            device_id="d1",
            image_hash="h1",
            analysis=self._make_analysis(),
            knowledge_lake_ids=[],
            routed_to=[],
            created_at="2026-04-15T10:00:00",
        )
        d = event.to_dict()
        for key in ["event_id", "session_id", "device_id", "image_hash", "analysis", "knowledge_lake_ids", "routed_to", "created_at"]:
            assert key in d
