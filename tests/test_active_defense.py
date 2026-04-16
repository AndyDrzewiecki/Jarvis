"""Tests for ActiveDefense."""
import pytest
from unittest.mock import MagicMock, patch

from jarvis.security.active_defense import ActiveDefense, AUTO_BLOCK_SCORE, AUTO_ISOLATE_SCORE
from jarvis.security.models import (
    NetworkDevice, NetworkDeviceType, VLANType,
    ThreatEvent, ThreatCategory, ThreatLevel,
)


def _mock_fw():
    fw = MagicMock()
    fw.create_block_rule.return_value = "fw-rule-123"
    fw.delete_rule.return_value = True
    fw.configured = True
    return fw


def _mock_aruba():
    aruba = MagicMock()
    aruba.move_client_to_vlan.return_value = True
    aruba.disconnect_client.return_value = True
    aruba.configured = True
    return aruba


@pytest.fixture
def defense(tmp_path):
    return ActiveDefense(
        db_path=str(tmp_path / "test_defense.db"),
        firewalla=_mock_fw(),
        aruba=_mock_aruba(),
    )


class TestBlocking:
    def test_block_ip(self, defense):
        entry = defense.block("1.2.3.4", reason="test block")
        assert entry.target == "1.2.3.4"
        assert entry.target_type == "ip"
        assert entry.firewalla_rule_id == "fw-rule-123"

    def test_block_domain(self, defense):
        entry = defense.block("evil.com", target_type="domain", reason="malware")
        assert entry.target == "evil.com"
        assert entry.target_type == "domain"

    def test_block_persisted(self, defense):
        defense.block("9.9.9.9", reason="persist test")
        blocks = defense.get_blocks()
        assert any(b.target == "9.9.9.9" for b in blocks)

    def test_is_blocked_true(self, defense):
        defense.block("5.5.5.5")
        assert defense.is_blocked("5.5.5.5") is True

    def test_is_blocked_false(self, defense):
        assert defense.is_blocked("not-blocked") is False

    def test_unblock(self, defense):
        defense.block("7.7.7.7")
        assert defense.is_blocked("7.7.7.7") is True
        ok = defense.unblock("7.7.7.7")
        assert ok is True
        assert defense.is_blocked("7.7.7.7") is False

    def test_unblock_nonexistent(self, defense):
        assert defense.unblock("not-blocked") is False

    def test_block_calls_firewalla(self, defense):
        defense.block("4.4.4.4", target_type="ip", reason="test")
        defense._firewalla.create_block_rule.assert_called_once()

    def test_unblock_calls_firewalla_delete(self, defense):
        defense.block("4.4.4.5")
        defense.unblock("4.4.4.5")
        defense._firewalla.delete_rule.assert_called_once_with("fw-rule-123")

    def test_auto_created_flag(self, defense):
        entry = defense.block("6.6.6.6", auto_created=True)
        assert entry.auto_created is True

    def test_block_with_ttl(self, defense):
        entry = defense.block("8.8.8.8", ttl_hours=24)
        assert entry.expires_at is not None

    def test_expire_blocks(self, defense):
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = defense._open()
        conn.execute(
            """INSERT INTO block_entries
               (block_id, target, target_type, reason, auto_created, expires_at, created_at, firewalla_rule_id)
               VALUES ('expired-1','10.0.0.1','ip','test',0,?,?,'')""",
            (past, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
        count = defense.expire_blocks()
        assert count == 1

    def test_get_blocks_active_only(self, defense):
        defense.block("11.11.11.11")
        blocks = defense.get_blocks(active_only=True)
        assert all(b.target != "expired" for b in blocks)


class TestIsolation:
    def test_isolate_device(self, defense):
        iso = defense.isolate_device(
            device_id="dev-1",
            mac="aa:bb:cc:dd:ee:ff",
            ip="192.168.1.5",
            original_vlan=VLANType.IOT,
            reason="malware detected",
        )
        assert iso.mac_address == "aa:bb:cc:dd:ee:ff"
        assert iso.original_vlan == VLANType.IOT
        assert iso.is_active is True
        defense._aruba.move_client_to_vlan.assert_called_once_with("aa:bb:cc:dd:ee:ff", 99)

    def test_release_device(self, defense):
        defense.isolate_device(
            device_id="dev-2",
            mac="11:22:33:44:55:66",
            ip="192.168.1.6",
            original_vlan=VLANType.IOT,
            reason="test",
        )
        ok = defense.release_device("11:22:33:44:55:66")
        assert ok is True
        isolations = defense.get_isolations(active_only=True)
        assert not any(i.mac_address == "11:22:33:44:55:66" for i in isolations)

    def test_release_nonexistent(self, defense):
        assert defense.release_device("not-isolated") is False

    def test_get_isolations(self, defense):
        defense.isolate_device("d1", "aa:00:00:00:00:01", "10.0.0.1", VLANType.IOT)
        defense.isolate_device("d2", "aa:00:00:00:00:02", "10.0.0.2", VLANType.MAIN)
        isos = defense.get_isolations(active_only=True)
        assert len(isos) == 2


class TestAutoRespond:
    def _event(self, score, source_ip="1.2.3.4", source_mac="", device_type=NetworkDeviceType.COMPUTER):
        return ThreatEvent.new(
            level=ThreatLevel.HIGH if score >= 70 else ThreatLevel.MEDIUM,
            category=ThreatCategory.PORT_SCAN,
            description="test",
            score=score,
            source_ip=source_ip,
            source_mac=source_mac,
        )

    def test_auto_block_high_score(self, defense):
        event = self._event(AUTO_BLOCK_SCORE + 1.0, source_ip="5.5.5.5")
        actions = defense.auto_respond(event)
        assert actions["blocked"] == "5.5.5.5"

    def test_no_auto_block_low_score(self, defense):
        event = self._event(AUTO_BLOCK_SCORE - 1.0, source_ip="6.6.6.6")
        actions = defense.auto_respond(event)
        assert actions["blocked"] is False

    def test_no_duplicate_block(self, defense):
        defense.block("7.7.7.7")
        event = self._event(AUTO_BLOCK_SCORE + 1.0, source_ip="7.7.7.7")
        actions = defense.auto_respond(event)
        # Should not block again
        assert actions["blocked"] is False

    def test_auto_isolate_iot_device(self, defense, tmp_path):
        from jarvis.security.device_inventory import DeviceInventory
        inventory = DeviceInventory(db_path=str(tmp_path / "inv.db"))
        iot_device = NetworkDevice.new(
            mac="iot:mac:00:01",
            ip="10.20.0.5",
            device_type=NetworkDeviceType.IOT,
            vlan=VLANType.IOT,
        )
        inventory.upsert(iot_device)

        event = ThreatEvent.new(
            level=ThreatLevel.HIGH,
            category=ThreatCategory.MALWARE,
            description="IoT malware",
            score=AUTO_ISOLATE_SCORE + 5.0,
            source_mac="iot:mac:00:01",
        )
        actions = defense.auto_respond(event, inventory=inventory)
        assert actions["isolated"] == "iot:mac:00:01"


class TestGuestManagement:
    def test_register_guest(self, defense):
        session = defense.register_guest(
            mac="guest:mac:01",
            ip="192.168.30.5",
            hostname="guest-phone",
            bandwidth_limit_mbps=10.0,
            ttl_hours=8,
        )
        assert session.mac_address == "guest:mac:01"
        assert session.expires_at is not None
        assert session.is_active is True

    def test_get_guest_sessions(self, defense):
        defense.register_guest("g1:mac", "192.168.30.6")
        defense.register_guest("g2:mac", "192.168.30.7")
        sessions = defense.get_guest_sessions()
        assert len(sessions) == 2

    def test_expire_guest_sessions(self, defense):
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = defense._open()
        conn.execute(
            """INSERT INTO guest_sessions
               (session_id, mac_address, ip_address, hostname, is_active, bytes_up, bytes_down, connected_at, expires_at)
               VALUES ('gs-1','guest:x','192.168.30.99','',1,0,0,?,?)""",
            (datetime.now(timezone.utc).isoformat(), past),
        )
        conn.commit()
        conn.close()
        count = defense.expire_guest_sessions()
        assert count == 1

    def test_expire_all_guests(self, defense):
        defense.register_guest("g:mac:1", "192.168.30.10")
        defense.register_guest("g:mac:2", "192.168.30.11")
        count = defense.expire_all_guests()
        assert count == 2
        remaining = defense.get_guest_sessions(active_only=True)
        assert len(remaining) == 0

    def test_update_guest_usage(self, defense):
        defense.register_guest("g:mac:3", "192.168.30.12")
        defense.update_guest_usage("g:mac:3", bytes_up=1024, bytes_down=4096)
        sessions = defense.get_guest_sessions()
        s = next(s for s in sessions if s.mac_address == "g:mac:3")
        assert s.bytes_up == 1024
        assert s.bytes_down == 4096
