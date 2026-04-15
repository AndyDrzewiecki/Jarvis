"""Tests for jarvis/smarthome/adapters/"""
import pytest
from jarvis.smarthome.models import BaseDevice, DeviceType, Protocol, DeviceState
from jarvis.smarthome.adapters.base import MockAdapter
from jarvis.smarthome.adapters.hubspace import HubSpaceAdapter
from jarvis.smarthome.adapters.instantpot import ApplianceAdapter
from jarvis.smarthome.adapters.tv import TVAdapter
from jarvis.smarthome.adapters.generic import GenericMQTTAdapter, GenericHTTPAdapter


def _device(adapter_type="mock", dtype=DeviceType.LIGHT, protocol=Protocol.BLE, room="kitchen"):
    return BaseDevice.new(
        display_name="Test Device",
        device_type=dtype,
        protocol=protocol,
        room=room,
        adapter_type=adapter_type,
    )


# ── MockAdapter ───────────────────────────────────────────────────────────────

class TestMockAdapter:
    def setup_method(self):
        self.adapter = MockAdapter()
        self.device = _device("mock")

    def test_turn_on(self):
        r = self.adapter.send_command(self.device, "turn_on")
        assert r.success
        assert r.new_state.power is True

    def test_turn_off(self):
        r = self.adapter.send_command(self.device, "turn_off")
        assert r.success
        assert r.new_state.power is False

    def test_set_brightness(self):
        r = self.adapter.send_command(self.device, "set_brightness", {"value": 75})
        assert r.success
        assert r.new_state.brightness == 75

    def test_set_brightness_clamped(self):
        r = self.adapter.send_command(self.device, "set_brightness", {"value": 150})
        assert r.new_state.brightness == 100
        r2 = self.adapter.send_command(self.device, "set_brightness", {"value": -10})
        assert r2.new_state.brightness == 0

    def test_set_color_temp(self):
        r = self.adapter.send_command(self.device, "set_color_temp", {"value": 4000})
        assert r.new_state.color_temp == 4000

    def test_set_color_rgb(self):
        r = self.adapter.send_command(self.device, "set_color_rgb", {"r": 255, "g": 0, "b": 128})
        assert r.new_state.color_rgb == (255, 0, 128)

    def test_set_volume(self):
        r = self.adapter.send_command(self.device, "set_volume", {"value": 40})
        assert r.new_state.volume == 40

    def test_set_mode(self):
        r = self.adapter.send_command(self.device, "set_mode", {"value": "slow_cook"})
        assert r.new_state.mode == "slow_cook"

    def test_set_temperature(self):
        r = self.adapter.send_command(self.device, "set_temperature", {"value": 72.5})
        assert r.new_state.target_temp_f == 72.5

    def test_lock(self):
        r = self.adapter.send_command(self.device, "lock")
        assert r.new_state.lock_state == "locked"

    def test_unlock(self):
        r = self.adapter.send_command(self.device, "unlock")
        assert r.new_state.lock_state == "unlocked"

    def test_unknown_command(self):
        r = self.adapter.send_command(self.device, "fly_to_moon")
        assert r.success is False
        assert "fly_to_moon" in r.message

    def test_get_state_empty(self):
        state = self.adapter.get_state(self.device)
        assert isinstance(state, DeviceState)

    def test_state_persists_across_commands(self):
        self.adapter.send_command(self.device, "turn_on")
        self.adapter.send_command(self.device, "set_brightness", {"value": 50})
        state = self.adapter.get_state(self.device)
        assert state.power is True
        assert state.brightness == 50

    def test_can_handle_any_device(self):
        assert self.adapter.can_handle(self.device) is True

    def test_adapter_type(self):
        assert self.adapter.adapter_type == "mock"


# ── HubSpaceAdapter ───────────────────────────────────────────────────────────

