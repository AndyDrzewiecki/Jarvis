"""
VisionPipeline: Orchestrates camera sessions, frame analysis, and event routing.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from jarvis.vision.models import VisionEvent


class VisionPipeline:
    def __init__(self, analyzer=None, router=None, store=None):
        self._analyzer = analyzer
        self._router = router
        self._store = store
        self._sessions: dict[str, dict] = {}

    def _get_analyzer(self):
        if self._analyzer is None:
            from jarvis.vision.analyzer import VisionAnalyzer
            self._analyzer = VisionAnalyzer()
        return self._analyzer

    def _get_router(self):
        if self._router is None:
            from jarvis.vision.router import VisionRouter
            self._router = VisionRouter()
        return self._router

    def _get_store(self):
        if self._store is None:
            from jarvis.vision.store import VisionStore
            self._store = VisionStore()
        return self._store

    @property
    def active_sessions(self) -> dict:
        return self._sessions

    def start_session(self, session_id: str, device_id: str, context: str = "unknown") -> dict:
        started_at = datetime.now(timezone.utc).isoformat()
        self._sessions[session_id] = {
            "session_id": session_id,
            "device_id": device_id,
            "context": context,
            "started_at": started_at,
            "frames_processed": 0,
        }
        return {
            "session_id": session_id,
            "device_id": device_id,
            "context": context,
            "status": "started",
            "started_at": started_at,
        }

    def stop_session(self, session_id: str) -> dict:
        session = self._sessions.pop(session_id, {})
        return {
            "session_id": session_id,
            "status": "stopped",
            "stats": {
                "frames_processed": session.get("frames_processed", 0),
                "started_at": session.get("started_at", ""),
            },
        }

    def submit_frame(self, session_id: str, image_b64: str) -> VisionEvent:
        if session_id not in self._sessions:
            raise ValueError(f"Session '{session_id}' not found. Call start_session first.")

        session = self._sessions[session_id]
        device_id = session["device_id"]
        context_hint = session.get("context", "unknown")

        # Compute image hash
        image_hash = hashlib.sha256(image_b64.encode()).hexdigest()[:16]

        # Analyze image
        analyzer = self._get_analyzer()
        analysis = analyzer.analyze(image_b64=image_b64, context_hint=context_hint, device_id=device_id)

        # Create event
        event = VisionEvent(
            event_id=str(uuid.uuid4()),
            session_id=session_id,
            device_id=device_id,
            image_hash=image_hash,
            analysis=analysis,
            knowledge_lake_ids=[],
            routed_to=[],
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Route event
        router = self._get_router()
        router.route(event, analysis)

        # Store event
        store = self._get_store()
        store.save_event(event)

        # Increment frame count
        session["frames_processed"] += 1

        return event

    def get_session_stats(self, session_id: str) -> dict | None:
        if session_id not in self._sessions:
            return None
        session = self._sessions[session_id]
        return {
            "session_id": session_id,
            "device_id": session["device_id"],
            "context": session.get("context", "unknown"),
            "frames_processed": session["frames_processed"],
            "started_at": session["started_at"],
        }
