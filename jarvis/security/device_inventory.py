"""
Network device inventory for Phase 7 — Network Security Agent.

Maintains a SQLite-backed registry of all network devices discovered via
Firewalla and Aruba. Merges data from both sources into unified NetworkDevice
records. Supports automatic discovery, manual registration, and threat-score
updates.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from jarvis.security.models import (
    NetworkDevice,
    NetworkDeviceType,
    VLANType,
)

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS network_devices (
    device_id    TEXT PRIMARY KEY,
    mac_address  TEXT NOT NULL UNIQUE,
    ip_address   TEXT NOT NULL,
    hostname     TEXT DEFAULT '',
    vendor       TEXT DEFAULT '',
    device_type  TEXT DEFAULT 'unknown',
    vlan         TEXT DEFAULT 'main',
    ssid         TEXT DEFAULT '',
    signal_dbm   INTEGER,
    is_online    INTEGER DEFAULT 1,
    is_blocked   INTEGER DEFAULT 0,
    is_isolated  INTEGER DEFAULT 0,
    threat_score REAL DEFAULT 0.0,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL,
    metadata     TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_nd_mac ON network_devices(mac_address);
CREATE INDEX IF NOT EXISTS idx_nd_ip  ON network_devices(ip_address);
"""


class DeviceInventory:
    """SQLite-backed network device inventory."""

    def __init__(self, db_path: str | None = None):
        from jarvis import config
        self._db_path = db_path or os.path.join(config.DATA_DIR, "security_devices.db")

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_DDL)
        conn.commit()
        return conn

    def _row_to_device(self, row: sqlite3.Row) -> NetworkDevice:
        d = dict(row)
        d["is_online"]   = bool(d["is_online"])
        d["is_blocked"]  = bool(d["is_blocked"])
        d["is_isolated"] = bool(d["is_isolated"])
        d["metadata"]    = json.loads(d.get("metadata") or "{}")
        return NetworkDevice.from_dict(d)

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def upsert(self, device: NetworkDevice) -> None:
        """Insert or update a device record (keyed by MAC address)."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            existing = conn.execute(
                "SELECT device_id, first_seen FROM network_devices WHERE mac_address=?",
                (device.mac_address,),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE network_devices SET
                        ip_address=?, hostname=?, vendor=?, device_type=?,
                        vlan=?, ssid=?, signal_dbm=?, is_online=?, is_blocked=?,
                        is_isolated=?, threat_score=?, last_seen=?, metadata=?
                       WHERE mac_address=?""",
                    (
                        device.ip_address, device.hostname, device.vendor,
                        device.device_type.value, device.vlan.value, device.ssid,
                        device.signal_dbm,
                        int(device.is_online), int(device.is_blocked), int(device.is_isolated),
                        device.threat_score, now,
                        json.dumps(device.metadata),
                        device.mac_address,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO network_devices
                       (device_id, mac_address, ip_address, hostname, vendor,
                        device_type, vlan, ssid, signal_dbm, is_online, is_blocked,
                        is_isolated, threat_score, first_seen, last_seen, metadata)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        device.device_id, device.mac_address, device.ip_address,
                        device.hostname, device.vendor, device.device_type.value,
                        device.vlan.value, device.ssid, device.signal_dbm,
                        int(device.is_online), int(device.is_blocked), int(device.is_isolated),
                        device.threat_score, device.first_seen, now,
                        json.dumps(device.metadata),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def get_by_mac(self, mac: str) -> Optional[NetworkDevice]:
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT * FROM network_devices WHERE mac_address=?", (mac,)
            ).fetchone()
            return self._row_to_device(row) if row else None
        finally:
            conn.close()

    def get_by_id(self, device_id: str) -> Optional[NetworkDevice]:
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT * FROM network_devices WHERE device_id=?", (device_id,)
            ).fetchone()
            return self._row_to_device(row) if row else None
        finally:
            conn.close()

    def get_all(
        self,
        online_only: bool = False,
        vlan: VLANType | None = None,
        device_type: NetworkDeviceType | None = None,
        limit: int = 200,
    ) -> list[NetworkDevice]:
        sql = "SELECT * FROM network_devices WHERE 1=1"
        params: list[Any] = []
        if online_only:
            sql += " AND is_online=1"
        if vlan:
            sql += " AND vlan=?"
            params.append(vlan.value)
        if device_type:
            sql += " AND device_type=?"
            params.append(device_type.value)
        sql += " ORDER BY threat_score DESC, last_seen DESC LIMIT ?"
        params.append(limit)

        conn = self._open()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_device(r) for r in rows]
        finally:
            conn.close()

    def set_blocked(self, mac: str, blocked: bool) -> bool:
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE network_devices SET is_blocked=? WHERE mac_address=?",
                (int(blocked), mac),
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def set_isolated(self, mac: str, isolated: bool, vlan: VLANType | None = None) -> bool:
        conn = self._open()
        try:
            if vlan:
                result = conn.execute(
                    "UPDATE network_devices SET is_isolated=?, vlan=? WHERE mac_address=?",
                    (int(isolated), vlan.value, mac),
                )
            else:
                result = conn.execute(
                    "UPDATE network_devices SET is_isolated=? WHERE mac_address=?",
                    (int(isolated), mac),
                )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def update_threat_score(self, mac: str, score: float) -> bool:
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE network_devices SET threat_score=? WHERE mac_address=?",
                (score, mac),
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def mark_offline(self, macs: list[str]) -> None:
        """Mark a set of MACs as offline (used after a fresh scan)."""
        if not macs:
            return
        conn = self._open()
        try:
            placeholders = ",".join("?" * len(macs))
            conn.execute(
                f"UPDATE network_devices SET is_online=0 WHERE mac_address IN ({placeholders})",
                macs,
            )
            conn.commit()
        finally:
            conn.close()

    def delete(self, mac: str) -> bool:
        conn = self._open()
        try:
            result = conn.execute(
                "DELETE FROM network_devices WHERE mac_address=?", (mac,)
            )
            conn.commit()
            return result.rowcount > 0
        finally:
            conn.close()

    def count(self) -> dict[str, int]:
        """Return counts by state."""
        conn = self._open()
        try:
            total    = conn.execute("SELECT COUNT(*) FROM network_devices").fetchone()[0]
            online   = conn.execute("SELECT COUNT(*) FROM network_devices WHERE is_online=1").fetchone()[0]
            blocked  = conn.execute("SELECT COUNT(*) FROM network_devices WHERE is_blocked=1").fetchone()[0]
            isolated = conn.execute("SELECT COUNT(*) FROM network_devices WHERE is_isolated=1").fetchone()[0]
            high_risk = conn.execute("SELECT COUNT(*) FROM network_devices WHERE threat_score>=70").fetchone()[0]
            return {
                "total": total,
                "online": online,
                "offline": total - online,
                "blocked": blocked,
                "isolated": isolated,
                "high_risk": high_risk,
            }
        finally:
            conn.close()

    # ── Discovery merge helpers ────────────────────────────────────────────────

    def merge_firewalla_devices(self, firewalla_devices: list[dict]) -> int:
        """
        Merge Firewalla device list into inventory.
        Returns number of new/updated devices.
        """
        count = 0
        for fw in firewalla_devices:
            mac = fw.get("mac") or fw.get("macAddress", "")
            ip  = fw.get("ip")  or fw.get("ipAddress", "")
            if not mac or not ip:
                continue
            existing = self.get_by_mac(mac)
            if existing:
                existing.ip_address = ip
                existing.hostname   = fw.get("name") or fw.get("hostname") or existing.hostname
                existing.vendor     = fw.get("vendor") or existing.vendor
                existing.is_online  = bool(fw.get("online", fw.get("active", True)))
                existing.is_blocked = bool(fw.get("blocked", False))
                self.upsert(existing)
            else:
                device = NetworkDevice.new(
                    mac=mac,
                    ip=ip,
                    hostname=fw.get("name") or fw.get("hostname", ""),
                    vendor=fw.get("vendor", ""),
                    is_online=bool(fw.get("online", fw.get("active", True))),
                    is_blocked=bool(fw.get("blocked", False)),
                    metadata={"source": "firewalla"},
                )
                self.upsert(device)
            count += 1
        return count

    def merge_aruba_clients(self, aruba_clients: list[dict]) -> int:
        """
        Merge Aruba wireless client list into inventory.
        Returns number of new/updated devices.
        """
        count = 0
        for cl in aruba_clients:
            mac = cl.get("mac") or cl.get("macAddress", "")
            ip  = cl.get("ip")  or cl.get("ipAddress", "")
            if not mac:
                continue
            ip = ip or "0.0.0.0"
            existing = self.get_by_mac(mac)
            if existing:
                existing.ip_address = ip or existing.ip_address
                existing.hostname   = cl.get("name") or existing.hostname
                existing.ssid       = cl.get("ssid", "") or existing.ssid
                existing.signal_dbm = cl.get("signal") or cl.get("rssi") or existing.signal_dbm
                existing.is_online  = True
                self.upsert(existing)
            else:
                device = NetworkDevice.new(
                    mac=mac,
                    ip=ip,
                    hostname=cl.get("name") or cl.get("os_type", ""),
                    ssid=cl.get("ssid", ""),
                    signal_dbm=cl.get("signal") or cl.get("rssi"),
                    device_type=_guess_device_type(cl),
                    metadata={"source": "aruba", "ap": cl.get("ap_name", "")},
                )
                self.upsert(device)
            count += 1
        return count


def _guess_device_type(client_dict: dict) -> NetworkDeviceType:
    """Heuristically guess device type from Aruba client metadata."""
    os_type = (client_dict.get("os_type") or client_dict.get("os", "")).lower()
    name    = (client_dict.get("name") or "").lower()
    ssid    = (client_dict.get("ssid") or "").lower()

    if "guest" in ssid:
        return NetworkDeviceType.GUEST
    if any(k in os_type for k in ("android", "ios", "iphone", "ipad")):
        return NetworkDeviceType.PHONE
    if "windows" in os_type or "mac" in os_type or "linux" in os_type:
        return NetworkDeviceType.COMPUTER
    if any(k in name for k in ("camera", "cam", "ring", "nest", "arlo")):
        return NetworkDeviceType.CAMERA
    if any(k in name for k in ("tv", "roku", "firetv", "appletv", "chromecast")):
        return NetworkDeviceType.SMART_TV
    if any(k in name for k in ("printer", "hp", "canon", "epson", "brother")):
        return NetworkDeviceType.PRINTER
    return NetworkDeviceType.UNKNOWN