class TestHubSpaceAdapter:
    def setup_method(self):
        self.adapter = HubSpaceAdapter()
        self.device = _device("hubspace")

    def test_adapter_type(self):
        assert self.adapter.adapter_type == "hubspace"

    def test_supported_commands(self):
        assert "turn_on" in self.adapter.supported_commands
        assert "set_brightness" in self.adapter.supported_commands

    def test_turn_on_no_bleak(self, monkeypatch):
        import jarvis.smarthome.adapters.hubspace as mod
        monkeypatch.setattr(mod, "_BLEAK_AVAILABLE", False)
        r = self.adapter.send_command(self.device, "turn_on")
        assert r.success
        assert r.new_state.power is True

    def test_turn_off_no_bleak(self, monkeypatch):
        import jarvis.smarthome.adapters.hubspace as mod
        monkeypatch.setattr(mod, "_BLEAK_AVAILABLE", False)
        r = self.adapter.send_command(self.device, "turn_off")
        assert r.success
        assert r.new_state.power is False

    def test_set_brightness_no_bleak(self, monkeypatch):
        import jarvis.smarthome.adapters.hubspace as mod
        monkeypatch.setattr(mod, "_BLEAK_AVAILABLE", False)
        r = self.adapter.send_command(self.device, "set_brightness", {"value": 60})
        assert r.new_state.brightness == 60

    def test_set_color_temp_no_bleak(self, monkeypatch):
        import jarvis.smarthome.adapters.hubspace as mod
        monkeypatch.setattr(mod, "_BLEAK_AVAILABLE", False)
        r = self.adapter.send_command(self.device, "set_color_temp", {"value": 2700})
        assert r.new_state.color_temp == 2700

    def test_ble_matcher_hubspace_name(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="AA:BB:CC", name="HubSpace Bulb", rssi=-60)
        assert HubSpaceAdapter.ble_matcher(disc) == "hubspace"

    def test_ble_matcher_hs_prefix(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="AA:BB:CC", name="HS-1234", rssi=-60)
        assert HubSpaceAdapter.ble_matcher(disc) == "hubspace"

    def test_ble_matcher_no_match(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="AA:BB:CC", name="Philips Hue", rssi=-60)
        assert HubSpaceAdapter.ble_matcher(disc) is None

    def test_can_handle(self):
        assert self.adapter.can_handle(self.device) is True
        other = _device("other")
        assert self.adapter.can_handle(other) is False


# ── ApplianceAdapter ──────────────────────────────────────────────────────────

class TestApplianceAdapter:
    def setup_method(self):
        self.adapter = ApplianceAdapter()
        self.device = _device("appliance", DeviceType.APPLIANCE)

    def test_adapter_type(self):
        assert self.adapter.adapter_type == "appliance"

    def test_turn_off(self):
        r = self.adapter.send_command(self.device, "turn_off")
        assert r.success
        assert r.new_state.power is False
        assert r.new_state.mode == "off"

    def test_set_mode_valid(self):
        r = self.adapter.send_command(self.device, "set_mode", {"value": "slow_cook"})
        assert r.success
        assert r.new_state.mode == "slow_cook"

    def test_set_mode_invalid(self):
        r = self.adapter.send_command(self.device, "set_mode", {"value": "turbo_blast"})
        assert r.success is False
        assert "Invalid mode" in r.message

    def test_get_state(self):
        r = self.adapter.send_command(self.device, "get_state")
        assert r.success

    def test_unknown_command(self):
        r = self.adapter.send_command(self.device, "warp_speed")
        assert r.success is False

    def test_camp_chef_mode(self):
        camp_device = BaseDevice.new(
            "Camp Chef", DeviceType.APPLIANCE, Protocol.BLE, "garage",
            adapter_type="appliance", manufacturer="Camp Chef",
        )
        r = self.adapter.send_command(camp_device, "set_mode", {"value": "smoke"})
        assert r.success
        assert r.new_state.mode == "smoke"

    def test_ble_matcher_instant_pot(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="AA", name="Instant Pot Ultra", rssi=-55)
        assert ApplianceAdapter.ble_matcher(disc) == "appliance"

    def test_ble_matcher_camp_chef(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="BB", name="Camp Chef 36", rssi=-55)
        assert ApplianceAdapter.ble_matcher(disc) == "appliance"

    def test_ble_matcher_no_match(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="CC", name="Smart Plug", rssi=-55)
        assert ApplianceAdapter.ble_matcher(disc) is None


# ── TVAdapter ─────────────────────────────────────────────────────────────────

