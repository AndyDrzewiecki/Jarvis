"""Tests for Phase 7 security data models."""
import pytest
from datetime import datetime, timezone

from jarvis.security.models import (
    NetworkDevice, NetworkDeviceType, VLANType,
    ThreatEvent, ThreatLevel, ThreatCategory,
    FirewallRule, RuleAction,
    TrafficFlow,
    AnomalyAlert,
    GuestSession,
    AuditLogEntry,
    BlockEntry,
    DeviceIsolation,
)


class TestNetworkDevice:
    def test_new_factory(self):
        d = NetworkDevice.new(mac="aa:bb:cc:dd:ee:ff", ip="192.168.1.1")
        assert d.mac_address == "aa:bb:cc:dd:ee:ff"
        assert d.ip_address == "192.168.1.1"
        assert d.device_id  # UUID generated

    def test_to_dict_roundtrip(self):
        d = NetworkDevice.new(
            mac="aa:bb:cc:dd:ee:ff",
            ip="10.0.0.5",
            hostname="my-router",
            vendor="Netgear",
            device_type=NetworkDeviceType.ROUTER,
            vlan=VLANType.MAIN,
            is_blocked=True,
            threat_score=55.0,
        )
        d2 = NetworkDevice.from_dict(d.to_dict())
        assert d2.mac_address == d.mac_address
        assert d2.device_type == NetworkDeviceType.ROUTER
        assert d2.is_blocked is True
        assert d2.threat_score == 55.0
        assert d2.vlan == VLANType.MAIN

    def test_defaults(self):
        d = NetworkDevice.new(mac="x", ip="y")
        assert d.device_type == NetworkDeviceType.UNKNOWN
        assert d.vlan == VLANType.MAIN
        assert d.threat_score == 0.0
        assert d.is_online is True
        assert d.is_blocked is False
        assert d.is_isolated is False

    def test_vlan_enum_values(self):
        assert VLANType.QUARANTINE.value == "quarantine"
        assert VLANType.GUEST.value == "guest"

    def test_device_type_enum_values(self):
        assert NetworkDeviceType.IOT.value == "iot"
        assert NetworkDeviceType.CAMERA.value == "camera"


class TestThreatEvent:
    def test_new_factory(self):
        e = ThreatEvent.new(
            level=ThreatLevel.HIGH,
            category=ThreatCategory.PORT_SCAN,
            description="Port scan detected",
            source_ip="1.2.3.4",
            score=75.0,
        )
        assert e.level == ThreatLevel.HIGH
        assert e.category == ThreatCategory.PORT_SCAN
        assert e.score == 75.0
        assert e.event_id  # UUID

    def test_to_dict_roundtrip(self):
        e = ThreatEvent.new(
            level=ThreatLevel.CRITICAL,
            category=ThreatCategory.MALWARE,
            description="Malware C2 communication",
            source_ip="5.6.7.8",
            dest_port=4444,
            score=92.0,
            auto_blocked=True,
        )
        e2 = ThreatEvent.from_dict(e.to_dict())
        assert e2.level == ThreatLevel.CRITICAL
        assert e2.category == ThreatCategory.MALWARE
        assert e2.dest_port == 4444
        assert e2.auto_blocked is True
        assert e2.score == 92.0

    def test_resolved_defaults_false(self):
        e = ThreatEvent.new(ThreatLevel.LOW, ThreatCategory.UNKNOWN, "test")
        assert e.resolved is False
        assert e.resolved_at is None


class TestFirewallRule:
    def test_new_and_roundtrip(self):
        r = FirewallRule.new(
            action=RuleAction.BLOCK,
            target="1.2.3.4",
            target_type="ip",
            reason="C2 server",
            auto_created=True,
        )
        d = r.to_dict()
        r2 = FirewallRule.from_dict(d)
        assert r2.action == RuleAction.BLOCK
        assert r2.target == "1.2.3.4"
        assert r2.auto_created is True

    def test_domain_target(self):
        r = FirewallRule.new(action=RuleAction.BLOCK, target="evil.com", target_type="domain")
        assert r.target_type == "domain"


class TestTrafficFlow:
    def test_new(self):
        f = TrafficFlow.new(
            src_ip="192.168.1.10",
            dst_ip="8.8.8.8",
            protocol="udp",
            dst_port=53,
            bytes_sent=512,
            bytes_recv=256,
        )
        assert f.src_ip == "192.168.1.10"
        assert f.dst_port == 53
        assert f.bytes_sent == 512

    def test_to_dict(self):
        f = TrafficFlow.new("1.1.1.1", "2.2.2.2", protocol="tcp", dst_port=80)
        d = f.to_dict()
        assert d["src_ip"] == "1.1.1.1"
        assert d["dst_port"] == 80


class TestAnomalyAlert:
    def test_new_computes_deviation(self):
        a = AnomalyAlert.new(
            device_mac="aa:bb:cc:dd:ee:ff",
            device_ip="10.0.0.1",
            metric="bytes_per_hour",
            baseline=1000.0,
            observed=3000.0,
            level=ThreatLevel.HIGH,
        )
        assert a.deviation_pct == pytest.approx(200.0, abs=0.1)
        assert a.level == ThreatLevel.HIGH

    def test_to_dict(self):
        a = AnomalyAlert.new("aa:bb", "1.1.1.1", "metric", 100.0, 150.0, level=ThreatLevel.LOW)
        d = a.to_dict()
        assert "deviation_pct" in d
        assert d["metric"] == "metric"


class TestGuestSession:
    def test_new(self):
        s = GuestSession.new(
            mac="11:22:33:44:55:66",
            ip="192.168.30.5",
            hostname="guest-phone",
            bandwidth_limit_mbps=10.0,
        )
        assert s.mac_address == "11:22:33:44:55:66"
        assert s.bandwidth_limit_mbps == 10.0
        assert s.is_active is True

    def test_to_dict(self):
        s = GuestSession.new("x", "y")
        d = s.to_dict()
        assert "connected_at" in d
        assert d["is_active"] is True


class TestAuditLogEntry:
    def test_new(self):
        e = AuditLogEntry.new(
            actor="api",
            action="block",
            target="1.2.3.4",
            ip_address="192.168.1.1",
            method="POST",
            endpoint="/api/security/block",
        )
        assert e.actor == "api"
        assert e.action == "block"
        assert e.entry_id  # UUID

    def test_to_dict(self):
        e = AuditLogEntry.new("api", "unblock", target="x.com")
        d = e.to_dict()
        assert d["actor"] == "api"
        assert "logged_at" in d


class TestBlockEntry:
    def test_new(self):
        b = BlockEntry.new(
            target="evil.com",
            target_type="domain",
            reason="malware",
            auto_created=True,
        )
        assert b.target == "evil.com"
        assert b.auto_created is True

    def test_to_dict(self):
        b = BlockEntry.new("1.2.3.4")
        d = b.to_dict()
        assert d["target"] == "1.2.3.4"
        assert "created_at" in d


class TestDeviceIsolation:
    def test_new(self):
        iso = DeviceIsolation.new(
            device_id="dev-1",
            mac="aa:bb:cc:dd:ee:ff",
            ip="10.0.0.5",
            original_vlan=VLANType.IOT,
            reason="malware",
        )
        assert iso.mac_address == "aa:bb:cc:dd:ee:ff"
        assert iso.original_vlan == VLANType.IOT
        assert iso.is_active is True

    def test_to_dict(self):
        iso = DeviceIsolation.new("d", "m", "i", VLANType.MAIN)
        d = iso.to_dict()
        assert d["original_vlan"] == "main"
        assert d["is_active"] is True
