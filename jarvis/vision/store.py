"""
VisionStore: SQLite-backed persistence for VisionEvent objects.
"""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Optional

from jarvis.vision.models import DetectedObject, SceneAnalysis, VisionEvent


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS vision_events (
    event_id TEXT PRIMARY KEY,
    session_id TEXT,
    device_id TEXT NOT NULL,
    image_hash TEXT NOT NULL,
    scene_description TEXT,
    detected_objects TEXT,
    context TEXT,
    confidence REAL,
    model_used TEXT,
    knowledge_lake_ids TEXT,
    routed_to TEXT,
    created_at TEXT,
    analyzed_at TEXT
)
"""


class VisionStore:
    def __init__(self, db_path: str = None):
        self.db_path = (
            db_path
            or os.getenv("JARVIS_VISION_DB", "data/vision_events.db")
        )
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(_CREATE_TABLE)
            conn.commit()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save_event(self, event: VisionEvent) -> str:
        analysis = event.analysis
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO vision_events
                (event_id, session_id, device_id, image_hash, scene_description,
                 detected_objects, context, confidence, model_used,
                 knowledge_lake_ids, routed_to, created_at, analyzed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    event.event_id,
                    event.session_id,
                    event.device_id,
                    event.image_hash,
                    analysis.scene_description,
                    json.dumps([obj.to_dict() for obj in analysis.detected_objects]),
                    analysis.context,
                    analysis.confidence,
                    analysis.model_used,
                    json.dumps(event.knowledge_lake_ids),
                    json.dumps(event.routed_to),
                    event.created_at,
                    analysis.analyzed_at,
                ),
            )
            conn.commit()
        return event.event_id

    def _row_to_event(self, row: sqlite3.Row) -> VisionEvent:
        detected_raw = json.loads(row["detected_objects"] or "[]")
        objects = [
            DetectedObject(
                label=o.get("label", "unknown"),
                confidence=float(o.get("confidence", 0.5)),
                bounding_box=o.get("bounding_box"),
                attributes=o.get("attributes", {}),
            )
            for o in detected_raw
        ]
        analysis = SceneAnalysis(
            scene_description=row["scene_description"] or "",
            detected_objects=objects,
            context=row["context"] or "unknown",
            confidence=float(row["confidence"] or 0.0),
            raw_response="",
            model_used=row["model_used"] or "unknown",
            analyzed_at=row["analyzed_at"] or "",
        )
        return VisionEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            device_id=row["device_id"],
            image_hash=row["image_hash"],
            analysis=analysis,
            knowledge_lake_ids=json.loads(row["knowledge_lake_ids"] or "[]"),
            routed_to=json.loads(row["routed_to"] or "[]"),
            created_at=row["created_at"] or "",
        )

    def get_event(self, event_id: str) -> VisionEvent | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM vision_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_event(row)

    def recent_events(
        self,
        limit: int = 20,
        device_id: str | None = None,
        context: str | None = None,
    ) -> list[VisionEvent]:
        conditions = []
        params: list = []
        if device_id is not None:
            conditions.append("device_id = ?")
            params.append(device_id)
        if context is not None:
            conditions.append("context = ?")
            params.append(context)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM vision_events {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def events_by_session(self, session_id: str) -> list[VisionEvent]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM vision_events WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]
