"""Tests for jarvis/smarthome/ble_scanner.py"""
import pytest
from jarvis.smarthome.ble_scanner import BLEScanner, BLEDiscovery


def _disc(name="", address="AA:BB:CC:DD:EE:FF", rssi=-65, manufacturer_data=None, service_uuids=None):
    return BLEDiscovery(
        address=address,
        name=name,
        rssi=rssi,
        manufacturer_data=manufacturer_data or {},
        service_uuids=service_uuids or [],
    )


class TestBLEDiscovery:
    def test_to_dict(self):
        d = _disc("My Device", rssi=-70)
        dd = d.to_dict()
        assert dd["name"] == "My Device"
        assert dd["rssi"] == -70
        assert "discovered_at" in dd

    def test_manufacturer_data_serialised(self):
        d = _disc(manufacturer_data={0x004C: bytes([0x01, 0x02])})
        dd = d.to_dict()
        assert "4" in dd["manufacturer_data"] or "76" in dd["manufacturer_data"]


class TestBLEScanner:
    def test_init(self):
        scanner = BLEScanner()
        assert scanner.last_scan() == []

    def test_bleak_unavailable_returns_empty(self, monkeypatch):
        import jarvis.smarthome.ble_scanner as mod
        monkeypatch.setattr(mod, "_BLEAK_AVAILABLE", False)
        scanner = BLEScanner()
        result = scanner.scan(timeout=1.0)
        assert result == []

    def test_register_matcher(self):
        scanner = BLEScanner()
        scanner.register_matcher("test", lambda d: "test" if d.name == "test" else None)
        # No error; verify it's registered
        result = scanner._match(_disc("test"))
        assert result == "test"

    def test_matcher_returns_none_for_unknown(self):
        scanner = BLEScanner()
        scanner.register_matcher("hubspace", lambda d: "hubspace" if "hubspace" in d.name.lower() else None)
        result = scanner._match(_disc("Random Device"))
        assert result is None

    def test_classify_with_match(self):
        scanner = BLEScanner()
        scanner.register_matcher("hubspace", lambda d: "hubspace" if "hubspace" in d.name.lower() else None)
        discoveries = [_disc("HubSpace Light 1"), _disc("Unknown Sensor")]
        classified = scanner.classify(discoveries)
        assert classified[0]["adapter_type"] == "hubspace"
        assert classified[1]["adapter_type"] == "unknown"

    def test_classify_empty(self):
        scanner = BLEScanner()
        assert scanner.classify([]) == []

    def test_matcher_exception_is_ignored(self):
        scanner = BLEScanner()
        def bad_matcher(d):
            raise ValueError("oops")
        scanner.register_matcher("bad", bad_matcher)
        result = scanner._match(_disc("anything"))
        assert result is None

    def test_multiple_matchers_first_wins(self):
        scanner = BLEScanner()
        scanner.register_matcher("first", lambda d: "first" if d.rssi < -50 else None)
        scanner.register_matcher("second", lambda d: "second" if d.rssi < -50 else None)
        result = scanner._match(_disc(rssi=-60))
        assert result == "first"
