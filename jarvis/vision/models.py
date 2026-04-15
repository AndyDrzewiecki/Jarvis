"""
Computer Vision data models for Jarvis Phase 5.
Uses Python stdlib dataclasses — no Pydantic dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DetectedObject:
    label: str                    # "apple", "car_battery", "wrench"
    confidence: float             # 0.0-1.0
    bounding_box: dict | None     # {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4} or None
    attributes: dict              # extra metadata

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "bounding_box": self.bounding_box,
            "attributes": self.attributes,
        }


@dataclass
class SceneAnalysis:
    scene_description: str        # natural language description
    detected_objects: list[DetectedObject]
    context: str                  # "kitchen", "garage", "workbench", "unknown"
    confidence: float
    raw_response: str             # raw LLM response
    model_used: str               # "llava", "bakllava", etc.
    analyzed_at: str              # ISO timestamp

    def to_dict(self) -> dict:
        return {
            "scene_description": self.scene_description,
            "detected_objects": [obj.to_dict() for obj in self.detected_objects],
            "context": self.context,
            "confidence": self.confidence,
            "raw_response": self.raw_response,
            "model_used": self.model_used,
            "analyzed_at": self.analyzed_at,
        }


@dataclass
class VisionEvent:
    event_id: str                 # uuid
    session_id: str | None        # camera session if streaming
    device_id: str                # which tablet/camera
    image_hash: str               # sha256 of image bytes for dedup
    analysis: SceneAnalysis
    knowledge_lake_ids: list[str] # IDs of facts stored in Knowledge Lake
    routed_to: list[str]          # adapter names that received this event
    created_at: str               # ISO timestamp

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "device_id": self.device_id,
            "image_hash": self.image_hash,
            "analysis": self.analysis.to_dict(),
            "knowledge_lake_ids": self.knowledge_lake_ids,
            "routed_to": self.routed_to,
            "created_at": self.created_at,
        }
