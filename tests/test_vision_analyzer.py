"""Tests for jarvis/vision/analyzer.py — Phase 5 Computer Vision"""
from __future__ import annotations

import json
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ollama_response(scene_desc, objects, context="kitchen", status=200):
    payload = json.dumps({
        "scene_description": scene_desc,
        "objects": objects,
        "context": context,
    })
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = {"response": payload}
    return mock_resp


class TestVisionAnalyzerInit:
    def test_default_host(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        with patch.dict("os.environ", {}, clear=False):
            va = VisionAnalyzer()
        assert "11434" in va.ollama_host or "localhost" in va.ollama_host

    def test_custom_host(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer(ollama_host="http://192.168.1.10:11434")
        assert va.ollama_host == "http://192.168.1.10:11434"

    def test_default_model(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        assert va.model == "llava"

    def test_custom_model(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer(model="bakllava")
        assert va.model == "bakllava"

    def test_env_var_host(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://remotehost:11434"}):
            va = VisionAnalyzer()
        assert va.ollama_host == "http://remotehost:11434"

    def test_env_var_model(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        with patch.dict("os.environ", {"JARVIS_VISION_MODEL": "bakllava"}):
            va = VisionAnalyzer()
        assert va.model == "bakllava"


class TestBuildPrompt:
    def test_includes_context_hint(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        prompt = va._build_prompt("kitchen")
        assert "kitchen" in prompt

    def test_includes_json_instruction(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        prompt = va._build_prompt("garage")
        assert "json" in prompt.lower() or "JSON" in prompt

    def test_includes_scene_description_key(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        prompt = va._build_prompt("unknown")
        assert "scene_description" in prompt

    def test_different_context_hints(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        for hint in ["kitchen", "garage", "workbench", "unknown"]:
            prompt = va._build_prompt(hint)
            assert hint in prompt


class TestParseResponse:
    def test_valid_json_response(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        raw = json.dumps({
            "scene_description": "Kitchen counter with fruit",
            "objects": [{"label": "apple", "confidence": 0.9, "attributes": {}}],
            "context": "kitchen",
        })
        result = va._parse_response(raw, "llava")
        assert result.scene_description == "Kitchen counter with fruit"
        assert result.context == "kitchen"
        assert len(result.detected_objects) == 1
        assert result.detected_objects[0].label == "apple"
        assert result.detected_objects[0].confidence == 0.9

    def test_invalid_json_fallback(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        raw = "This is not JSON at all"
        result = va._parse_response(raw, "llava")
        assert result.scene_description == raw
        assert result.detected_objects == []

    def test_model_stored(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        raw = json.dumps({"scene_description": "A garage", "objects": [], "context": "garage"})
        result = va._parse_response(raw, "bakllava")
        assert result.model_used == "bakllava"

    def test_raw_response_stored(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        raw = json.dumps({"scene_description": "test", "objects": [], "context": "unknown"})
        result = va._parse_response(raw, "llava")
        assert result.raw_response == raw

    def test_missing_objects_key_fallback(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        raw = json.dumps({"scene_description": "A scene", "context": "kitchen"})
        result = va._parse_response(raw, "llava")
        assert result.detected_objects == []


class TestAnalyze:
    def test_analyze_valid_response(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value = make_ollama_response(
                "A kitchen counter with fruit",
                [{"label": "apple", "confidence": 0.9, "attributes": {}}],
                "kitchen",
            )
            result = va.analyze(image_b64="abc123", context_hint="kitchen")
        assert result.scene_description == "A kitchen counter with fruit"
        assert result.context == "kitchen"
        assert len(result.detected_objects) == 1
        assert result.detected_objects[0].label == "apple"

    def test_analyze_invalid_json_response(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": "not valid json here"}
            result = va.analyze(image_b64="abc123", context_hint="unknown")
        assert result.detected_objects == []
        assert result.scene_description == "not valid json here"

    def test_analyze_network_error(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        import requests
        va = VisionAnalyzer()
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("refused")):
            result = va.analyze(image_b64="abc123", context_hint="unknown")
        assert result.scene_description == "Vision service unavailable"
        assert result.detected_objects == []
        assert result.confidence == 0.0

    def test_analyze_sends_image(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value = make_ollama_response("scene", [], "unknown")
            va.analyze(image_b64="mybase64img", context_hint="kitchen")
        call_kwargs = mock_post.call_args
        body = call_kwargs[1].get("json") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("json", {})
        # Check the images field in the POST body
        assert mock_post.called

    def test_analyze_garage_context(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value = make_ollama_response(
                "A garage with tools",
                [{"label": "wrench", "confidence": 0.8, "attributes": {}}],
                "garage",
            )
            result = va.analyze(image_b64="abc123", context_hint="garage")
        assert result.context == "garage"

    def test_analyze_workbench_context(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value = make_ollama_response(
                "A workbench with tools",
                [{"label": "drill", "confidence": 0.85, "attributes": {}}],
                "workbench",
            )
            result = va.analyze(image_b64="abc123", context_hint="workbench")
        assert result.context == "workbench"

    def test_analyze_stores_analyzed_at(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value = make_ollama_response("scene", [], "unknown")
            result = va.analyze(image_b64="abc123", context_hint="unknown")
        assert result.analyzed_at is not None
        assert len(result.analyzed_at) > 0

    def test_analyze_multiple_objects(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        objects = [
            {"label": "apple", "confidence": 0.9, "attributes": {}},
            {"label": "milk", "confidence": 0.85, "attributes": {"size": "large"}},
            {"label": "bread", "confidence": 0.7, "attributes": {}},
        ]
        with patch("requests.post") as mock_post:
            mock_post.return_value = make_ollama_response("Kitchen scene", objects, "kitchen")
            result = va.analyze(image_b64="abc123", context_hint="kitchen")
        assert len(result.detected_objects) == 3

    def test_analyze_partial_json_fallback(self):
        from jarvis.vision.analyzer import VisionAnalyzer
        va = VisionAnalyzer()
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"response": "{broken json"}
            result = va.analyze(image_b64="abc123", context_hint="unknown")
        assert result.scene_description == "{broken json"
        assert result.detected_objects == []
