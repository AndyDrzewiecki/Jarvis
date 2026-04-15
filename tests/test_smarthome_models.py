"""Tests for jarvis/smarthome/models.py"""
import pytest
from jarvis.smarthome.models import (
    DeviceType, Protocol, DeviceStatus,
    DeviceState, BaseDevice, CommandResult,
    TriggerType, ActionType,
    AutomationTrigger, AutomationAction, AutomationRule,
)


# ── DeviceState ───────────────────────────────────────────────────────────────

class TestDeviceState:
    def test_default_state(self):
        s = DeviceState()
        assert s.power is None
        assert s.brightness is None
        assert s.updated_at is not None

    def test_to_dict_excludes_none(self):
        s = DeviceState(power=True, brightness=80)
        d = s.to_dict()
        assert d["power"] is True
        assert d["brightness"] == 80
        assert "color_temp" not in d

    def test_to_dict_color_rgb(self):
        s = DeviceState(color_rgb=(255, 128, 0))
        d = s.to_dict()
        assert d["color_rgb"] == [255, 128, 0]

    def test_from_dict_roundtrip(self):
        s = DeviceState(power=False, brightness=50, color_temp=3000, volume=70)
        d = s.to_dict()
        s2 = DeviceState.from_dict(d)
        assert s2.power is False
        assert s2.brightness == 50
        assert s2.color_temp == 3000
        assert s2.volume == 70

    def test_from_dict_color_rgb_list_to_tuple(self):
        d = {"color_rgb": [255, 0, 128], "updated_at": "2026-01-01T00:00:00+00:00"}
        s = DeviceState.from_dict(d)
        assert s.color_rgb == (255, 0, 128)

    def test_from_dict_empty(self):
        s = DeviceState.from_dict({})
        assert s.power is None

    def test_extra_dict(self):
        s = DeviceState(extra={"muted": True})
        d = s.to_dict()
        assert d["extra"]["muted"] is True

    def test_lock_state(self):
        s = DeviceState(lock_state="locked")
        d = s.to_dict()
        assert d["lock_state"] == "locked"

    def test_motion_detected(self):
        s = DeviceState(motion_detected=True)
        assert s.to_dict()["motion_detected"] is True


# ── BaseDevice ────────────────────────────────────────────────────────────────

class TestBaseDevice:
    def _make_device(self):
        return BaseDevice.new(
            display_name="Kitchen Light",
            device_type=DeviceType.LIGHT,
            protocol=Protocol.BLE,
            room="kitchen",
            address="AA:BB:CC:DD:EE:FF",
            adapter_type="hubspace",
        )

    def test_new_generates_uuid(self):
        d1 = self._make_device()
        d2 = self._make_device()
        assert d1.device_id != d2.device_id

    def test_to_dict_keys(self):
        d = self._make_device()
        dd = d.to_dict()
        for key in ("device_id", "display_name", "device_type", "protocol",
                    "room", "address", "adapter_type", "status", "state",
                    "capabilities", "metadata", "registered_at"):
            assert key in dd

    def test_device_type_enum_serialises(self):
        d = self._make_device()
        assert d.to_dict()["device_type"] == "light"

    def test_from_dict_roundtrip(self):
        d = self._make_device()
        dd = d.to_dict()
        d2 = BaseDevice.from_dict(dd)
        assert d2.device_id == d.device_id
        assert d2.display_name == d.display_name
        assert d2.device_type == DeviceType.LIGHT
        assert d2.protocol == Protocol.BLE
        assert d2.room == "kitchen"

    def test_default_status_unknown(self):
        d = self._make_device()
        assert d.status == DeviceStatus.UNKNOWN

    def test_capabilities_list(self):
        d = BaseDevice.new(
            "Bulb", DeviceType.LIGHT, Protocol.BLE, "bedroom",
            capabilities=["power", "brightness"]
        )
        assert "brightness" in d.to_dict()["capabilities"]


# ── CommandResult ─────────────────────────────────────────────────────────────

class TestCommandResult:
    def test_success_result(self):
        r = CommandResult(success=True, device_id="abc", command="turn_on", message="OK")
        d = r.to_dict()
        assert d["success"] is True
        assert d["command"] == "turn_on"

    def test_failure_result(self):
        r = CommandResult(success=False, device_id="x", command="bad", message="unknown")
        assert r.to_dict()["success"] is False

    def test_result_with_new_state(self):
        state = DeviceState(power=True)
        r = CommandResult(success=True, device_id="d", command="turn_on", new_state=state)
        d = r.to_dict()
        assert "new_state" in d
        assert d["new_state"]["power"] is True

    def test_result_without_new_state(self):
        r = CommandResult(success=True, device_id="d", command="noop")
        assert "new_state" not in r.to_dict()


