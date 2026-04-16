"""
Threat scoring engine for Phase 7 — Network Security Agent.

Processes Firewalla alarms and raw traffic flows to:
  1. Score individual threats (0–100)
  2. Update per-device cumulative threat scores
  3. Persist ThreatEvent records to SQLite
  4. Post critical alerts to the blackboard

Threat score thresholds:
  0–29   → info / benign
  30–49  → low
  50–69  → medium
  70–84  → high
  85–100 → critical
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from jarvis.security.models import (
    ThreatCategory,
    ThreatEvent,
    ThreatLevel,
)

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS threat_events (
    event_id      TEXT PRIMARY KEY,
    level         TEXT NOT NULL,
    category      TEXT NOT NULL,
    description   TEXT NOT NULL,
    source_ip     TEXT DEFAULT '',
    source_mac    TEXT DEFAULT '',
    dest_ip       TEXT DEFAULT '',
    dest_port     INTEGER,
    protocol      TEXT DEFAULT '',
    device_id     TEXT DEFAULT '',
    auto_blocked  INTEGER DEFAULT 0,
    resolved      INTEGER DEFAULT 0,
    score         REAL DEFAULT 0.0,
    raw_data      TEXT DEFAULT '{}',
    detected_at   TEXT NOT NULL,
    resolved_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_te_level     ON threat_events(level);
CREATE INDEX IF NOT EXISTS idx_te_detected  ON threat_events(detected_at);
CREATE INDEX IF NOT EXISTS idx_te_resolved  ON threat_events(resolved);
"""

# ── Firewalla alarm type → ThreatCategory mapping ─────────────────────────────
_ALARM_TYPE_MAP: dict[str, ThreatCategory] = {
    "ALARM_NEW_DEVICE":            ThreatCategory.UNKNOWN,
    "ALARM_DEVICE_BACK_ONLINE":    ThreatCategory.UNKNOWN,
    "ALARM_VULNERABILITY":         ThreatCategory.MALWARE,
    "ALARM_SCAN":                  ThreatCategory.PORT_SCAN,
    "ALARM_LARGE_UPLOAD":          ThreatCategory.DATA_EXFILTRATION,
    "ALARM_VIDEO_STREAMING":       ThreatCategory.POLICY_VIOLATION,
    "ALARM_GAMING":                ThreatCategory.POLICY_VIOLATION,
    "ALARM_PORN":                  ThreatCategory.POLICY_VIOLATION,
    "ALARM_VPN":                   ThreatCategory.POLICY_VIOLATION,
    "ALARM_BRO_INTEL":             ThreatCategory.MALWARE,
    "ALARM_INTEL":                 ThreatCategory.BOTNET,
    "ALARM_CUSTOMIZE":             ThreatCategory.POLICY_VIOLATION,
    "ALARM_DNS_BLOCK":             ThreatCategory.SUSPICIOUS_DNS,
    "ALARM_DEVICE_OFFLINE":        ThreatCategory.UNKNOWN,
    "ALARM_ABNORMAL_BANDWIDTH":    ThreatCategory.ANOMALY,
}

# Base score by alarm severity string (Firewalla uses 0-3)
_SEVERITY_SCORE: dict[str, float] = {
    "0": 15.0,  # notice
    "1": 35.0,  # warning
    "2": 65.0,  # error
    "3": 85.0,  # critical
}

# Score multipliers by category
_CATEGORY_MULTIPLIER: dict[ThreatCategory, float] = {
    ThreatCategory.PORT_SCAN:         1.2,
    ThreatCategory.MALWARE:           1.5,
    ThreatCategory.BOTNET:            1.6,
    ThreatCategory.DATA_EXFILTRATION: 1.4,
    ThreatCategory.BRUTE_FORCE:       1.3,
    ThreatCategory.ROGUE_AP:          1.1,
    ThreatCategory.SUSPICIOUS_DNS:    1.1,
    ThreatCategory.POLICY_VIOLATION:  0.7,
    ThreatCategory.ANOMALY:           1.0,
    ThreatCategory.UNKNOWN:           0.5,
}