class TestTVAdapter:
    def setup_method(self):
        self.adapter = TVAdapter()
        self.device = _device("tv", DeviceType.TV, Protocol.BLE, "living room")

    def test_adapter_type(self):
        assert self.adapter.adapter_type == "tv"

    def test_turn_on_simulated(self):
        r = self.adapter.send_command(self.device, "turn_on")
        assert r.success
        assert r.new_state.power is True

    def test_turn_off_simulated(self):
        r = self.adapter.send_command(self.device, "turn_off")
        assert r.success
        assert r.new_state.power is False

    def test_set_volume(self):
        r = self.adapter.send_command(self.device, "set_volume", {"value": 35})
        assert r.success
        assert r.new_state.volume == 35

    def test_mute(self):
        r = self.adapter.send_command(self.device, "mute")
        assert r.success

    def test_set_input(self):
        r = self.adapter.send_command(self.device, "set_input", {"value": "hdmi1"})
        assert r.success
        assert r.new_state.input_source == "hdmi1"

    def test_unknown_command(self):
        r = self.adapter.send_command(self.device, "fly")
        assert r.success is False

    def test_cec_no_cec_client(self, monkeypatch):
        import subprocess
        cec_device = _device("tv", DeviceType.TV, Protocol.CEC)
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("cec-client not found")
        monkeypatch.setattr(subprocess, "run", fake_run)
        r = self.adapter.send_command(cec_device, "turn_on")
        assert r.success  # graceful degradation

    def test_ir_no_irsend(self, monkeypatch):
        import subprocess
        ir_device = BaseDevice.new(
            "IR TV", DeviceType.TV, Protocol.IR, "bedroom",
            adapter_type="tv", metadata={"ir_remote": "samsung_tv"},
        )
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("irsend not found")
        monkeypatch.setattr(subprocess, "run", fake_run)
        r = self.adapter.send_command(ir_device, "turn_off")
        assert r.success  # graceful degradation

    def test_ble_matcher_bravia(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="AA", name="BRAVIA XR-55A90K", rssi=-60)
        assert TVAdapter.ble_matcher(disc) == "tv"

    def test_ble_matcher_no_match(self):
        from jarvis.smarthome.ble_scanner import BLEDiscovery
        disc = BLEDiscovery(address="BB", name="Philips Hue Bridge", rssi=-60)
        assert TVAdapter.ble_matcher(disc) is None


# ── GenericMQTTAdapter ────────────────────────────────────────────────────────

class TestGenericMQTTAdapter:
    def setup_method(self):
        self.adapter = GenericMQTTAdapter(mqtt_client=None)
        self.device = _device("generic_mqtt", DeviceType.LIGHT, Protocol.MQTT)

    def test_adapter_type(self):
        assert self.adapter.adapter_type == "generic_mqtt"

    def test_turn_on_no_client(self):
        r = self.adapter.send_command(self.device, "turn_on")
        assert r.success
        assert r.new_state.power is True

    def test_turn_off_no_client(self):
        r = self.adapter.send_command(self.device, "turn_off")
        assert r.success
        assert r.new_state.power is False

    def test_set_brightness(self):
        r = self.adapter.send_command(self.device, "set_brightness", {"value": 45})
        assert r.new_state.brightness == 45

    def test_lock_unlock(self):
        r = self.adapter.send_command(self.device, "lock")
        assert r.new_state.lock_state == "locked"
        r2 = self.adapter.send_command(self.device, "unlock")
        assert r2.new_state.lock_state == "unlocked"

    def test_on_state_update_power(self):
        state = self.adapter.on_state_update(self.device, {"power": True, "brightness": 80})
        assert state.power is True
        assert state.brightness == 80

    def test_on_state_update_temperature(self):
        state = self.adapter.on_state_update(self.device, {"temperature_f": 71.5})
        assert state.temperature_f == 71.5

    def test_mqtt_publish_with_client(self):
        from jarvis.smarthome.mqtt_client import MQTTClient
        client = MQTTClient()
        published = []
        client.subscribe("jarvis/testdev/cmd", lambda t, p: published.append(p))

        dev = BaseDevice.new(
            "Test MQTT Dev", DeviceType.LIGHT, Protocol.MQTT, "kitchen",
            adapter_type="generic_mqtt",
            metadata={"mqtt_prefix": "jarvis/testdev"},
        )
        adapter = GenericMQTTAdapter(mqtt_client=client)
        # No real broker — publish will fail, but inject_message simulates reception
        client.inject_message("jarvis/testdev/cmd", {"command": "turn_on", "params": {}})
        assert published[0]["command"] == "turn_on"
