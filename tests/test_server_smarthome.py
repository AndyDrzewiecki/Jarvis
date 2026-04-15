"""Tests for Phase 6 smart home endpoints in server.py"""
import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def clean_smarthome_db(tmp_path, monkeypatch):
    """Give each test its own isolated smart home DB."""
    db = str(tmp_path / "test_sh_server.db")
    monkeypatch.setenv("JARVIS_SMARTHOME_DB", db)
    # Reset singleton instances between tests
    import server
    server._sh_registry = None
    server._sh_automation = None
    server._sh_voice = None
    server._sh_ble = None
    server._ADAPTER_REGISTRY = {}
    yield
    server._sh_registry = None
    server._sh_automation = None
    server._sh_voice = None
    server._sh_ble = None
    server._ADAPTER_REGISTRY = {}


@pytest.fixture
def client():
    from server import app
    return TestClient(app)


# ── Device endpoints ──────────────────────────────────────────────────────────

class TestDeviceEndpoints:
    def test_list_devices_empty(self, client):
        r = client.get("/api/smarthome/devices")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_register_device(self, client):
        r = client.post("/api/smarthome/devices", json={
            "display_name": "Kitchen Light",
            "device_type": "light",
            "protocol": "ble",
            "room": "kitchen",
            "adapter_type": "mock",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["display_name"] == "Kitchen Light"
        assert data["room"] == "kitchen"
        assert "device_id" in data

    def test_list_devices_after_register(self, client):
        client.post("/api/smarthome/devices", json={
            "display_name": "Light 1", "device_type": "light",
            "protocol": "ble", "room": "kitchen", "adapter_type": "mock",
        })
        r = client.get("/api/smarthome/devices")
        assert r.json()["total"] == 1

    def test_get_device(self, client):
        reg = client.post("/api/smarthome/devices", json={
            "display_name": "Bedroom Light", "device_type": "light",
            "protocol": "ble", "room": "bedroom", "adapter_type": "mock",
        })
        device_id = reg.json()["device_id"]
        r = client.get(f"/api/smarthome/devices/{device_id}")
        assert r.status_code == 200
        assert r.json()["device_id"] == device_id

    def test_get_device_not_found(self, client):
        r = client.get("/api/smarthome/devices/nonexistent")
        assert r.status_code == 404

    def test_delete_device(self, client):
        reg = client.post("/api/smarthome/devices", json={
            "display_name": "Temp Device", "device_type": "switch",
            "protocol": "mqtt", "room": "office", "adapter_type": "mock",
        })
        device_id = reg.json()["device_id"]
        r = client.delete(f"/api/smarthome/devices/{device_id}")
        assert r.status_code == 200
        assert client.get(f"/api/smarthome/devices/{device_id}").status_code == 404

    def test_delete_device_not_found(self, client):
        r = client.delete("/api/smarthome/devices/ghost")
        assert r.status_code == 404

    def test_register_device_invalid_type(self, client):
        r = client.post("/api/smarthome/devices", json={
            "display_name": "Bad", "device_type": "invalid_type",
            "protocol": "ble", "room": "kitchen",
        })
        assert r.status_code == 400

    def test_filter_by_room(self, client):
        client.post("/api/smarthome/devices", json={
            "display_name": "K Light", "device_type": "light",
            "protocol": "ble", "room": "kitchen", "adapter_type": "mock",
        })
        client.post("/api/smarthome/devices", json={
            "display_name": "B Light", "device_type": "light",
            "protocol": "ble", "room": "bedroom", "adapter_type": "mock",
        })
        r = client.get("/api/smarthome/devices?room=kitchen")
        assert r.json()["total"] == 1

    def test_filter_by_type(self, client):
        client.post("/api/smarthome/devices", json={
            "display_name": "Light", "device_type": "light",
            "protocol": "ble", "room": "kitchen", "adapter_type": "mock",
        })
        client.post("/api/smarthome/devices", json={
            "display_name": "TV", "device_type": "tv",
            "protocol": "ble", "room": "living room", "adapter_type": "mock",
        })
        r = client.get("/api/smarthome/devices?device_type=tv")
        assert r.json()["total"] == 1


# ── Device command ────────────────────────────────────────────────────────────

class TestDeviceCommandEndpoint:
    def _register(self, client):
        r = client.post("/api/smarthome/devices", json={
            "display_name": "Light", "device_type": "light",
            "protocol": "ble", "room": "kitchen", "adapter_type": "mock",
        })
        return r.json()["device_id"]

    def test_turn_on(self, client):
        dev_id = self._register(client)
        r = client.post(f"/api/smarthome/devices/{dev_id}/command", json={
            "command": "turn_on", "params": {}
        })
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_set_brightness(self, client):
        dev_id = self._register(client)
        r = client.post(f"/api/smarthome/devices/{dev_id}/command", json={
            "command": "set_brightness", "params": {"value": 50}
        })
        assert r.status_code == 200

    def test_command_device_not_found(self, client):
        r = client.post("/api/smarthome/devices/ghost/command", json={
            "command": "turn_on"
        })
        assert r.status_code == 404


# ── BLE scan ──────────────────────────────────────────────────────────────────

class TestBLEScan:
    def test_ble_scan_endpoint(self, client, monkeypatch):
        import jarvis.smarthome.ble_scanner as mod
        monkeypatch.setattr(mod, "_BLEAK_AVAILABLE", False)
        r = client.post("/api/smarthome/scan/ble?timeout=1.0")
        assert r.status_code == 200
        data = r.json()
        assert "found" in data
        assert data["bleak_available"] is False


# ── Automation endpoints ──────────────────────────────────────────────────────

class TestAutomationEndpoints:
    def _create_rule(self, client, name="Test Rule"):
        return client.post("/api/smarthome/automations", json={
            "name": name,
            "trigger": {"trigger_type": "manual"},
            "actions": [{"action_type": "notify", "message": "Hello"}],
        })

    def test_list_automations_empty(self, client):
        r = client.get("/api/smarthome/automations")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_create_automation(self, client):
        r = self._create_rule(client)
        assert r.status_code == 201
        assert r.json()["name"] == "Test Rule"

    def test_get_automation(self, client):
        rule_id = self._create_rule(client).json()["rule_id"]
        r = client.get(f"/api/smarthome/automations/{rule_id}")
        assert r.status_code == 200
        assert r.json()["rule_id"] == rule_id

    def test_get_automation_not_found(self, client):
        r = client.get("/api/smarthome/automations/ghost")
        assert r.status_code == 404

    def test_update_automation(self, client):
        rule_id = self._create_rule(client).json()["rule_id"]
        r = client.put(f"/api/smarthome/automations/{rule_id}", json={
            "name": "Updated Name",
            "trigger": {"trigger_type": "manual"},
            "actions": [],
        })
        assert r.status_code == 200
        assert r.json()["name"] == "Updated Name"

    def test_delete_automation(self, client):
        rule_id = self._create_rule(client).json()["rule_id"]
        r = client.delete(f"/api/smarthome/automations/{rule_id}")
        assert r.status_code == 200
        assert client.get(f"/api/smarthome/automations/{rule_id}").status_code == 404

    def test_trigger_automation(self, client):
        rule_id = self._create_rule(client).json()["rule_id"]
        r = client.post(f"/api/smarthome/automations/{rule_id}/trigger")
        assert r.status_code == 200
        data = r.json()
        assert "results" in data

    def test_trigger_not_found(self, client):
        r = client.post("/api/smarthome/automations/ghost/trigger")
        assert r.status_code == 404

    def test_automation_log(self, client):
        rule_id = self._create_rule(client).json()["rule_id"]
        client.post(f"/api/smarthome/automations/{rule_id}/trigger")
        r = client.get("/api/smarthome/automations/log")
        assert r.status_code == 200
        assert len(r.json()["log"]) >= 1

    def test_create_time_automation(self, client):
        r = client.post("/api/smarthome/automations", json={
            "name": "9pm dim",
            "trigger": {"trigger_type": "time", "time_str": "21:00"},
            "actions": [],
        })
        assert r.status_code == 201
        assert r.json()["trigger"]["time_str"] == "21:00"

    def test_enabled_filter(self, client):
        self._create_rule(client, "Enabled Rule")
        client.post("/api/smarthome/automations", json={
            "name": "Disabled Rule", "enabled": False,
            "trigger": {"trigger_type": "manual"}, "actions": [],
        })
        r = client.get("/api/smarthome/automations?enabled_only=true")
        assert r.json()["total"] == 1


# ── Voice endpoint ────────────────────────────────────────────────────────────

class TestVoiceEndpoint:
    def test_voice_command_unknown(self, client):
        r = client.post("/api/smarthome/voice", json={
            "utterance": "play jazz music",
            "room": "kitchen",
        })
        assert r.status_code == 200
        data = r.json()
        assert "spoken_reply" in data

    def test_voice_command_turn_on(self, client):
        # Register a light first
        client.post("/api/smarthome/devices", json={
            "display_name": "K Light", "device_type": "light",
            "protocol": "ble", "room": "kitchen", "adapter_type": "mock",
        })
        r = client.post("/api/smarthome/voice", json={
            "utterance": "turn on the kitchen lights",
            "room": "kitchen",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["parsed"]["intent"] == "turn_on"
        assert len(data["device_ids"]) >= 1

    def test_voice_response_structure(self, client):
        r = client.post("/api/smarthome/voice", json={"utterance": "turn off lights"})
        data = r.json()
        for key in ("parsed", "device_ids", "results", "spoken_reply", "automation_fired"):
            assert key in data


# ── Scenes endpoints ──────────────────────────────────────────────────────────

class TestScenesEndpoints:
    def test_list_scenes_empty(self, client):
        r = client.get("/api/smarthome/scenes")
        assert r.status_code == 200
        assert r.json()["scenes"] == []

    def test_create_scene(self, client):
        r = client.post("/api/smarthome/scenes", json={
            "name": "goodnight",
            "actions": [{"action_type": "notify", "message": "Goodnight!"}],
        })
        assert r.status_code == 201
        assert r.json()["name"] == "goodnight"

    def test_list_scenes_after_create(self, client):
        client.post("/api/smarthome/scenes", json={"name": "morning", "actions": []})
        r = client.get("/api/smarthome/scenes")
        assert "morning" in r.json()["scenes"]

    def test_delete_scene(self, client):
        client.post("/api/smarthome/scenes", json={"name": "temp", "actions": []})
        r = client.delete("/api/smarthome/scenes/temp")
        assert r.status_code == 200

    def test_delete_scene_not_found(self, client):
        r = client.delete("/api/smarthome/scenes/ghost")
        assert r.status_code == 404
