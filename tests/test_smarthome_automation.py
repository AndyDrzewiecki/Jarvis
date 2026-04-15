"""Tests for jarvis/smarthome/automation.py"""
import os
from datetime import datetime, timezone
import pytest

from jarvis.smarthome.models import (
    AutomationRule, AutomationTrigger, AutomationAction,
    TriggerType, ActionType, BaseDevice, DeviceType, Protocol,
)
from jarvis.smarthome.automation import AutomationEngine, _cron_matches, _field_matches
from jarvis.smarthome.registry import DeviceRegistry
from jarvis.smarthome.adapters.base import MockAdapter


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "automation_test.db")


@pytest.fixture
def registry(tmp_path):
    return DeviceRegistry(db_path=str(tmp_path / "devices.db"))


@pytest.fixture
def engine(db_path, registry):
    adapters = {"mock": MockAdapter()}
    return AutomationEngine(registry=registry, adapter_registry=adapters, db_path=db_path)


def _light_device(registry):
    dev = BaseDevice.new("Kitchen Light", DeviceType.LIGHT, Protocol.BLE, "kitchen", adapter_type="mock")
    registry.register(dev)
    return dev


def _time_rule(time_str="21:00", device_id="light1", command="set_brightness", value=30):
    return AutomationRule.new(
        name="Dim at 9pm",
        trigger=AutomationTrigger(trigger_type=TriggerType.TIME, time_str=time_str),
        actions=[
            AutomationAction(
                action_type=ActionType.DEVICE_COMMAND,
                device_id=device_id,
                command=command,
                params={"value": value},
            )
        ],
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

class TestAutomationCRUD:
    def test_create_and_get(self, engine):
        rule = _time_rule()
        engine.create_rule(rule)
        retrieved = engine.get_rule(rule.rule_id)
        assert retrieved is not None
        assert retrieved.name == "Dim at 9pm"

    def test_get_nonexistent(self, engine):
        assert engine.get_rule("ghost") is None

    def test_list_rules_empty(self, engine):
        assert engine.list_rules() == []

    def test_list_rules(self, engine):
        engine.create_rule(_time_rule())
        engine.create_rule(AutomationRule.new(
            name="Morning",
            trigger=AutomationTrigger(trigger_type=TriggerType.TIME, time_str="07:00"),
            actions=[],
        ))
        rules = engine.list_rules()
        assert len(rules) == 2

    def test_list_enabled_only(self, engine):
        r1 = _time_rule()
        r2 = AutomationRule.new(
            name="Disabled",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[],
            enabled=False,
        )
        engine.create_rule(r1)
        engine.create_rule(r2)
        enabled = engine.list_rules(enabled_only=True)
        assert len(enabled) == 1
        assert enabled[0].name == "Dim at 9pm"

    def test_update_rule(self, engine):
        rule = _time_rule()
        engine.create_rule(rule)
        rule.name = "Updated Name"
        engine.update_rule(rule)
        retrieved = engine.get_rule(rule.rule_id)
        assert retrieved.name == "Updated Name"

    def test_delete_rule(self, engine):
        rule = _time_rule()
        engine.create_rule(rule)
        result = engine.delete_rule(rule.rule_id)
        assert result is True
        assert engine.get_rule(rule.rule_id) is None

    def test_delete_nonexistent(self, engine):
        assert engine.delete_rule("ghost") is False

    def test_enable_disable_rule(self, engine):
        rule = _time_rule()
        engine.create_rule(rule)
        engine.enable_rule(rule.rule_id, False)
        assert engine.list_rules(enabled_only=True) == []
        engine.enable_rule(rule.rule_id, True)
        assert len(engine.list_rules(enabled_only=True)) == 1


# ── Time tick ─────────────────────────────────────────────────────────────────

class TestTimeTick:
    def test_tick_fires_matching_rule(self, engine, registry):
        dev = _light_device(registry)
        rule = _time_rule("21:00", dev.device_id, "turn_off")
        engine.create_rule(rule)
        now = datetime(2026, 4, 15, 21, 0, tzinfo=timezone.utc)
        fired = engine.tick(now)
        assert len(fired) == 1
        assert fired[0][0].name == "Dim at 9pm"

    def test_tick_does_not_fire_wrong_time(self, engine):
        rule = _time_rule("21:00")
        engine.create_rule(rule)
        now = datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
        fired = engine.tick(now)
        assert fired == []

    def test_tick_disabled_rule_skipped(self, engine):
        rule = AutomationRule.new(
            name="Disabled",
            trigger=AutomationTrigger(trigger_type=TriggerType.TIME, time_str="21:00"),
            actions=[],
            enabled=False,
        )
        engine.create_rule(rule)
        now = datetime(2026, 4, 15, 21, 0, tzinfo=timezone.utc)
        assert engine.tick(now) == []

    def test_tick_cron_rule(self, engine, registry):
        dev = _light_device(registry)
        rule = AutomationRule.new(
            name="9pm daily",
            trigger=AutomationTrigger(trigger_type=TriggerType.TIME, cron="0 21 * * *"),
            actions=[AutomationAction(
                action_type=ActionType.DEVICE_COMMAND,
                device_id=dev.device_id,
                command="turn_off",
            )],
        )
        engine.create_rule(rule)
        now = datetime(2026, 4, 15, 21, 0, tzinfo=timezone.utc)
        fired = engine.tick(now)
        assert len(fired) == 1


# ── Sensor triggers ───────────────────────────────────────────────────────────

class TestSensorTrigger:
    def test_sensor_trigger_fires(self, engine, registry):
        dev = _light_device(registry)
        sensor_rule = AutomationRule.new(
            name="Light on motion",
            trigger=AutomationTrigger(
                trigger_type=TriggerType.SENSOR,
                device_id="sensor1",
                attribute="motion_detected",
                value=True,
            ),
            actions=[AutomationAction(
                action_type=ActionType.DEVICE_COMMAND,
                device_id=dev.device_id,
                command="turn_on",
            )],
        )
        engine.create_rule(sensor_rule)
        fired = engine.check_sensor_triggers("sensor1", "motion_detected", True)
        assert len(fired) == 1

    def test_sensor_trigger_wrong_value(self, engine):
        rule = AutomationRule.new(
            name="Motion rule",
            trigger=AutomationTrigger(
                trigger_type=TriggerType.SENSOR,
                device_id="s1",
                attribute="motion_detected",
                value=True,
            ),
            actions=[],
        )
        engine.create_rule(rule)
        fired = engine.check_sensor_triggers("s1", "motion_detected", False)
        assert fired == []

    def test_sensor_trigger_wrong_device(self, engine):
        rule = AutomationRule.new(
            name="Motion rule",
            trigger=AutomationTrigger(
                trigger_type=TriggerType.SENSOR,
                device_id="sensor1",
                attribute="motion_detected",
                value=True,
            ),
            actions=[],
        )
        engine.create_rule(rule)
        fired = engine.check_sensor_triggers("different_sensor", "motion_detected", True)
        assert fired == []


# ── Voice triggers ────────────────────────────────────────────────────────────

class TestVoiceTrigger:
    def test_voice_trigger_exact(self, engine):
        rule = AutomationRule.new(
            name="Goodnight routine",
            trigger=AutomationTrigger(trigger_type=TriggerType.VOICE, phrase="goodnight"),
            actions=[AutomationAction(action_type=ActionType.NOTIFY, message="Goodnight!")],
        )
        engine.create_rule(rule)
        fired = engine.trigger_by_voice("goodnight")
        assert len(fired) == 1

    def test_voice_trigger_substring(self, engine):
        rule = AutomationRule.new(
            name="Goodnight",
            trigger=AutomationTrigger(trigger_type=TriggerType.VOICE, phrase="goodnight"),
            actions=[],
        )
        engine.create_rule(rule)
        fired = engine.trigger_by_voice("hey jarvis, goodnight everyone")
        assert len(fired) == 1

    def test_voice_trigger_no_match(self, engine):
        rule = AutomationRule.new(
            name="Goodnight",
            trigger=AutomationTrigger(trigger_type=TriggerType.VOICE, phrase="goodnight"),
            actions=[],
        )
        engine.create_rule(rule)
        assert engine.trigger_by_voice("good morning") == []


# ── Manual trigger ────────────────────────────────────────────────────────────

class TestManualTrigger:
    def test_manual_trigger(self, engine):
        rule = AutomationRule.new(
            name="Manual",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[AutomationAction(action_type=ActionType.NOTIFY, message="OK")],
        )
        engine.create_rule(rule)
        results = engine.trigger_manual(rule.rule_id)
        assert results is not None
        assert len(results) == 1

    def test_manual_trigger_nonexistent(self, engine):
        assert engine.trigger_manual("ghost") is None


# ── Rule execution ────────────────────────────────────────────────────────────

class TestRuleExecution:
    def test_run_count_incremented(self, engine):
        rule = AutomationRule.new(
            name="Counter",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[AutomationAction(action_type=ActionType.NOTIFY, message="ping")],
        )
        engine.create_rule(rule)
        engine.execute_rule(rule)
        engine.execute_rule(rule)
        retrieved = engine.get_rule(rule.rule_id)
        assert retrieved.run_count == 2

    def test_last_triggered_set(self, engine):
        rule = AutomationRule.new(
            name="Timed",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[],
        )
        engine.create_rule(rule)
        engine.execute_rule(rule)
        retrieved = engine.get_rule(rule.rule_id)
        assert retrieved.last_triggered is not None

    def test_post_hook_called(self, engine):
        calls = []
        engine.add_post_hook(lambda rule, results: calls.append(rule.name))
        rule = AutomationRule.new(
            name="Hook Test",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[],
        )
        engine.create_rule(rule)
        engine.execute_rule(rule)
        assert "Hook Test" in calls

    def test_device_command_dispatched(self, engine, registry):
        dev = _light_device(registry)
        rule = AutomationRule.new(
            name="Turn on kitchen",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[AutomationAction(
                action_type=ActionType.DEVICE_COMMAND,
                device_id=dev.device_id,
                command="turn_on",
            )],
        )
        engine.create_rule(rule)
        results = engine.execute_rule(rule)
        assert results[0].success is True

    def test_scene_execution(self, engine, registry):
        dev = _light_device(registry)
        registry.save_scene("goodnight", [
            {"action_type": "device_command", "device_id": dev.device_id, "command": "turn_off"}
        ])
        rule = AutomationRule.new(
            name="Goodnight scene",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[AutomationAction(action_type=ActionType.SCENE, scene_name="goodnight")],
        )
        engine.create_rule(rule)
        results = engine.execute_rule(rule)
        assert len(results) == 1

    def test_recent_log(self, engine):
        rule = AutomationRule.new(
            name="Log test",
            trigger=AutomationTrigger(trigger_type=TriggerType.MANUAL),
            actions=[],
        )
        engine.create_rule(rule)
        engine.execute_rule(rule)
        log = engine.recent_log(limit=10)
        assert len(log) >= 1
        assert log[0]["rule_name"] == "Log test"


# ── Cron helper ───────────────────────────────────────────────────────────────

class TestCronMatcher:
    def test_match_every_minute(self):
        now = datetime(2026, 4, 15, 9, 0, tzinfo=timezone.utc)
        assert _cron_matches("* * * * *", now) is True

    def test_match_specific_time(self):
        now = datetime(2026, 4, 15, 21, 0, tzinfo=timezone.utc)
        assert _cron_matches("0 21 * * *", now) is True

    def test_no_match_wrong_hour(self):
        now = datetime(2026, 4, 15, 22, 0, tzinfo=timezone.utc)
        assert _cron_matches("0 21 * * *", now) is False

    def test_comma_separated(self):
        now = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
        assert _cron_matches("0 8,20 * * *", now) is True

    def test_range(self):
        now = datetime(2026, 4, 15, 10, 0, tzinfo=timezone.utc)
        assert _cron_matches("0 9-11 * * *", now) is True

    def test_invalid_cron(self):
        now = datetime(2026, 4, 15, 9, 0, tzinfo=timezone.utc)
        assert _cron_matches("not a cron", now) is False

    def test_field_matches_wildcard(self):
        assert _field_matches("*", 5) is True

    def test_field_matches_exact(self):
        assert _field_matches("5", 5) is True
        assert _field_matches("5", 6) is False

    def test_field_matches_range(self):
        assert _field_matches("1-5", 3) is True
        assert _field_matches("1-5", 6) is False