def _score_to_level(score: float) -> ThreatLevel:
    if score >= 85:
        return ThreatLevel.CRITICAL
    if score >= 70:
        return ThreatLevel.HIGH
    if score >= 50:
        return ThreatLevel.MEDIUM
    if score >= 30:
        return ThreatLevel.LOW
    return ThreatLevel.INFO


class ThreatEngine:
    """Processes security signals and maintains the threat event log."""

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "security_threats.db")

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        conn.commit()
        return conn

    def _row_to_event(self, row: sqlite3.Row) -> ThreatEvent:
        d = dict(row)
        d["auto_blocked"] = bool(d["auto_blocked"])
        d["resolved"]     = bool(d["resolved"])
        d["raw_data"]     = json.loads(d.get("raw_data") or "{}")
        return ThreatEvent.from_dict(d)

    # ── Firewalla alarm processing ────────────────────────────────────────────

    def process_firewalla_alarm(self, alarm: dict) -> ThreatEvent:
        """
        Convert a raw Firewalla alarm dict into a ThreatEvent and persist it.
        Returns the resulting ThreatEvent.
        """
        alarm_type = alarm.get("type", "ALARM_CUSTOMIZE")
        category   = _ALARM_TYPE_MAP.get(alarm_type, ThreatCategory.UNKNOWN)

        severity_str = str(alarm.get("severity", alarm.get("alarmSeverity", "1")))
        base_score   = _SEVERITY_SCORE.get(severity_str, 35.0)
        score        = min(100.0, base_score * _CATEGORY_MULTIPLIER.get(category, 1.0))
        level        = _score_to_level(score)

        device_info = alarm.get("device") or {}
        remote_info = alarm.get("remote") or {}

        description = (
            alarm.get("message")
            or alarm.get("alarmMessage")
            or f"{alarm_type} from {device_info.get('name', 'unknown device')}"
        )

        event = ThreatEvent.new(
            level=level,
            category=category,
            description=description,
            source_ip=device_info.get("ip") or alarm.get("device.ip", ""),
            source_mac=device_info.get("mac") or alarm.get("device.mac", ""),
            dest_ip=remote_info.get("ip") or alarm.get("remote.ip", ""),
            dest_port=remote_info.get("port") or alarm.get("remote.port"),
            protocol=alarm.get("protocol", ""),
            score=score,
            raw_data=alarm,
        )
        self._persist(event)
        self._maybe_post_blackboard(event)
        return event

    def process_firewalla_alarms(self, alarms: list[dict]) -> list[ThreatEvent]:
        """Process a batch of Firewalla alarms."""
        return [self.process_firewalla_alarm(a) for a in alarms]

    # ── Manual / computed threat events ───────────────────────────────────────

    def record_threat(
        self,
        category: ThreatCategory,
        description: str,
        score: float,
        source_ip: str = "",
        source_mac: str = "",
        dest_ip: str = "",
        dest_port: Optional[int] = None,
        protocol: str = "",
        device_id: str = "",
        auto_blocked: bool = False,
        raw_data: dict | None = None,
    ) -> ThreatEvent:
        """Manually record a threat event (e.g. from anomaly detector)."""
        level = _score_to_level(score)
        event = ThreatEvent.new(
            level=level,
            category=category,
            description=description,
            source_ip=source_ip,
            source_mac=source_mac,
            dest_ip=dest_ip,
            dest_port=dest_port,
            protocol=protocol,
            device_id=device_id,
            auto_blocked=auto_blocked,
            score=score,
            raw_data=raw_data or {},
        )
        self._persist(event)
        self._maybe_post_blackboard(event)
        return event

    # ── Rogue AP handling ─────────────────────────────────────────────────────

    def process_rogue_aps(self, rogue_aps: list[dict]) -> list[ThreatEvent]:
        """Convert Aruba rogue AP detections to ThreatEvents."""
        events = []
        for rogue in rogue_aps:
            classification = rogue.get("classification", "interfering").lower()
            if classification == "neighbor":
                continue  # neighboring APs are not threats
            score = 75.0 if classification == "rogue" else 45.0
            event = self.record_threat(
                category=ThreatCategory.ROGUE_AP,
                description=(
                    f"Rogue AP detected: SSID={rogue.get('ssid', 'unknown')} "
                    f"BSSID={rogue.get('bssid', 'unknown')} "
                    f"channel={rogue.get('channel', '?')}"
                ),
                score=score,
                raw_data=rogue,
            )
            events.append(event)
        return events

    # ── Query ─────────────────────────────────────────────────────────────────

    def get_events(
        self,
        unresolved_only: bool = True,
        level: ThreatLevel | None = None,
        limit: int = 100,
    ) -> list[ThreatEvent]:
        sql = "SELECT * FROM threat_events WHERE 1=1"
        params: list[Any] = []
        if unresolved_only:
            sql += " AND resolved=0"
        if level:
            sql += " AND level=?"
            params.append(level.value)
        sql += " ORDER BY score DESC, detected_at DESC LIMIT ?"
        params.append(limit)

        conn = self._open()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_event(r) for r in rows]
        finally:
            conn.close()

    def resolve_event(self, event_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE threat_events SET resolved=1, resolved_at=? WHERE event_id=?",
                (now, event_id),
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def mark_auto_blocked(self, event_id: str) -> bool:
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE threat_events SET auto_blocked=1 WHERE event_id=?",
                (event_id,),
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def count_by_level(self) -> dict[str, int]:
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT level, COUNT(*) as cnt FROM threat_events WHERE resolved=0 GROUP BY level"
            ).fetchall()
            return {r["level"]: r["cnt"] for r in rows}
        finally:
            conn.close()

    def compute_device_threat_score(self, mac: str, days: int = 7) -> float:
        """
        Compute a rolling threat score for a device based on recent events.
        Returns 0–100.
        """
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = self._open()
        try:
            rows = conn.execute(
                """SELECT score FROM threat_events
                   WHERE source_mac=? AND detected_at>=? AND resolved=0
                   ORDER BY detected_at DESC LIMIT 20""",
                (mac, cutoff),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return 0.0
        scores = [r["score"] for r in rows]
        # Weighted: most recent event counts most, with diminishing weight
        total  = sum(s * (0.9 ** i) for i, s in enumerate(scores))
        weight = sum(0.9 ** i for i in range(len(scores)))
        return min(100.0, total / weight)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _persist(self, event: ThreatEvent) -> None:
        conn = self._open()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO threat_events
                   (event_id, level, category, description, source_ip, source_mac,
                    dest_ip, dest_port, protocol, device_id, auto_blocked, resolved,
                    score, raw_data, detected_at, resolved_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event.event_id, event.level.value, event.category.value,
                    event.description, event.source_ip, event.source_mac,
                    event.dest_ip, event.dest_port, event.protocol,
                    event.device_id, int(event.auto_blocked), int(event.resolved),
                    event.score, json.dumps(event.raw_data),
                    event.detected_at, event.resolved_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _maybe_post_blackboard(self, event: ThreatEvent) -> None:
        """Post high/critical threats to the shared blackboard."""
        if event.level not in (ThreatLevel.HIGH, ThreatLevel.CRITICAL):
            return
        try:
            from jarvis.blackboard import SharedBlackboard
            bb = SharedBlackboard()
            urgency = "urgent" if event.level == ThreatLevel.CRITICAL else "high"
            bb.post(
                agent="security_agent",
                topic="security.threat",
                content=(
                    f"[{event.level.value.upper()}] {event.category.value}: "
                    f"{event.description} | score={event.score:.0f} "
                    f"src={event.source_ip or event.source_mac}"
                ),
                urgency=urgency,
                ttl_days=3,
            )
        except Exception as exc:
            logger.debug("Blackboard post failed: %s", exc)