# ── AutomationTrigger ─────────────────────────────────────────────────────────

class TestAutomationTrigger:
    def test_time_trigger_to_dict(self):
        t = AutomationTrigger(trigger_type=TriggerType.TIME, time_str="21:00")
        d = t.to_dict()
        assert d["trigger_type"] == "time"
        assert d["time_str"] == "21:00"
        assert "cron" not in d

    def test_cron_trigger(self):
        t = AutomationTrigger(trigger_type=TriggerType.TIME, cron="0 21 * * *")
        d = t.to_dict()
        assert d["cron"] == "0 21 * * *"

    def test_sensor_trigger(self):
        t = AutomationTrigger(
            trigger_type=TriggerType.SENSOR,
            device_id="dev1",
            attribute="motion_detected",
            value=True,
        )
        d = t.to_dict()
        assert d["attribute"] == "motion_detected"
        assert d["value"] is True

    def test_voice_trigger(self):
        t = AutomationTrigger(trigger_type=TriggerType.VOICE, phrase="goodnight")
        d = t.to_dict()
        assert d["phrase"] == "goodnight"

    def test_from_dict_roundtrip(self):
        t = AutomationTrigger(trigger_type=TriggerType.TIME, cron="30 8 * * 1-5")
        t2 = AutomationTrigger.from_dict(t.to_dict())
        assert t2.trigger_type == TriggerType.TIME
        assert t2.cron == "30 8 * * 1-5"


# ── AutomationAction ──────────────────────────────────────────────────────────

class TestAutomationAction:
    def test_device_command_action(self):
        a = AutomationAction(
            action_type=ActionType.DEVICE_COMMAND,
            device_id="dev1",
            command="set_brightness",
            params={"value": 30},
        )
        d = a.to_dict()
        assert d["command"] == "set_brightness"
        assert d["params"]["value"] == 30

    def test_scene_action(self):
        a = AutomationAction(action_type=ActionType.SCENE, scene_name="goodnight")
        d = a.to_dict()
        assert d["scene_name"] == "goodnight"

    def test_delay_action(self):
        a = AutomationAction(action_type=ActionType.DELAY, delay_seconds=5.0)
        d = a.to_dict()
        assert d["delay_seconds"] == 5.0

    def test_notify_action(self):
        a = AutomationAction(action_type=ActionType.NOTIFY, message="Goodnight!")
        d = a.to_dict()
        assert d["message"] == "Goodnight!"

    def test_from_dict_roundtrip(self):
        a = AutomationAction(
            action_type=ActionType.DEVICE_COMMAND,
            device_id="d1",
            command="turn_off",
        )
        a2 = AutomationAction.from_dict(a.to_dict())
        assert a2.action_type == ActionType.DEVICE_COMMAND
        assert a2.device_id == "d1"


# ── AutomationRule ────────────────────────────────────────────────────────────

class TestAutomationRule:
    def _make_rule(self):
        return AutomationRule.new(
            name="Dim at 9pm",
            trigger=AutomationTrigger(trigger_type=TriggerType.TIME, time_str="21:00"),
            actions=[
                AutomationAction(
                    action_type=ActionType.DEVICE_COMMAND,
                    device_id="light1",
                    command="set_brightness",
                    params={"value": 30},
                )
            ],
            description="Dim lights at 9 PM",
        )

    def test_new_generates_uuid(self):
        r1 = self._make_rule()
        r2 = self._make_rule()
        assert r1.rule_id != r2.rule_id

    def test_to_dict(self):
        r = self._make_rule()
        d = r.to_dict()
        assert d["name"] == "Dim at 9pm"
        assert d["enabled"] is True
        assert len(d["actions"]) == 1
        assert d["trigger"]["time_str"] == "21:00"

    def test_from_dict_roundtrip(self):
        r = self._make_rule()
        d = r.to_dict()
        r2 = AutomationRule.from_dict(d)
        assert r2.rule_id == r.rule_id
        assert r2.name == r.name
        assert r2.trigger.time_str == "21:00"
        assert len(r2.actions) == 1

    def test_enabled_default_true(self):
        r = self._make_rule()
        assert r.enabled is True

    def test_disabled_rule(self):
        r = AutomationRule.new(
            name="Off",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[],
            enabled=False,
        )
        assert r.enabled is False
