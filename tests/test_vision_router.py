"""Tests for jarvis/vision/router.py — Phase 5 Computer Vision"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, call


def make_analysis(context="unknown", labels=None):
    from jarvis.vision.models import DetectedObject, SceneAnalysis
    objects = []
    if labels:
        objects = [DetectedObject(label=lbl, confidence=0.8, bounding_box=None, attributes={}) for lbl in labels]
    return SceneAnalysis(
        scene_description="A test scene",
        detected_objects=objects,
        context=context,
        confidence=0.7,
        raw_response="{}",
        model_used="llava",
        analyzed_at="2026-04-15T10:00:00",
    )


def make_event(event_id="evt-001", session_id=None, device_id="tablet-1"):
    from jarvis.vision.models import VisionEvent
    return VisionEvent(
        event_id=event_id,
        session_id=session_id,
        device_id=device_id,
        image_hash="hash001",
        analysis=make_analysis(),
        knowledge_lake_ids=[],
        routed_to=[],
        created_at="2026-04-15T10:00:00",
    )


@pytest.fixture
def mock_kl():
    kl = MagicMock()
    kl.store_fact.return_value = "kl-fact-id-001"
    return kl


@pytest.fixture
def router(mock_kl):
    from jarvis.vision.router import VisionRouter
    return VisionRouter(knowledge_lake=mock_kl)


class TestRoutingKitchen:
    def test_kitchen_context_routes_to_grocery(self, router):
        analysis = make_analysis(context="kitchen")
        event = make_event()
        routed = router.route(event, analysis)
        assert "grocery" in routed

    def test_food_objects_route_to_grocery(self, router):
        analysis = make_analysis(context="unknown", labels=["apple"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "grocery" in routed

    def test_multiple_food_objects(self, router):
        analysis = make_analysis(context="unknown", labels=["apple", "milk", "bread"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "grocery" in routed

    def test_kitchen_context_always_includes_knowledge_lake(self, router):
        analysis = make_analysis(context="kitchen")
        event = make_event()
        routed = router.route(event, analysis)
        assert "knowledge_lake" in routed


class TestRoutingCarMaintenance:
    def test_car_parts_route_to_car_maintenance(self, router):
        analysis = make_analysis(context="unknown", labels=["battery"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "car_maintenance" in routed

    def test_tire_routes_to_car_maintenance(self, router):
        analysis = make_analysis(context="unknown", labels=["tire"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "car_maintenance" in routed

    def test_multiple_car_parts(self, router):
        analysis = make_analysis(context="unknown", labels=["oil", "filter", "brake"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "car_maintenance" in routed


class TestRoutingTools:
    def test_tool_objects_route_to_project_tracking(self, router):
        analysis = make_analysis(context="unknown", labels=["wrench"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "project_tracking" in routed

    def test_workbench_context_routes_to_project_tracking(self, router):
        analysis = make_analysis(context="workbench")
        event = make_event()
        routed = router.route(event, analysis)
        assert "project_tracking" in routed

    def test_drill_routes_to_project_tracking(self, router):
        analysis = make_analysis(context="unknown", labels=["drill"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "project_tracking" in routed


class TestRoutingGarage:
    def test_garage_context_routes_to_car_maintenance(self, router):
        analysis = make_analysis(context="garage")
        event = make_event()
        routed = router.route(event, analysis)
        assert "car_maintenance" in routed

    def test_garage_context_routes_to_project_tracking(self, router):
        analysis = make_analysis(context="garage")
        event = make_event()
        routed = router.route(event, analysis)
        assert "project_tracking" in routed

    def test_garage_context_always_includes_knowledge_lake(self, router):
        analysis = make_analysis(context="garage")
        event = make_event()
        routed = router.route(event, analysis)
        assert "knowledge_lake" in routed


class TestAlwaysKnowledgeLake:
    def test_empty_scene_still_routes_to_knowledge_lake(self, router):
        analysis = make_analysis(context="unknown", labels=None)
        event = make_event()
        routed = router.route(event, analysis)
        assert "knowledge_lake" in routed

    def test_kitchen_always_knowledge_lake(self, router):
        analysis = make_analysis(context="kitchen", labels=["apple"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "knowledge_lake" in routed


class TestMixedObjects:
    def test_food_and_tools_routes_both(self, router):
        analysis = make_analysis(context="unknown", labels=["apple", "wrench"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "grocery" in routed
        assert "project_tracking" in routed

    def test_car_and_tools_routes_both(self, router):
        analysis = make_analysis(context="unknown", labels=["battery", "wrench"])
        event = make_event()
        routed = router.route(event, analysis)
        assert "car_maintenance" in routed
        assert "project_tracking" in routed


class TestKnowledgeLakeStorage:
    def test_store_fact_called(self, router, mock_kl):
        analysis = make_analysis(context="kitchen")
        event = make_event()
        router.route(event, analysis)
        assert mock_kl.store_fact.called

    def test_store_fact_called_with_vision_domain(self, router, mock_kl):
        analysis = make_analysis(context="unknown")
        event = make_event()
        router.route(event, analysis)
        calls = mock_kl.store_fact.call_args_list
        domains = [c[1].get("domain") or c[0][0] for c in calls]
        assert any("vision" in str(d) for d in domains)

    def test_knowledge_lake_ids_returned(self, router, mock_kl):
        mock_kl.store_fact.return_value = "kl-test-id"
        analysis = make_analysis(context="kitchen")
        event = make_event()
        router.route(event, analysis)
        # The IDs are used internally; route should complete without error


class TestIdentifyRoutingContexts:
    def test_kitchen_context(self, router):
        analysis = make_analysis(context="kitchen")
        contexts = router._identify_routing_contexts(analysis)
        assert "grocery" in contexts

    def test_garage_context(self, router):
        analysis = make_analysis(context="garage")
        contexts = router._identify_routing_contexts(analysis)
        assert "car_maintenance" in contexts
        assert "project_tracking" in contexts

    def test_workbench_context(self, router):
        analysis = make_analysis(context="workbench")
        contexts = router._identify_routing_contexts(analysis)
        assert "project_tracking" in contexts

    def test_unknown_context_no_special_routing(self, router):
        analysis = make_analysis(context="unknown")
        contexts = router._identify_routing_contexts(analysis)
        # With no special objects, should not include domain-specific routes
        assert "grocery" not in contexts
        assert "car_maintenance" not in contexts
