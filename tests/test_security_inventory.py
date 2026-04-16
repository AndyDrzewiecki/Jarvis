"""Tests for DeviceInventory."""
import os
import pytest
import tempfile

from jarvis.security.device_inventory import DeviceInventory, _guess_device_type
from jarvis.security.models import NetworkDevice, NetworkDeviceType, VLANType


@pytest.fixture
def inv(tmp_path):
    return DeviceInventory(db_path=str(tmp_path / "test_devices.db"))


class TestDeviceInventoryCRUD:
    def test_upsert_and_get_by_mac(self, inv):
        d = NetworkDevice.new(mac="aa:bb:cc:dd:ee:ff", ip="10.0.0.1", hostname="test-host")
        inv.upsert(d)
        result = inv.get_by_mac("aa:bb:cc:dd:ee:ff")
        assert result is not None
        assert result.hostname == "test-host"
        assert result.ip_address == "10.0.0.1"

    def test_upsert_updates_existing(self, inv):
        d = NetworkDevice.new(mac="aa:bb:cc:dd:ee:ff", ip="10.0.0.1")
        inv.upsert(d)
        d.hostname = "updated-host"
        d.ip_address = "10.0.0.2"
        inv.upsert(d)
        result = inv.get_by_mac("aa:bb:cc:dd:ee:ff")
        assert result.hostname == "updated-host"
        assert result.ip_address == "10.0.0.2"

    def test_get_by_id(self, inv):
        d = NetworkDevice.new(mac="11:22:33:44:55:66", ip="10.0.0.5")
        inv.upsert(d)
        result = inv.get_by_id(d.device_id)
        assert result is not None
        assert result.mac_address == "11:22:33:44:55:66"

    def test_get_by_id_not_found(self, inv):
        assert inv.get_by_id("nonexistent") is None

    def test_get_all(self, inv):
        for i in range(3):
            inv.upsert(NetworkDevice.new(mac=f"aa:bb:cc:dd:ee:{i:02x}", ip=f"10.0.0.{i+1}"))
        devices = inv.get_all()
        assert len(devices) == 3

    def test_get_all_online_only(self, inv):
        d1 = NetworkDevice.new(mac="aa:bb:cc:dd:ee:01", ip="10.0.0.1", is_online=True)
        d2 = NetworkDevice.new(mac="aa:bb:cc:dd:ee:02", ip="10.0.0.2", is_online=False)
        inv.upsert(d1)
        inv.upsert(d2)
        online = inv.get_all(online_only=True)
        assert len(online) == 1
        assert online[0].mac_address == "aa:bb:cc:dd:ee:01"

    def test_get_all_by_vlan(self, inv):
        d1 = NetworkDevice.new(mac="aa:bb:cc:dd:ee:01", ip="10.0.0.1", vlan=VLANType.IOT)
        d2 = NetworkDevice.new(mac="aa:bb:cc:dd:ee:02", ip="10.0.0.2", vlan=VLANType.MAIN)
        inv.upsert(d1)
        inv.upsert(d2)
        iot = inv.get_all(vlan=VLANType.IOT)
        assert len(iot) == 1
        assert iot[0].vlan == VLANType.IOT

    def test_delete(self, inv):
        d = NetworkDevice.new(mac="de:ad:be:ef:00:01", ip="10.0.0.10")
        inv.upsert(d)
        assert inv.get_by_mac("de:ad:be:ef:00:01") is not None
        inv.delete("de:ad:be:ef:00:01")
        assert inv.get_by_mac("de:ad:be:ef:00:01") is None

    def test_set_blocked(self, inv):
        d = NetworkDevice.new(mac="ff:ee:dd:cc:bb:aa", ip="10.0.0.20")
        inv.upsert(d)
        inv.set_blocked("ff:ee:dd:cc:bb:aa", True)
        result = inv.get_by_mac("ff:ee:dd:cc:bb:aa")
        assert result.is_blocked is True

    def test_set_isolated(self, inv):
        d = NetworkDevice.new(mac="ff:ee:dd:cc:bb:ab", ip="10.0.0.21")
        inv.upsert(d)
        inv.set_isolated("ff:ee:dd:cc:bb:ab", True, VLANType.QUARANTINE)
        result = inv.get_by_mac("ff:ee:dd:cc:bb:ab")
        assert result.is_isolated is True
        assert result.vlan == VLANType.QUARANTINE

    def test_update_threat_score(self, inv):
        d = NetworkDevice.new(mac="aa:00:00:00:00:01", ip="10.0.0.30")
        inv.upsert(d)
        inv.update_threat_score("aa:00:00:00:00:01", 88.5)
        result = inv.get_by_mac("aa:00:00:00:00:01")
        assert result.threat_score == pytest.approx(88.5)

    def test_mark_offline(self, inv):
        macs = []
        for i in range(3):
            mac = f"bb:{i:02x}:00:00:00:00"
            inv.upsert(NetworkDevice.new(mac=mac, ip=f"10.0.1.{i}"))
            macs.append(mac)
        inv.mark_offline(macs[:2])
        all_devices = inv.get_all()
        offline = [d for d in all_devices if not d.is_online]
        assert len(offline) == 2

    def test_count(self, inv):
        inv.upsert(NetworkDevice.new(mac="c1:00:00:00:00:01", ip="10.0.0.1"))
        inv.upsert(NetworkDevice.new(mac="c1:00:00:00:00:02", ip="10.0.0.2", is_blocked=True))
        counts = inv.count()
        assert counts["total"] == 2
        assert counts["blocked"] == 1
        assert counts["online"] == 2


