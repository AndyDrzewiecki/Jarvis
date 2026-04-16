"""
Anomaly detector for Phase 7 — Network Security Agent.

Establishes per-device traffic baselines from recent Firewalla flow data
and flags deviations above configurable thresholds.

Metrics tracked per device (keyed by MAC):
  - bytes_per_hour        — average hourly upload + download bytes
  - new_destinations      — count of unique external IPs contacted per hour
  - port_variety          — unique destination ports per hour
  - dns_queries_per_hour  — DNS query rate

Deviation thresholds:
  >200%  → CRITICAL
  >150%  → HIGH
  >100%  → MEDIUM
  >50%   → LOW
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from jarvis.security.models import AnomalyAlert, ThreatLevel

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS traffic_baselines (
    mac_address  TEXT NOT NULL,
    metric       TEXT NOT NULL,
    baseline     REAL NOT NULL,
    sample_count INTEGER DEFAULT 1,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (mac_address, metric)
);

CREATE TABLE IF NOT EXISTS anomaly_alerts (
    alert_id       TEXT PRIMARY KEY,
    device_mac     TEXT NOT NULL,
    device_ip      TEXT DEFAULT '',
    metric         TEXT NOT NULL,
    baseline       REAL NOT NULL,
    observed       REAL NOT NULL,
    deviation_pct  REAL NOT NULL,
    level          TEXT NOT NULL,
    description    TEXT DEFAULT '',
    resolved       INTEGER DEFAULT 0,
    detected_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_aa_mac      ON anomaly_alerts(device_mac);
CREATE INDEX IF NOT EXISTS idx_aa_resolved ON anomaly_alerts(resolved);
CREATE INDEX IF NOT EXISTS idx_aa_detected ON anomaly_alerts(detected_at);
"""

# Deviation → ThreatLevel
_DEVIATION_LEVELS: list[tuple[float, ThreatLevel]] = [
    (200.0, ThreatLevel.CRITICAL),
    (150.0, ThreatLevel.HIGH),
    (100.0, ThreatLevel.MEDIUM),
    (50.0,  ThreatLevel.LOW),
]


def _deviation_to_level(pct: float) -> Optional[ThreatLevel]:
    for threshold, level in _DEVIATION_LEVELS:
        if pct >= threshold:
            return level
    return None   # below minimum threshold — not an anomaly


