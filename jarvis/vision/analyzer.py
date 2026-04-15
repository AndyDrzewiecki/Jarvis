"""
VisionAnalyzer: Sends images to Ollama multimodal LLM and parses responses.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

from jarvis.vision.models import DetectedObject, SceneAnalysis


class VisionAnalyzer:
    def __init__(self, ollama_host: str = None, model: str = None):
        self.ollama_host = (
            ollama_host
            or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        )
        self.model = (
            model
            or os.getenv("JARVIS_VISION_MODEL", "llava")
        )

    def _build_prompt(self, context_hint: str) -> str:
        return (
            f"You are analyzing an image from context: {context_hint}. "
            "Respond ONLY with valid JSON in this exact format: "
            '{"scene_description": "brief description", '
            '"objects": [{"label": "object_name", "confidence": 0.9, "attributes": {}}], '
            '"context": "kitchen|garage|workbench|unknown"} '
            "List all visible objects with their labels and confidence scores."
        )

    def _parse_response(self, raw: str, model: str) -> SceneAnalysis:
        analyzed_at = datetime.now(timezone.utc).isoformat()
        try:
            data = json.loads(raw)
            objects = []
            for obj in data.get("objects", []):
                objects.append(DetectedObject(
                    label=obj.get("label", "unknown"),
                    confidence=float(obj.get("confidence", 0.5)),
                    bounding_box=obj.get("bounding_box"),
                    attributes=obj.get("attributes", {}),
                ))
            return SceneAnalysis(
                scene_description=data.get("scene_description", raw),
                detected_objects=objects,
                context=data.get("context", "unknown"),
                confidence=float(data.get("confidence", 0.7)),
                raw_response=raw,
                model_used=model,
                analyzed_at=analyzed_at,
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return SceneAnalysis(
                scene_description=raw,
                detected_objects=[],
                context="unknown",
                confidence=0.0,
                raw_response=raw,
                model_used=model,
                analyzed_at=analyzed_at,
            )

    def analyze(self, image_b64: str, context_hint: str = "unknown", device_id: str = "unknown") -> SceneAnalysis:
        prompt = self._build_prompt(context_hint)
        url = f"{self.ollama_host}/api/generate"
        body = {
            "model": self.model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
        }
        try:
            resp = requests.post(url, json=body, timeout=60)
            data = resp.json()
            raw = data.get("response", "")
            return self._parse_response(raw, self.model)
        except requests.exceptions.ConnectionError:
            analyzed_at = datetime.now(timezone.utc).isoformat()
            return SceneAnalysis(
                scene_description="Vision service unavailable",
                detected_objects=[],
                context="unknown",
                confidence=0.0,
                raw_response="",
                model_used=self.model,
                analyzed_at=analyzed_at,
            )