class TestDiscoveryMerge:
    def test_merge_firewalla_devices(self, inv):
        fw_devices = [
            {"mac": "fa:11:22:33:44:55", "ip": "192.168.1.10", "name": "MyPC", "vendor": "Dell", "online": True},
            {"mac": "fa:11:22:33:44:56", "ip": "192.168.1.11", "name": "TV", "online": False},
        ]
        count = inv.merge_firewalla_devices(fw_devices)
        assert count == 2
        d = inv.get_by_mac("fa:11:22:33:44:55")
        assert d.hostname == "MyPC"
        assert d.vendor == "Dell"
        assert d.is_online is True

    def test_merge_firewalla_updates_existing(self, inv):
        inv.upsert(NetworkDevice.new(mac="fa:11:22:33:44:55", ip="192.168.1.10", hostname="OldName"))
        inv.merge_firewalla_devices([{"mac": "fa:11:22:33:44:55", "ip": "192.168.1.10", "name": "NewName", "online": True}])
        d = inv.get_by_mac("fa:11:22:33:44:55")
        assert d.hostname == "NewName"

    def test_merge_firewalla_skips_missing_mac(self, inv):
        count = inv.merge_firewalla_devices([{"ip": "192.168.1.10"}])
        assert count == 0

    def test_merge_aruba_clients(self, inv):
        aruba_clients = [
            {"mac": "ab:cd:ef:01:02:03", "ip": "192.168.1.20", "ssid": "JarvisMain", "signal": -65},
            {"mac": "ab:cd:ef:01:02:04", "ip": "192.168.1.21", "ssid": "JarvisGuest"},
        ]
        count = inv.merge_aruba_clients(aruba_clients)
        assert count == 2
        d = inv.get_by_mac("ab:cd:ef:01:02:03")
        assert d.ssid == "JarvisMain"
        assert d.signal_dbm == -65

    def test_merge_aruba_updates_existing(self, inv):
        inv.upsert(NetworkDevice.new(mac="ab:cd:ef:01:02:03", ip="old-ip", ssid="OldSSID"))
        inv.merge_aruba_clients([{"mac": "ab:cd:ef:01:02:03", "ip": "new-ip", "ssid": "NewSSID"}])
        d = inv.get_by_mac("ab:cd:ef:01:02:03")
        assert d.ssid == "NewSSID"


class TestGuessDeviceType:
    def test_android_phone(self):
        assert _guess_device_type({"os_type": "Android"}) == NetworkDeviceType.PHONE

    def test_ios_phone(self):
        assert _guess_device_type({"os_type": "iOS"}) == NetworkDeviceType.PHONE

    def test_windows_computer(self):
        assert _guess_device_type({"os_type": "Windows"}) == NetworkDeviceType.COMPUTER

    def test_camera_name(self):
        assert _guess_device_type({"name": "Nest Camera"}) == NetworkDeviceType.CAMERA

    def test_tv_name(self):
        assert _guess_device_type({"name": "Roku TV"}) == NetworkDeviceType.SMART_TV

    def test_guest_ssid(self):
        assert _guess_device_type({"ssid": "JarvisGuest"}) == NetworkDeviceType.GUEST

    def test_unknown(self):
        assert _guess_device_type({}) == NetworkDeviceType.UNKNOWN