class AnomalyDetector:
    """Maintains traffic baselines and detects deviations."""

    def __init__(self, db_path: str | None = None, min_alert_pct: float = 50.0):
        from jarvis import config
        self._db_path       = db_path or os.path.join(config.DATA_DIR, "security_anomalies.db")
        self.min_alert_pct  = min_alert_pct

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        conn.commit()
        return conn

    # ── Baseline management ────────────────────────────────────────────────────

    def update_baseline(
        self,
        mac: str,
        metric: str,
        observed: float,
        alpha: float = 0.1,
    ) -> float:
        """
        Exponential moving average baseline update.
        Returns the new baseline value.
        """
        now  = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT baseline, sample_count FROM traffic_baselines WHERE mac_address=? AND metric=?",
                (mac, metric),
            ).fetchone()
            if row:
                # EMA update: new = alpha*observed + (1-alpha)*old
                new_baseline = alpha * observed + (1 - alpha) * row["baseline"]
                new_count    = row["sample_count"] + 1
                conn.execute(
                    "UPDATE traffic_baselines SET baseline=?, sample_count=?, updated_at=? WHERE mac_address=? AND metric=?",
                    (new_baseline, new_count, now, mac, metric),
                )
            else:
                new_baseline = observed
                new_count    = 1
                conn.execute(
                    "INSERT INTO traffic_baselines (mac_address, metric, baseline, sample_count, updated_at) VALUES (?,?,?,?,?)",
                    (mac, metric, new_baseline, new_count, now),
                )
            conn.commit()
            return new_baseline
        finally:
            conn.close()

    def get_baseline(self, mac: str, metric: str) -> Optional[float]:
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT baseline FROM traffic_baselines WHERE mac_address=? AND metric=?",
                (mac, metric),
            ).fetchone()
            return row["baseline"] if row else None
        finally:
            conn.close()

    def get_all_baselines(self, mac: str) -> dict[str, float]:
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT metric, baseline FROM traffic_baselines WHERE mac_address=?", (mac,)
            ).fetchall()
            return {r["metric"]: r["baseline"] for r in rows}
        finally:
            conn.close()

    # ── Anomaly detection ──────────────────────────────────────────────────────

    def check(
        self,
        mac: str,
        ip: str,
        metric: str,
        observed: float,
        min_samples: int = 5,
    ) -> Optional[AnomalyAlert]:
        """
        Check if an observed value deviates significantly from baseline.
        Updates the baseline as a side-effect.
        Returns an AnomalyAlert if an anomaly is detected, else None.
        """
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT baseline, sample_count FROM traffic_baselines WHERE mac_address=? AND metric=?",
                (mac, metric),
            ).fetchone()
        finally:
            conn.close()

        if row is None or row["sample_count"] < min_samples:
            # Not enough data — just update baseline
            self.update_baseline(mac, metric, observed)
            return None

        baseline = row["baseline"]
        # Update baseline before scoring
        self.update_baseline(mac, metric, observed)

        if baseline <= 0:
            return None

        deviation_pct = abs((observed - baseline) / baseline) * 100
        level = _deviation_to_level(deviation_pct)
        if level is None or deviation_pct < self.min_alert_pct:
            return None

        direction = "above" if observed > baseline else "below"
        description = (
            f"{metric} is {deviation_pct:.0f}% {direction} baseline "
            f"(baseline={baseline:.1f}, observed={observed:.1f}) "
            f"for device {mac}"
        )

        alert = AnomalyAlert.new(
            device_mac=mac,
            device_ip=ip,
            metric=metric,
            baseline=baseline,
            observed=observed,
            level=level,
            description=description,
        )
        self._persist_alert(alert)
        return alert

    def analyze_flows(
        self,
        mac: str,
        ip: str,
        flows: list[dict],
        window_hours: float = 1.0,
    ) -> list[AnomalyAlert]:
        """
        Compute traffic metrics from a list of flow dicts and run anomaly checks.
        Returns a list of any AnomalyAlerts detected.

        Flow dict expected keys: ob (out bytes), rb (recv bytes), dp (dst port), dh (dst host).
        """
        if not flows:
            return []

        total_bytes       = sum(f.get("ob", 0) + f.get("rb", 0) for f in flows)
        bytes_per_hour    = total_bytes / max(window_hours, 0.0001)
        unique_dests      = len({f.get("dh", f.get("dst_ip", "")) for f in flows if f.get("dh") or f.get("dst_ip")})
        unique_ports      = len({f.get("dp", f.get("dst_port")) for f in flows if f.get("dp") or f.get("dst_port")})
        dns_count         = sum(1 for f in flows if f.get("dp") == 53 or f.get("dst_port") == 53)
        dns_per_hour      = dns_count / max(window_hours, 0.0001)

        alerts: list[AnomalyAlert] = []
        for metric, value in [
            ("bytes_per_hour",       bytes_per_hour),
            ("new_destinations",     float(unique_dests)),
            ("port_variety",         float(unique_ports)),
            ("dns_queries_per_hour", dns_per_hour),
        ]:
            alert = self.check(mac, ip, metric, value)
            if alert:
                alerts.append(alert)

        return alerts

    # ── Queries ────────────────────────────────────────────────────────────────

    def get_alerts(
        self,
        unresolved_only: bool = True,
        mac: str | None = None,
        limit: int = 100,
    ) -> list[AnomalyAlert]:
        sql = "SELECT * FROM anomaly_alerts WHERE 1=1"
        params: list[Any] = []
        if unresolved_only:
            sql += " AND resolved=0"
        if mac:
            sql += " AND device_mac=?"
            params.append(mac)
        sql += " ORDER BY deviation_pct DESC, detected_at DESC LIMIT ?"
        params.append(limit)

        conn = self._open()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_alert(r) for r in rows]
        finally:
            conn.close()

    def resolve_alert(self, alert_id: str) -> bool:
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE anomaly_alerts SET resolved=1 WHERE alert_id=?", (alert_id,)
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def count_unresolved(self) -> int:
        conn = self._open()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM anomaly_alerts WHERE resolved=0"
            ).fetchone()[0]
        finally:
            conn.close()

    def purge_old_alerts(self, days: int = 30) -> int:
        """Delete resolved alerts older than `days` days."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        conn = self._open()
        try:
            result = conn.execute(
                "DELETE FROM anomaly_alerts WHERE resolved=1 AND detected_at<?", (cutoff,)
            )
            conn.commit()
            return result.rowcount
        finally:
            conn.close()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _persist_alert(self, alert: AnomalyAlert) -> None:
        conn = self._open()
        try:
            conn.execute(
                """INSERT OR IGNORE INTO anomaly_alerts
                   (alert_id, device_mac, device_ip, metric, baseline, observed,
                    deviation_pct, level, description, resolved, detected_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    alert.alert_id, alert.device_mac, alert.device_ip,
                    alert.metric, alert.baseline, alert.observed,
                    alert.deviation_pct, alert.level.value, alert.description,
                    int(alert.resolved), alert.detected_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_alert(self, row: sqlite3.Row) -> AnomalyAlert:
        d = dict(row)
        d["resolved"] = bool(d["resolved"])
        return AnomalyAlert(
            alert_id=d["alert_id"],
            device_mac=d["device_mac"],
            device_ip=d.get("device_ip", ""),
            metric=d["metric"],
            baseline=d["baseline"],
            observed=d["observed"],
            deviation_pct=d["deviation_pct"],
            level=ThreatLevel(d["level"]),
            description=d.get("description", ""),
            resolved=d["resolved"],
            detected_at=d["detected_at"],
        )
