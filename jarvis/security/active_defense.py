"""
Active defense engine for Phase 7 — Network Security Agent.

Handles:
  - Auto-blocking suspicious IPs/domains via Firewalla
  - Device isolation to quarantine VLAN via Aruba
  - Guest network session management (expire, bandwidth limits)
  - Alert posting to blackboard + notifier on critical actions

All actions are logged to the audit log (db_protection.AuditLogger).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from jarvis.security.models import (
    BlockEntry,
    DeviceIsolation,
    GuestSession,
    ThreatEvent,
    ThreatLevel,
    VLANType,
)

logger = logging.getLogger(__name__)

_BLOCK_DDL = """
CREATE TABLE IF NOT EXISTS block_entries (
    block_id          TEXT PRIMARY KEY,
    target            TEXT NOT NULL,
    target_type       TEXT DEFAULT 'ip',
    reason            TEXT DEFAULT '',
    auto_created      INTEGER DEFAULT 0,
    expires_at        TEXT,
    created_at        TEXT NOT NULL,
    firewalla_rule_id TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_be_target ON block_entries(target);

CREATE TABLE IF NOT EXISTS device_isolations (
    isolation_id     TEXT PRIMARY KEY,
    device_id        TEXT DEFAULT '',
    mac_address      TEXT NOT NULL,
    ip_address       TEXT DEFAULT '',
    original_vlan    TEXT NOT NULL,
    reason           TEXT DEFAULT '',
    threat_event_id  TEXT DEFAULT '',
    is_active        INTEGER DEFAULT 1,
    isolated_at      TEXT NOT NULL,
    released_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_di_mac    ON device_isolations(mac_address);
CREATE INDEX IF NOT EXISTS idx_di_active ON device_isolations(is_active);

CREATE TABLE IF NOT EXISTS guest_sessions (
    session_id            TEXT PRIMARY KEY,
    mac_address           TEXT NOT NULL,
    ip_address            TEXT DEFAULT '',
    hostname              TEXT DEFAULT '',
    bandwidth_limit_mbps  REAL,
    expires_at            TEXT,
    is_active             INTEGER DEFAULT 1,
    bytes_up              INTEGER DEFAULT 0,
    bytes_down            INTEGER DEFAULT 0,
    connected_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gs_mac    ON guest_sessions(mac_address);
CREATE INDEX IF NOT EXISTS idx_gs_active ON guest_sessions(is_active);
"""

# VLAN ID mapping for Aruba
_VLAN_ID: dict[VLANType, int] = {
    VLANType.MAIN:      10,
    VLANType.IOT:       20,
    VLANType.GUEST:     30,
    VLANType.QUARANTINE: 99,
}

# Auto-block threshold (threat score)
AUTO_BLOCK_SCORE = 75.0
# Auto-isolate threshold for IoT devices
AUTO_ISOLATE_SCORE = 65.0


class ActiveDefense:
    """Orchestrates active network defense actions."""

    def __init__(
        self,
        db_path: str | None = None,
        firewalla=None,
        aruba=None,
    ):
        from jarvis import config
        self._db_path  = db_path or os.path.join(config.DATA_DIR, "security_defense.db")
        self._firewalla = firewalla   # FirewallaClient instance (injected or lazy-loaded)
        self._aruba     = aruba       # ArubaClient instance

    def _open(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript(_BLOCK_DDL)
        conn.commit()
        return conn

    def _get_firewalla(self):
        if self._firewalla is not None:
            return self._firewalla
        from jarvis.security.firewalla_client import FirewallaClient
        return FirewallaClient()

    def _get_aruba(self):
        if self._aruba is not None:
            return self._aruba
        from jarvis.security.aruba_client import ArubaClient
        return ArubaClient()

    # ── Block management ───────────────────────────────────────────────────────

    def block(
        self,
        target: str,
        target_type: str = "ip",
        reason: str = "",
        auto_created: bool = False,
        ttl_hours: Optional[int] = None,
    ) -> BlockEntry:
        """
        Block an IP address or domain via Firewalla.
        Returns the BlockEntry (persisted).
        """
        expires_at = None
        if ttl_hours:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()

        # Push to Firewalla
        fw = self._get_firewalla()
        fw_rule_id = fw.create_block_rule(target, target_type=target_type, reason=reason) or ""

        entry = BlockEntry.new(
            target=target,
            target_type=target_type,
            reason=reason,
            auto_created=auto_created,
            expires_at=expires_at,
            firewalla_rule_id=fw_rule_id,
        )
        self._persist_block(entry)
        self._audit("block", target, detail=f"type={target_type} reason={reason}")
        self._notify_if_auto(entry)
        logger.info("Blocked %s (%s): %s", target, target_type, reason)
        return entry

    def unblock(self, target: str) -> bool:
        """Remove a block on an IP/domain."""
        entry = self._get_block(target)
        if not entry:
            return False

        # Remove from Firewalla
        if entry.firewalla_rule_id:
            fw = self._get_firewalla()
            fw.delete_rule(entry.firewalla_rule_id)

        conn = self._open()
        try:
            conn.execute("DELETE FROM block_entries WHERE target=?", (target,))
            conn.commit()
        finally:
            conn.close()

        self._audit("unblock", target)
        logger.info("Unblocked %s", target)
        return True

    def get_blocks(self, active_only: bool = True) -> list[BlockEntry]:
        now = datetime.now(timezone.utc).isoformat()
        sql = "SELECT * FROM block_entries WHERE 1=1"
        params: list[Any] = []
        if active_only:
            sql += " AND (expires_at IS NULL OR expires_at > ?)"
            params.append(now)
        sql += " ORDER BY created_at DESC"

        conn = self._open()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_block(r) for r in rows]
        finally:
            conn.close()

    def is_blocked(self, target: str) -> bool:
        return self._get_block(target) is not None

    def expire_blocks(self) -> int:
        """Remove expired block entries (and their Firewalla rules)."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            rows = conn.execute(
                "SELECT * FROM block_entries WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            ).fetchall()
        finally:
            conn.close()

        count = 0
        for row in rows:
            entry = self._row_to_block(row)
            if entry.firewalla_rule_id:
                self._get_firewalla().delete_rule(entry.firewalla_rule_id)
            conn2 = self._open()
            try:
                conn2.execute("DELETE FROM block_entries WHERE block_id=?", (entry.block_id,))
                conn2.commit()
            finally:
                conn2.close()
            count += 1
        return count

    # ── Device isolation ───────────────────────────────────────────────────────

    def isolate_device(
        self,
        device_id: str,
        mac: str,
        ip: str,
        original_vlan: VLANType,
        reason: str = "",
        threat_event_id: str = "",
    ) -> DeviceIsolation:
        """
        Move a device to the quarantine VLAN (VLAN 99).
        Pushes the VLAN change via Aruba and records the isolation.
        """
        aruba = self._get_aruba()
        vlan_id = _VLAN_ID[VLANType.QUARANTINE]
        aruba.move_client_to_vlan(mac, vlan_id)

        isolation = DeviceIsolation.new(
            device_id=device_id,
            mac=mac,
            ip=ip,
            original_vlan=original_vlan,
            reason=reason,
            threat_event_id=threat_event_id,
        )
        self._persist_isolation(isolation)

        # Update device inventory
        try:
            from jarvis.security.device_inventory import DeviceInventory
            inventory = DeviceInventory()
            inventory.set_isolated(mac, True, VLANType.QUARANTINE)
        except Exception:
            pass

        self._audit("isolate_device", mac, detail=f"reason={reason} original_vlan={original_vlan.value}")
        self._post_blackboard(
            f"Device ISOLATED: {mac} ({ip}) moved to quarantine VLAN. Reason: {reason}",
            urgency="urgent",
        )
        logger.warning("Isolated device %s (%s) — %s", mac, ip, reason)
        return isolation

    def release_device(self, mac: str) -> bool:
        """Release a device from quarantine back to its original VLAN."""
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT * FROM device_isolations WHERE mac_address=? AND is_active=1",
                (mac,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return False

        isolation = self._row_to_isolation(row)
        original_vlan_id = _VLAN_ID.get(isolation.original_vlan, _VLAN_ID[VLANType.MAIN])

        aruba = self._get_aruba()
        aruba.move_client_to_vlan(mac, original_vlan_id)

        now = datetime.now(timezone.utc).isoformat()
        conn2 = self._open()
        try:
            conn2.execute(
                "UPDATE device_isolations SET is_active=0, released_at=? WHERE mac_address=? AND is_active=1",
                (now, mac),
            )
            conn2.commit()
        finally:
            conn2.close()

        try:
            from jarvis.security.device_inventory import DeviceInventory
            inventory = DeviceInventory()
            inventory.set_isolated(mac, False, isolation.original_vlan)
        except Exception:
            pass

        self._audit("release_device", mac)
        logger.info("Released device %s from quarantine", mac)
        return True

    def get_isolations(self, active_only: bool = True) -> list[DeviceIsolation]:
        sql = "SELECT * FROM device_isolations"
        params: list[Any] = []
        if active_only:
            sql += " WHERE is_active=1"
        sql += " ORDER BY isolated_at DESC"

        conn = self._open()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_isolation(r) for r in rows]
        finally:
            conn.close()

    # ── Automated response ─────────────────────────────────────────────────────

    def auto_respond(
        self,
        event: ThreatEvent,
        inventory=None,
    ) -> dict[str, Any]:
        """
        Automatic response to a high/critical threat event.
        - Blocks source IP if score >= AUTO_BLOCK_SCORE
        - Isolates IoT devices if score >= AUTO_ISOLATE_SCORE
        Returns dict of actions taken.
        """
        actions: dict[str, Any] = {"blocked": False, "isolated": False}

        if event.score >= AUTO_BLOCK_SCORE and event.source_ip:
            already = self.is_blocked(event.source_ip)
            if not already:
                self.block(
                    event.source_ip,
                    reason=f"Auto-blocked: {event.category.value} (score={event.score:.0f})",
                    auto_created=True,
                )
                actions["blocked"] = event.source_ip

                # Mark event as auto-blocked
                try:
                    from jarvis.security.threat_engine import ThreatEngine
                    ThreatEngine().mark_auto_blocked(event.event_id)
                except Exception:
                    pass

        if event.score >= AUTO_ISOLATE_SCORE and event.source_mac and inventory:
            device = inventory.get_by_mac(event.source_mac)
            if device and not device.is_isolated:
                from jarvis.security.models import NetworkDeviceType
                if device.device_type in (NetworkDeviceType.IOT, NetworkDeviceType.CAMERA):
                    self.isolate_device(
                        device_id=device.device_id,
                        mac=device.mac_address,
                        ip=device.ip_address,
                        original_vlan=device.vlan,
                        reason=f"Auto-isolated: {event.category.value} (score={event.score:.0f})",
                        threat_event_id=event.event_id,
                    )
                    actions["isolated"] = device.mac_address

        return actions

    # ── Guest network management ───────────────────────────────────────────────

    def register_guest(
        self,
        mac: str,
        ip: str,
        hostname: str = "",
        bandwidth_limit_mbps: Optional[float] = None,
        ttl_hours: int = 24,
    ) -> GuestSession:
        """Register a guest Wi-Fi session."""
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).isoformat()

        if bandwidth_limit_mbps:
            aruba = self._get_aruba()
            aruba.set_guest_bandwidth("JarvisGuest", bandwidth_limit_mbps, bandwidth_limit_mbps / 2)

        session = GuestSession.new(
            mac=mac,
            ip=ip,
            hostname=hostname,
            bandwidth_limit_mbps=bandwidth_limit_mbps,
            expires_at=expires_at,
        )
        self._persist_guest(session)
        logger.info("Registered guest session: %s (%s) expires %s", mac, ip, expires_at)
        return session

    def expire_guest_sessions(self) -> int:
        """Expire all guest sessions past their expiry time."""
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE guest_sessions SET is_active=0 WHERE is_active=1 AND expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            )
            count = result.rowcount
            conn.commit()
        finally:
            conn.close()

        if count:
            self._audit("expire_guests", f"{count} sessions")
            logger.info("Expired %d guest sessions", count)
        return count

    def expire_all_guests(self) -> int:
        """Immediately expire all active guest sessions."""
        conn = self._open()
        try:
            result = conn.execute(
                "UPDATE guest_sessions SET is_active=0 WHERE is_active=1"
            )
            count = result.rowcount
            conn.commit()
        finally:
            conn.close()

        if count:
            # Disconnect clients from Aruba
            aruba = self._get_aruba()
            active = self.get_guest_sessions(active_only=False)
            for s in active:
                aruba.disconnect_client(s.mac_address)

        self._audit("expire_all_guests", f"{count} sessions forced")
        return count

    def get_guest_sessions(self, active_only: bool = True) -> list[GuestSession]:
        sql = "SELECT * FROM guest_sessions"
        if active_only:
            sql += " WHERE is_active=1"
        sql += " ORDER BY connected_at DESC"
        conn = self._open()
        try:
            rows = conn.execute(sql).fetchall()
            return [self._row_to_guest(r) for r in rows]
        finally:
            conn.close()

    def update_guest_usage(self, mac: str, bytes_up: int, bytes_down: int) -> None:
        conn = self._open()
        try:
            conn.execute(
                "UPDATE guest_sessions SET bytes_up=bytes_up+?, bytes_down=bytes_down+? WHERE mac_address=? AND is_active=1",
                (bytes_up, bytes_down, mac),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _persist_block(self, entry: BlockEntry) -> None:
        conn = self._open()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO block_entries
                   (block_id, target, target_type, reason, auto_created, expires_at, created_at, firewalla_rule_id)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (entry.block_id, entry.target, entry.target_type, entry.reason,
                 int(entry.auto_created), entry.expires_at, entry.created_at, entry.firewalla_rule_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _get_block(self, target: str) -> Optional[BlockEntry]:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._open()
        try:
            row = conn.execute(
                "SELECT * FROM block_entries WHERE target=? AND (expires_at IS NULL OR expires_at > ?)",
                (target, now),
            ).fetchone()
            return self._row_to_block(row) if row else None
        finally:
            conn.close()

    def _row_to_block(self, row: sqlite3.Row) -> BlockEntry:
        d = dict(row)
        d["auto_created"] = bool(d["auto_created"])
        return BlockEntry(
            block_id=d["block_id"],
            target=d["target"],
            target_type=d.get("target_type", "ip"),
            reason=d.get("reason", ""),
            auto_created=d["auto_created"],
            expires_at=d.get("expires_at"),
            created_at=d["created_at"],
            firewalla_rule_id=d.get("firewalla_rule_id", ""),
        )

    def _persist_isolation(self, iso: DeviceIsolation) -> None:
        conn = self._open()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO device_isolations
                   (isolation_id, device_id, mac_address, ip_address, original_vlan,
                    reason, threat_event_id, is_active, isolated_at, released_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (iso.isolation_id, iso.device_id, iso.mac_address, iso.ip_address,
                 iso.original_vlan.value, iso.reason, iso.threat_event_id,
                 int(iso.is_active), iso.isolated_at, iso.released_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_isolation(self, row: sqlite3.Row) -> DeviceIsolation:
        d = dict(row)
        return DeviceIsolation(
            isolation_id=d["isolation_id"],
            device_id=d.get("device_id", ""),
            mac_address=d["mac_address"],
            ip_address=d.get("ip_address", ""),
            original_vlan=VLANType(d["original_vlan"]),
            reason=d.get("reason", ""),
            threat_event_id=d.get("threat_event_id", ""),
            is_active=bool(d["is_active"]),
            isolated_at=d["isolated_at"],
            released_at=d.get("released_at"),
        )

    def _persist_guest(self, session: GuestSession) -> None:
        conn = self._open()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO guest_sessions
                   (session_id, mac_address, ip_address, hostname, bandwidth_limit_mbps,
                    expires_at, is_active, bytes_up, bytes_down, connected_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (session.session_id, session.mac_address, session.ip_address,
                 session.hostname, session.bandwidth_limit_mbps,
                 session.expires_at, int(session.is_active),
                 session.bytes_up, session.bytes_down, session.connected_at),
            )
            conn.commit()
        finally:
            conn.close()

    def _row_to_guest(self, row: sqlite3.Row) -> GuestSession:
        d = dict(row)
        return GuestSession(
            session_id=d["session_id"],
            mac_address=d["mac_address"],
            ip_address=d.get("ip_address", ""),
            hostname=d.get("hostname", ""),
            bandwidth_limit_mbps=d.get("bandwidth_limit_mbps"),
            expires_at=d.get("expires_at"),
            is_active=bool(d["is_active"]),
            bytes_up=d.get("bytes_up", 0),
            bytes_down=d.get("bytes_down", 0),
            connected_at=d["connected_at"],
        )

    def _audit(self, action: str, target: str, detail: str = "") -> None:
        try:
            from jarvis.security.db_protection import AuditLogger
            AuditLogger().log(actor="security_agent", action=action, target=target, detail=detail)
        except Exception:
            pass

    def _notify_if_auto(self, entry: BlockEntry) -> None:
        if not entry.auto_created:
            return
        try:
            from jarvis.notifier import notify
            notify(
                f"Auto-blocked: {entry.target} ({entry.target_type}). {entry.reason}",
                title="Jarvis Security",
            )
        except Exception:
            pass

    def _post_blackboard(self, content: str, urgency: str = "high") -> None:
        try:
            from jarvis.blackboard import SharedBlackboard
            SharedBlackboard().post(
                agent="security_agent",
                topic="security.action",
                content=content,
                urgency=urgency,
                ttl_days=3,
            )
        except Exception:
            pass
