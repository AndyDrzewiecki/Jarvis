"""
Automation Engine — evaluates and executes smart home rules.

Supports:
  TIME triggers  — cron expression or "HH:MM" shorthand
  SENSOR triggers — fire when a device attribute matches a value
  VOICE triggers  — registered phrase shortcuts
  MANUAL triggers — API-only, always executable on demand

Rule storage uses SQLite (same DB as device registry).

Usage:
    engine = AutomationEngine(registry, adapter_registry)
    engine.create_rule(rule)
    engine.tick()               # call from scheduler every minute
    engine.trigger_by_voice("goodnight")
    engine.trigger_manual(rule_id)
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator, Optional

from jarvis.smarthome.models import (
    ActionType,
    AutomationAction,
    AutomationRule,
    AutomationTrigger,
    CommandResult,
    TriggerType,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "..", "data", "smarthome.db")

_CREATE_RULES = """
CREATE TABLE IF NOT EXISTS automation_rules (
    rule_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    description TEXT NOT NULL DEFAULT '',
    trigger_json TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    run_count   INTEGER NOT NULL DEFAULT 0,
    last_triggered TEXT,
    created_at  TEXT NOT NULL
)
"""

_CREATE_RULE_LOG = """
CREATE TABLE IF NOT EXISTS automation_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     TEXT NOT NULL,
    rule_name   TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    results_json TEXT NOT NULL,
    executed_at TEXT NOT NULL
)
"""


@contextmanager
def _conn(path: str) -> Iterator[sqlite3.Connection]:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


class AutomationEngine:
    """
    Evaluates automation rules and dispatches device commands.

    Parameters
    ----------
    registry:
        DeviceRegistry instance for looking up devices and updating state.
    adapter_registry:
        AdapterRegistry (or any dict-like {adapter_type: adapter}) for
        dispatching commands to the right adapter.
    db_path:
        SQLite path; defaults to JARVIS_SMARTHOME_DB or data/smarthome.db
    """

    def __init__(
        self,
        registry: Any = None,
        adapter_registry: Optional[dict[str, Any]] = None,
        db_path: Optional[str] = None,
    ) -> None:
        self._registry = registry
        self._adapters: dict[str, Any] = adapter_registry or {}
        self._db = db_path or os.environ.get("JARVIS_SMARTHOME_DB", _DEFAULT_DB)
        self._init_db()
        # Callbacks for after-execution hooks (e.g. blackboard posts)
        self._post_hooks: list[Callable[[AutomationRule, list[CommandResult]], None]] = []

    def _init_db(self) -> None:
        with _conn(self._db) as con:
            con.execute(_CREATE_RULES)
            con.execute(_CREATE_RULE_LOG)

    # ── Rule CRUD ─────────────────────────────────────────────────────────────

    def create_rule(self, rule: AutomationRule) -> AutomationRule:
        with _conn(self._db) as con:
            con.execute(
                """INSERT OR REPLACE INTO automation_rules
                   (rule_id, name, enabled, description,
                    trigger_json, actions_json, run_count, last_triggered, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    rule.rule_id,
                    rule.name,
                    int(rule.enabled),
                    rule.description,
                    json.dumps(rule.trigger.to_dict()),
                    json.dumps([a.to_dict() for a in rule.actions]),
                    rule.run_count,
                    rule.last_triggered,
                    rule.created_at,
                ),
            )
        return rule

    def get_rule(self, rule_id: str) -> Optional[AutomationRule]:
        with _conn(self._db) as con:
            row = con.execute(
                "SELECT * FROM automation_rules WHERE rule_id = ?", (rule_id,)
            ).fetchone()
        return self._row_to_rule(row) if row else None

    def list_rules(self, enabled_only: bool = False) -> list[AutomationRule]:
        query = "SELECT * FROM automation_rules"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY name"
        with _conn(self._db) as con:
            rows = con.execute(query).fetchall()
        return [self._row_to_rule(r) for r in rows]

    def update_rule(self, rule: AutomationRule) -> bool:
        with _conn(self._db) as con:
            cur = con.execute(
                """UPDATE automation_rules
                   SET name=?, enabled=?, description=?,
                       trigger_json=?, actions_json=?
                   WHERE rule_id=?""",
                (
                    rule.name,
                    int(rule.enabled),
                    rule.description,
                    json.dumps(rule.trigger.to_dict()),
                    json.dumps([a.to_dict() for a in rule.actions]),
                    rule.rule_id,
                ),
            )
        return cur.rowcount > 0

    def delete_rule(self, rule_id: str) -> bool:
        with _conn(self._db) as con:
            cur = con.execute("DELETE FROM automation_rules WHERE rule_id = ?", (rule_id,))
        return cur.rowcount > 0

    def enable_rule(self, rule_id: str, enabled: bool = True) -> bool:
        with _conn(self._db) as con:
            cur = con.execute(
                "UPDATE automation_rules SET enabled=? WHERE rule_id=?",
                (int(enabled), rule_id),
            )
        return cur.rowcount > 0

    # ── Execution ─────────────────────────────────────────────────────────────

    def tick(self, now: Optional[datetime] = None) -> list[tuple[AutomationRule, list[CommandResult]]]:
        """
        Evaluate all time-based rules. Call this once per minute from scheduler.
        Returns list of (rule, results) for rules that fired.
        """
        now = now or datetime.now(timezone.utc)
        fired = []
        for rule in self.list_rules(enabled_only=True):
            if rule.trigger.trigger_type == TriggerType.TIME:
                if self._time_matches(rule.trigger, now):
                    results = self.execute_rule(rule)
                    fired.append((rule, results))
        return fired

    def check_sensor_triggers(
        self,
        device_id: str,
        attribute: str,
        value: Any,
    ) -> list[tuple[AutomationRule, list[CommandResult]]]:
        """
        Called when a device state attribute changes.
        Evaluates any SENSOR rules watching that device+attribute.
        """
        fired = []
        for rule in self.list_rules(enabled_only=True):
            t = rule.trigger
            if (
                t.trigger_type == TriggerType.SENSOR
                and t.device_id == device_id
                and t.attribute == attribute
                and self._value_matches(t.value, value)
            ):
                results = self.execute_rule(rule)
                fired.append((rule, results))
        return fired

    def trigger_by_voice(self, phrase: str) -> list[tuple[AutomationRule, list[CommandResult]]]:
        """Fire any VOICE rules whose phrase matches the utterance."""
        phrase_lower = phrase.lower().strip()
        fired = []
        for rule in self.list_rules(enabled_only=True):
            t = rule.trigger
            if t.trigger_type == TriggerType.VOICE and t.phrase:
                if t.phrase.lower().strip() in phrase_lower:
                    results = self.execute_rule(rule)
                    fired.append((rule, results))
        return fired

    def trigger_manual(self, rule_id: str) -> Optional[list[CommandResult]]:
        """Force-execute a rule by ID regardless of trigger type."""
        rule = self.get_rule(rule_id)
        if rule is None:
            return None
        return self.execute_rule(rule)

    def execute_rule(self, rule: AutomationRule) -> list[CommandResult]:
        """Execute all actions of a rule and record the run."""
        results: list[CommandResult] = []
        for action in rule.actions:
            result = self._execute_action(action)
            if result is not None:
                results.append(result)

        # Update run metadata
        now = datetime.now(timezone.utc).isoformat()
        with _conn(self._db) as con:
            con.execute(
                """UPDATE automation_rules
                   SET run_count = run_count + 1, last_triggered = ?
                   WHERE rule_id = ?""",
                (now, rule.rule_id),
            )
            con.execute(
                """INSERT INTO automation_log
                   (rule_id, rule_name, trigger_type, results_json, executed_at)
                   VALUES (?,?,?,?,?)""",
                (
                    rule.rule_id,
                    rule.name,
                    rule.trigger.trigger_type.value,
                    json.dumps([r.to_dict() for r in results]),
                    now,
                ),
            )

        # Fire post-hooks
        for hook in self._post_hooks:
            try:
                hook(rule, results)
            except Exception as exc:
                logger.error("Post-hook error for rule %s: %s", rule.name, exc)

        logger.info("Rule %r fired: %d actions, %d results", rule.name, len(rule.actions), len(results))
        return results

    def _execute_action(self, action: AutomationAction) -> Optional[CommandResult]:
        import time as _time

        if action.action_type == ActionType.DELAY:
            secs = action.delay_seconds or 0
            if secs > 0:
                _time.sleep(secs)
            return None

        if action.action_type == ActionType.NOTIFY:
            logger.info("Automation notify: %s", action.message)
            return CommandResult(
                success=True, device_id="system", command="notify",
                message=action.message or ""
            )

        if action.action_type == ActionType.SCENE:
            return self._execute_scene(action.scene_name or "")

        if action.action_type == ActionType.DEVICE_COMMAND:
            return self._dispatch_command(
                action.device_id or "",
                action.command or "",
                action.params,
            )

        return None

    def _dispatch_command(
        self,
        device_id: str,
        command: str,
        params: Optional[dict[str, Any]],
    ) -> CommandResult:
        if self._registry is None:
            return CommandResult(
                success=False, device_id=device_id, command=command,
                message="No device registry available",
            )
        device = self._registry.get(device_id)
        if device is None:
            return CommandResult(
                success=False, device_id=device_id, command=command,
                message=f"Device {device_id!r} not found",
            )
        adapter = self._adapters.get(device.adapter_type)
        if adapter is None:
            return CommandResult(
                success=False, device_id=device_id, command=command,
                message=f"No adapter for type {device.adapter_type!r}",
            )
        result = adapter.send_command(device, command, params)
        if result.success and result.new_state and self._registry:
            self._registry.update_state(device_id, result.new_state)
        return result

    def _execute_scene(self, scene_name: str) -> CommandResult:
        if self._registry is None:
            return CommandResult(
                success=False, device_id="scene", command=scene_name,
                message="No registry available",
            )
        actions_raw = self._registry.get_scene(scene_name)
        if actions_raw is None:
            return CommandResult(
                success=False, device_id="scene", command=scene_name,
                message=f"Scene {scene_name!r} not found",
            )
        results = []
        for action_dict in actions_raw:
            try:
                action = AutomationAction.from_dict(action_dict)
                r = self._execute_action(action)
                if r:
                    results.append(r)
            except Exception as exc:
                logger.error("Scene action error: %s", exc)
        all_ok = all(r.success for r in results) if results else True
        return CommandResult(
            success=all_ok,
            device_id="scene",
            command=scene_name,
            message=f"Scene {scene_name!r}: {len(results)} actions",
        )

    # ── Run log ───────────────────────────────────────────────────────────────

    def recent_log(self, limit: int = 50) -> list[dict[str, Any]]:
        with _conn(self._db) as con:
            rows = con.execute(
                "SELECT * FROM automation_log ORDER BY log_id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Hooks ─────────────────────────────────────────────────────────────────

    def add_post_hook(
        self, hook: Callable[[AutomationRule, list[CommandResult]], None]
    ) -> None:
        self._post_hooks.append(hook)

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _time_matches(trigger: AutomationTrigger, now: datetime) -> bool:
        """Check if a TIME trigger fires at `now`."""
        if trigger.time_str:
            # Format: "HH:MM" in local time
            try:
                hh, mm = trigger.time_str.split(":")
                return now.hour == int(hh) and now.minute == int(mm)
            except ValueError:
                return False
        if trigger.cron:
            return _cron_matches(trigger.cron, now)
        return False

    @staticmethod
    def _value_matches(expected: Any, actual: Any) -> bool:
        if expected is None:
            return actual is not None  # any truthy change
        return expected == actual

    @staticmethod
    def _row_to_rule(row: sqlite3.Row) -> AutomationRule:
        return AutomationRule(
            rule_id=row["rule_id"],
            name=row["name"],
            enabled=bool(row["enabled"]),
            description=row["description"],
            trigger=AutomationTrigger.from_dict(json.loads(row["trigger_json"])),
            actions=[AutomationAction.from_dict(a) for a in json.loads(row["actions_json"])],
            run_count=row["run_count"],
            last_triggered=row["last_triggered"],
            created_at=row["created_at"],
        )


# ── Minimal cron matcher (field-by-field, no library required) ────────────────

def _cron_matches(expr: str, now: datetime) -> bool:
    """
    Match a 5-field cron expression (minute hour dom month dow) against now.
    Supports * and comma-separated values. No ranges or steps.
    """
    try:
        parts = expr.strip().split()
        if len(parts) != 5:
            return False
        minute, hour, dom, month, dow = parts
        return (
            _field_matches(minute, now.minute)
            and _field_matches(hour, now.hour)
            and _field_matches(dom, now.day)
            and _field_matches(month, now.month)
            and _field_matches(dow, now.weekday())
        )
    except Exception:
        return False


def _field_matches(field: str, value: int) -> bool:
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            if int(lo) <= value <= int(hi):
                return True
        elif "/" in part:
            base, step = part.split("/", 1)
            base_val = 0 if base == "*" else int(base)
            if step and (value - base_val) % int(step) == 0:
                return True
        elif int(part) == value:
            return True
    return False
