"""Tests for Phase 7 security API endpoints in server.py."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


def _mock_inventory():
    inv = MagicMock()
    inv.count.return_value = {"total": 5, "online": 4, "offline": 1, "blocked": 1, "isolated": 0, "high_risk": 0}
    inv.get_all.return_value = []
    return inv


def _mock_threat_engine():
    te = MagicMock()
    te.count_by_level.return_value = {"high": 1}
    te.get_events.return_value = []
    te.resolve_event.return_value = True
    return te


def _mock_anomaly_detector():
    ad = MagicMock()
    ad.count_unresolved.return_value = 2
    ad.get_alerts.return_value = []
    ad.resolve_alert.return_value = True
    return ad


def _mock_defense():
    d = MagicMock()
    d.get_blocks.return_value = []
    d.get_isolations.return_value = []
    d.get_guest_sessions.return_value = []
    from jarvis.security.models import BlockEntry
    d.block.return_value = BlockEntry.new(target="1.2.3.4", reason="test")
    d.unblock.return_value = True
    from jarvis.security.models import DeviceIsolation, VLANType
    d.isolate_device.return_value = DeviceIsolation.new("d1", "aa:bb", "10.0.0.1", VLANType.MAIN)
    d.release_device.return_value = True
    from jarvis.security.models import GuestSession
    d.register_guest.return_value = GuestSession.new("g:mac", "10.0.0.5")
    d.expire_all_guests.return_value = 3
    return d


def _mock_firewalla():
    fw = MagicMock()
    fw.configured = False
    fw.get_flows.return_value = []
    fw.get_rules.return_value = []
    fw.get_rogue_aps = MagicMock(return_value=[])
    return fw


def _mock_aruba():
    aruba = MagicMock()
    aruba.configured = False
    aruba.get_aps.return_value = []
    aruba.get_rogue_aps.return_value = []
    return aruba


def _mock_audit():
    al = MagicMock()
    al.query.return_value = []
    al.log.return_value = None
    return al


class TestSecurityDashboard:
    def test_dashboard_200(self, client):
        with (
            patch("server._get_inventory", return_value=_mock_inventory()),
            patch("server._get_threat_engine", return_value=_mock_threat_engine()),
            patch("server._get_anomaly_detector", return_value=_mock_anomaly_detector()),
            patch("server._get_defense", return_value=_mock_defense()),
            patch("server._get_firewalla", return_value=_mock_firewalla()),
            patch("server._get_aruba", return_value=_mock_aruba()),
        ):
            r = client.get("/api/security/dashboard")
            assert r.status_code == 200
            data = r.json()
            assert "devices" in data
            assert "threats" in data
            assert "defense" in data

    def test_dashboard_has_device_counts(self, client):
        with (
            patch("server._get_inventory", return_value=_mock_inventory()),
            patch("server._get_threat_engine", return_value=_mock_threat_engine()),
            patch("server._get_anomaly_detector", return_value=_mock_anomaly_detector()),
            patch("server._get_defense", return_value=_mock_defense()),
            patch("server._get_firewalla", return_value=_mock_firewalla()),
            patch("server._get_aruba", return_value=_mock_aruba()),
        ):
            r = client.get("/api/security/dashboard")
            assert r.json()["devices"]["total"] == 5


class TestSecurityDevices:
    def test_list_devices(self, client):
        with patch("server._get_inventory", return_value=_mock_inventory()):
            r = client.get("/api/security/devices")
            assert r.status_code == 200
            assert "devices" in r.json()

    def test_list_devices_online_only(self, client):
        with patch("server._get_inventory", return_value=_mock_inventory()):
            r = client.get("/api/security/devices?online_only=true")
            assert r.status_code == 200

    def test_list_devices_invalid_vlan(self, client):
        with patch("server._get_inventory", return_value=_mock_inventory()):
            r = client.get("/api/security/devices?vlan=invalid")
            assert r.status_code == 400

    def test_list_devices_invalid_device_type(self, client):
        with patch("server._get_inventory", return_value=_mock_inventory()):
            r = client.get("/api/security/devices?device_type=invalid")
            assert r.status_code == 400


class TestSecurityScan:
    def test_scan_endpoint(self, client):
        fw = _mock_firewalla()
        fw.configured = True
        fw.get_devices.return_value = []
        aruba = _mock_aruba()
        aruba.configured = False
        with (
            patch("server._get_firewalla", return_value=fw),
            patch("server._get_aruba", return_value=aruba),
            patch("server._get_inventory", return_value=_mock_inventory()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/scan")
            assert r.status_code == 200
            data = r.json()
            assert "firewalla_devices" in data
            assert "aruba_clients" in data


class TestSecurityThreats:
    def test_get_threats(self, client):
        with patch("server._get_threat_engine", return_value=_mock_threat_engine()):
            r = client.get("/api/security/threats")
            assert r.status_code == 200
            assert "threats" in r.json()

    def test_get_threats_invalid_level(self, client):
        with patch("server._get_threat_engine", return_value=_mock_threat_engine()):
            r = client.get("/api/security/threats?level=invalid")
            assert r.status_code == 400

    def test_resolve_threat(self, client):
        with (
            patch("server._get_threat_engine", return_value=_mock_threat_engine()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/threats/test-event-id/resolve")
            assert r.status_code == 200
            assert r.json()["resolved"] == "test-event-id"

    def test_resolve_threat_not_found(self, client):
        te = _mock_threat_engine()
        te.resolve_event.return_value = False
        with (
            patch("server._get_threat_engine", return_value=te),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/threats/nonexistent/resolve")
            assert r.status_code == 404


class TestSecurityBlocking:
    def test_get_blocks(self, client):
        with patch("server._get_defense", return_value=_mock_defense()):
            r = client.get("/api/security/blocks")
            assert r.status_code == 200
            assert "blocks" in r.json()

    def test_block_ip(self, client):
        with (
            patch("server._get_defense", return_value=_mock_defense()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/block", json={"target": "1.2.3.4", "reason": "test"})
            assert r.status_code == 201
            assert "target" in r.json()

    def test_unblock(self, client):
        with (
            patch("server._get_defense", return_value=_mock_defense()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.delete("/api/security/block/1.2.3.4")
            assert r.status_code == 200

    def test_unblock_not_found(self, client):
        d = _mock_defense()
        d.unblock.return_value = False
        with (
            patch("server._get_defense", return_value=d),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.delete("/api/security/block/not-blocked")
            assert r.status_code == 404


class TestSecurityIsolation:
    def test_get_isolations(self, client):
        with patch("server._get_defense", return_value=_mock_defense()):
            r = client.get("/api/security/isolations")
            assert r.status_code == 200

    def test_isolate_device(self, client):
        with (
            patch("server._get_defense", return_value=_mock_defense()),
        ):
            r = client.post("/api/security/isolate/aa:bb:cc:dd:ee:ff", json={
                "device_id": "dev-1",
                "ip_address": "10.0.0.5",
                "original_vlan": "iot",
                "reason": "malware",
            })
            assert r.status_code == 201

    def test_isolate_invalid_vlan(self, client):
        with patch("server._get_defense", return_value=_mock_defense()):
            r = client.post("/api/security/isolate/aa:bb:cc", json={"original_vlan": "invalid"})
            assert r.status_code == 400

    def test_release_device(self, client):
        with (
            patch("server._get_defense", return_value=_mock_defense()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/release/aa:bb:cc:dd:ee:ff")
            assert r.status_code == 200

    def test_release_not_found(self, client):
        d = _mock_defense()
        d.release_device.return_value = False
        with (
            patch("server._get_defense", return_value=d),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/release/not-isolated")
            assert r.status_code == 404


class TestSecurityAnomalies:
    def test_get_anomalies(self, client):
        with patch("server._get_anomaly_detector", return_value=_mock_anomaly_detector()):
            r = client.get("/api/security/anomalies")
            assert r.status_code == 200
            assert "anomalies" in r.json()

    def test_resolve_anomaly(self, client):
        with (
            patch("server._get_anomaly_detector", return_value=_mock_anomaly_detector()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/anomalies/test-alert/resolve")
            assert r.status_code == 200

    def test_resolve_anomaly_not_found(self, client):
        ad = _mock_anomaly_detector()
        ad.resolve_alert.return_value = False
        with (
            patch("server._get_anomaly_detector", return_value=ad),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/anomalies/nope/resolve")
            assert r.status_code == 404


class TestSecurityGuest:
    def test_get_guest(self, client):
        with patch("server._get_defense", return_value=_mock_defense()):
            r = client.get("/api/security/guest")
            assert r.status_code == 200

    def test_register_guest(self, client):
        with patch("server._get_defense", return_value=_mock_defense()):
            r = client.post("/api/security/guest/register", json={
                "mac_address": "aa:bb:cc:dd:ee:ff",
                "ip_address": "192.168.30.5",
                "ttl_hours": 24,
            })
            assert r.status_code == 201

    def test_expire_guest(self, client):
        with (
            patch("server._get_defense", return_value=_mock_defense()),
            patch("server._get_audit_logger", return_value=_mock_audit()),
        ):
            r = client.post("/api/security/guest/expire")
            assert r.status_code == 200
            assert r.json()["expired"] == 3


class TestSecurityTrafficAndRules:
    def test_get_traffic(self, client):
        fw = _mock_firewalla()
        fw.get_flows.return_value = [{"sh": "1.1.1.1", "dh": "2.2.2.2"}]
        with patch("server._get_firewalla", return_value=fw):
            r = client.get("/api/security/traffic")
            assert r.status_code == 200
            assert r.json()["total"] == 1

    def test_get_rules(self, client):
        fw = _mock_firewalla()
        fw.get_rules.return_value = [{"id": "r1", "action": "block"}]
        with patch("server._get_firewalla", return_value=fw):
            r = client.get("/api/security/rules")
            assert r.status_code == 200
            assert r.json()["total"] == 1


class TestSecurityAudit:
    def test_get_audit(self, client):
        with patch("server._get_audit_logger", return_value=_mock_audit()):
            r = client.get("/api/security/audit")
            assert r.status_code == 200
            assert "entries" in r.json()

    def test_get_audit_with_filters(self, client):
        with patch("server._get_audit_logger", return_value=_mock_audit()):
            r = client.get("/api/security/audit?actor=api&action=block")
            assert r.status_code == 200


class TestSecurityAPs:
    def test_get_aps(self, client):
        aruba = _mock_aruba()
        aruba.get_aps.return_value = [{"name": "AP-1", "status": "up"}]
        with patch("server._get_aruba", return_value=aruba):
            r = client.get("/api/security/aps")
            assert r.status_code == 200
            assert r.json()["total"] == 1

    def test_get_rogue_aps(self, client):
        aruba = _mock_aruba()
        aruba.get_rogue_aps.return_value = [{"ssid": "EvilNet", "classification": "rogue"}]
        with patch("server._get_aruba", return_value=aruba):
            r = client.get("/api/security/rogue-aps")
            assert r.status_code == 200
            assert r.json()["total"] == 1


class TestSecurityDBCheck:
    def test_db_check(self, client):
        with (
            patch("server._get_audit_logger", return_value=_mock_audit()),
            patch("jarvis.security.db_protection.SecurityScanner.get_db_sizes", return_value={"memory": 0}),
            patch("jarvis.security.db_protection.SecurityScanner.check_jarvis_db_permissions", return_value=[]),
            patch("jarvis.security.db_protection.SecurityScanner.integrity_check", return_value=True),
        ):
            r = client.post("/api/security/db/check")
            assert r.status_code == 200
            data = r.json()
            assert "db_sizes" in data
            assert "integrity" in data
