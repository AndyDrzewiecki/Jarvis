"""Tests for jarvis/devices.py"""
import os
import pytest

import jarvis.devices as devices


@pytest.fixture(autouse=True)
def tmp_devices_path(tmp_path, monkeypatch):
    """Point JARVIS_DEVICES_PATH to an isolated temp file for every test."""
    devices_file = str(tmp_path / "devices.json")
    monkeypatch.setenv("JARVIS_DEVICES_PATH", devices_file)
    yield devices_file


class TestRegister:
    def test_register_creates_device(self):
        record = devices.register("tablet-kitchen-01", "kitchen", "Kitchen Tablet")
        assert record["device_id"] == "tablet-kitchen-01"
        assert record["profile"] == "kitchen"
        assert record["display_name"] == "Kitchen Tablet"
        assert "last_seen" in record

    def test_invalid_profile_normalized_to_default(self):
        record = devices.register("device-xyz", "invalid", "Unknown Device")
        assert record["profile"] == "default"


class TestListDevices:
    def test_list_devices_returns_all(self):
        devices.register("device-a", "kitchen", "Device A")
        devices.register("device-b", "garage", "Device B")
        result = devices.list_devices()
        ids = [d["device_id"] for d in result]
        assert "device-a" in ids
        assert "device-b" in ids
        assert len(result) == 2


class TestGetProfile:
    def test_get_profile_known_device(self):
        devices.register("tablet-kitchen-01", "kitchen", "Kitchen Tablet")
        profile = devices.get_profile("tablet-kitchen-01")
        assert profile == "kitchen"

    def test_get_profile_unknown_device_returns_default(self):
        profile = devices.get_profile("nonexistent-device")
        assert profile == "default"


class TestGetContextInjection:
    def test_get_context_injection_kitchen(self):
        devices.register("tablet-kitchen-01", "kitchen", "Kitchen Tablet")
        context = devices.get_context_injection("tablet-kitchen-01")
        assert "food" in context.lower() or "kitchen" in context.lower()

    def test_get_context_injection_none_device_returns_default(self):
        context = devices.get_context_injection(None)
        assert context == devices.PROFILE_CONTEXTS["default"]
