"""
VisionRouter: Routes VisionEvents to appropriate adapters based on context + objects.
"""
from __future__ import annotations

from jarvis.vision.models import SceneAnalysis, VisionEvent


FOOD_KEYWORDS = {
    "apple", "banana", "milk", "bread", "cheese", "egg", "vegetable", "fruit",
    "meat", "chicken", "beef", "fish", "cereal", "juice", "yogurt", "butter",
    "rice", "pasta", "can", "bottle", "jar",
}

CAR_PART_KEYWORDS = {
    "battery", "tire", "filter", "brake", "oil", "spark_plug", "belt", "hose",
    "wiper", "headlight", "taillight", "caliper", "rotor", "alternator", "radiator",
}

TOOL_KEYWORDS = {
    "wrench", "screwdriver", "drill", "hammer", "saw", "plier", "clamp", "level",
    "tape_measure", "socket", "ratchet", "chisel", "sander", "grinder",
}


class VisionRouter:
    def __init__(self, knowledge_lake=None):
        self._kl = knowledge_lake

    def _identify_routing_contexts(self, analysis: SceneAnalysis) -> list[str]:
        contexts: set[str] = set()
        labels = {obj.label.lower() for obj in analysis.detected_objects}
        ctx = analysis.context.lower()

        if ctx == "kitchen" or labels & FOOD_KEYWORDS:
            contexts.add("grocery")

        if labels & CAR_PART_KEYWORDS:
            contexts.add("car_maintenance")

        if ctx == "workbench" or labels & TOOL_KEYWORDS:
            contexts.add("project_tracking")

        if ctx == "garage":
            contexts.add("car_maintenance")
            contexts.add("project_tracking")

        return list(contexts)

    def _store_to_knowledge_lake(self, event: VisionEvent, analysis: SceneAnalysis) -> list[str]:
        if self._kl is None:
            return []
        ids = []
        try:
            fact_id = self._kl.store_fact(
                domain="vision",
                fact_type="scene_observation",
                content=f"[{event.device_id}] {analysis.scene_description} (context: {analysis.context})",
                source_agent="vision_pipeline",
                confidence=analysis.confidence,
            )
            if fact_id:
                ids.append(fact_id)
        except Exception:
            pass
        return ids

    def route(self, event: VisionEvent, analysis: SceneAnalysis) -> list[str]:
        routing_contexts = self._identify_routing_contexts(analysis)
        routed: list[str] = ["knowledge_lake"]

        kl_ids = self._store_to_knowledge_lake(event, analysis)
        event.knowledge_lake_ids.extend(kl_ids)

        for ctx in routing_contexts:
            if ctx not in routed:
                routed.append(ctx)

        event.routed_to = routed
        return routed
