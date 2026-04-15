"""Tests for jarvis/smarthome/voice_handler.py"""
import pytest
from jarvis.smarthome.voice_handler import VoiceHandler, ParsedCommand
from jarvis.smarthome.models import (
    BaseDevice, DeviceType, Protocol,
    AutomationRule, AutomationTrigger, AutomationAction,
    TriggerType, ActionType,
)
from jarvis.smarthome.registry import DeviceRegistry
from jarvis.smarthome.automation import AutomationEngine
from jarvis.smarthome.adapters.base import MockAdapter


@pytest.fixture
def registry(tmp_path):
    return DeviceRegistry(db_path=str(tmp_path / "voice_test.db"))


@pytest.fixture
def engine(tmp_path, registry):
    return AutomationEngine(
        registry=registry,
        adapter_registry={"mock": MockAdapter()},
        db_path=str(tmp_path / "auto_test.db"),
    )


@pytest.fixture
def handler(registry, engine):
    return VoiceHandler(
        registry=registry,
        automation_engine=engine,
        adapter_registry={"mock": MockAdapter()},
    )


def _add_light(registry, room="kitchen"):
    dev = BaseDevice.new(
        f"{room.title()} Light", DeviceType.LIGHT, Protocol.BLE, room,
        adapter_type="mock",
    )
    registry.register(dev)
    return dev


# ── Parser unit tests ─────────────────────────────────────────────────────────

class TestVoiceParser:
    def setup_method(self):
        self.h = VoiceHandler()

    def test_turn_on(self):
        p = self.h.parse("turn on the kitchen lights")
        assert p.intent == "turn_on"

    def test_turn_off(self):
        p = self.h.parse("turn off the living room lights")
        assert p.intent == "turn_off"

    def test_switch_on(self):
        p = self.h.parse("switch on the lamp")
        assert p.intent == "turn_on"

    def test_power_off(self):
        p = self.h.parse("power off the TV")
        assert p.intent == "turn_off"

    def test_dim_with_percentage(self):
        p = self.h.parse("dim the bedroom lights to 20%")
        assert p.intent == "set_brightness"
        assert p.params["value"] == 20

    def test_set_brightness(self):
        p = self.h.parse("set brightness to 80")
        assert p.intent == "set_brightness"
        assert p.params["value"] == 80

    def test_dim_no_percentage(self):
        p = self.h.parse("dim the lights")
        assert p.intent == "set_brightness"
        assert p.params["value"] == 30

    def test_warm_light(self):
        p = self.h.parse("set warm light")
        assert p.intent == "set_color_temp"
        assert p.params["value"] == 2700

    def test_cool_light(self):
        p = self.h.parse("set daylight mode")
        assert p.intent == "set_color_temp"
        assert p.params["value"] == 5000

    def test_thermostat(self):
        p = self.h.parse("set thermostat to 72")
        assert p.intent == "set_temperature"
        assert p.params["value"] == 72.0

    def test_set_temp_degrees(self):
        p = self.h.parse("set temperature to 68")
        assert p.intent == "set_temperature"
        assert p.params["value"] == 68.0

    def test_volume(self):
        p = self.h.parse("set volume to 30")
        assert p.intent == "set_volume"
        assert p.params["value"] == 30

    def test_volume_up(self):
        p = self.h.parse("volume up")
        assert p.intent == "volume_up"

    def test_volume_down(self):
        p = self.h.parse("turn down the volume")
        assert p.intent == "volume_down"

    def test_slow_cook(self):
        p = self.h.parse("set the instant pot to slow cook")
        assert p.intent == "set_mode"
        assert "slow" in p.params["value"]

    def test_status_query(self):
        p = self.h.parse("what is the temperature")
        assert p.intent == "get_state"

    def test_unknown_utterance(self):
        p = self.h.parse("play my favorite song")
        assert p is None

    def test_room_extraction_kitchen(self):
        p = self.h.parse("turn on the kitchen lights")
        assert "kitchen" in p.target

    def test_room_extraction_bedroom(self):
        p = self.h.parse("dim bedroom lights to 50%")
        assert "bedroom" in p.target

    def test_device_type_tv(self):
        p = self.h.parse("turn off the TV")
        assert "tv" in p.target

    def test_device_type_light(self):
        p = self.h.parse("turn on the lights")
        assert "light" in p.target

    def test_brightness_clamped_high(self):
        p = self.h.parse("set brightness to 150")
        # Parser captures 150, clamping happens in adapter
        assert p.params["value"] == 100  # clamped to 100

    def test_room_context_fallback(self):
        p = self.h.parse("turn on the lights", room="bedroom")
        assert "bedroom" in p.target


# ── Full process() integration tests ─────────────────────────────────────────

class TestVoiceProcess:
    def test_process_turn_on_kitchen_light(self, handler, registry):
        _add_light(registry, "kitchen")
        resp = handler.process("turn on the kitchen lights", room="kitchen")
        assert resp.parsed.intent == "turn_on"
        assert len(resp.device_ids) >= 1
        assert "Turned on" in resp.spoken_reply

    def test_process_turn_off_no_room_uses_context(self, handler, registry):
        _add_light(registry, "bedroom")
        resp = handler.process("turn off the lights", room="bedroom")
        assert resp.parsed.intent == "turn_off"

    def test_process_unknown_utterance(self, handler):
        resp = handler.process("sing me a lullaby")
        assert "didn't understand" in resp.spoken_reply.lower()

    def test_process_no_matching_device(self, handler):
        resp = handler.process("turn on the garage lights", room="office")
        assert "couldn't find" in resp.spoken_reply.lower() or len(resp.device_ids) == 0

    def test_process_automation_voice_trigger(self, handler, engine, registry):
        dev = _add_light(registry, "bedroom")
        rule = AutomationRule.new(
            name="Goodnight routine",
            trigger=AutomationTrigger(trigger_type=TriggerType.VOICE, phrase="goodnight"),
            actions=[AutomationAction(
                action_type=ActionType.DEVICE_COMMAND,
                device_id=dev.device_id,
                command="turn_off",
            )],
        )
        engine.create_rule(rule)
        resp = handler.process("goodnight jarvis")
        assert resp.automation_fired is True

    def test_reply_set_brightness(self, handler, registry):
        _add_light(registry, "living room")
        resp = handler.process("dim the living room lights to 40%", room="living room")
        assert "40%" in resp.spoken_reply

    def test_reply_set_temperature(self, handler, registry):
        thermo = BaseDevice.new(
            "Thermostat", DeviceType.THERMOSTAT, Protocol.BLE, "hallway",
            adapter_type="mock"
        )
        registry.register(thermo)
        resp = handler.process("set thermostat to 72", room="hallway")
        assert "72" in resp.spoken_reply

    def test_process_without_registry(self):
        h = VoiceHandler()  # no registry
        resp = h.process("turn on the lights")
        assert resp.device_ids == []


# ── ParsedCommand serialisation ───────────────────────────────────────────────

class TestParsedCommandDict:
    def test_to_dict(self):
        p = ParsedCommand(intent="turn_on", target="kitchen/light", params={}, raw_utterance="turn on lights")
        d = p.to_dict()
        assert d["intent"] == "turn_on"
        assert d["target"] == "kitchen/light"
        assert "raw_utterance" in d

    def test_confidence_field(self):
        p = ParsedCommand(intent="get_state", target="all", confidence=0.8)
        assert p.to_dict()["confidence"] == 0.8
