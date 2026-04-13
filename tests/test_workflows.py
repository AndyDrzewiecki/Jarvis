"""Tests for WorkflowEngine — trigger/action callables mocked."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch

from jarvis.workflows import WorkflowEngine, Workflow


@pytest.fixture
def engine(tmp_path):
    return WorkflowEngine(
        state_path=str(tmp_path / "workflow_state.json"),
        auto_approve=False,
    )


@pytest.fixture
def auto_engine(tmp_path):
    return WorkflowEngine(
        state_path=str(tmp_path / "workflow_state.json"),
        auto_approve=True,
    )


# ── registration ───────────────────────────────────────────────────────────────

def test_builtin_workflows_registered(engine):
    names = [w["name"] for w in engine.status()]
    assert "grocery_closed_loop" in names
    assert "budget_warning" in names
    assert "security_watchdog" in names


def test_custom_workflow_registration(engine):
    wf = Workflow(name="custom", description="Test", trigger=lambda: True, action=lambda: "done")
    engine.register(wf)
    names = [w["name"] for w in engine.status()]
    assert "custom" in names


def test_status_returns_expected_keys(engine):
    for wf in engine.status():
        assert "name" in wf
        assert "description" in wf
        assert "last_triggered" in wf
        assert "pending_approval" in wf
        assert "cooldown_hours" in wf


# ── run_checks — no auto approve ───────────────────────────────────────────────

def test_trigger_false_no_action(engine):
    wf = Workflow(name="no_fire", description="", trigger=lambda: False, action=lambda: "x")
    engine.register(wf)
    results = engine.run_checks()
    assert not any("no_fire" in r for r in results)


def test_trigger_true_queues_approval(engine):
    wf = Workflow(name="needs_ok", description="", trigger=lambda: True, action=lambda: "executed")
    engine.register(wf)
    results = engine.run_checks()
    assert any("needs_ok" in r and "pending" in r for r in results)


def test_trigger_exception_does_not_crash(engine):
    def bad_trigger():
        raise RuntimeError("trigger error")
    wf = Workflow(name="bad_wf", description="", trigger=bad_trigger, action=lambda: "x")
    engine.register(wf)
    results = engine.run_checks()  # should not raise
    assert isinstance(results, list)


# ── run_checks — auto approve ──────────────────────────────────────────────────

def test_auto_approve_executes_action(auto_engine):
    wf = Workflow(name="auto_wf", description="", trigger=lambda: True, action=lambda: "auto done")
    auto_engine.register(wf)
    results = auto_engine.run_checks()
    assert any("auto_wf" in r and "auto done" in r for r in results)


def test_auto_approve_action_exception_captured(auto_engine):
    def bad_action():
        raise ValueError("oops")
    wf = Workflow(name="bad_action", description="", trigger=lambda: True, action=bad_action)
    auto_engine.register(wf)
    results = auto_engine.run_checks()
    assert any("bad_action" in r for r in results)


# ── approve ────────────────────────────────────────────────────────────────────

def test_approve_executes_pending_action(engine):
    action_mock = MagicMock(return_value="action result")
    wf = Workflow(name="approvable", description="", trigger=lambda: True, action=action_mock)
    engine.register(wf)
    engine.run_checks()  # queues for approval
    result = engine.approve("approvable")
    assert "action result" in result
    action_mock.assert_called_once()


def test_approve_unknown_workflow(engine):
    result = engine.approve("nonexistent_wf")
    assert "Unknown workflow" in result


def test_approve_without_pending(engine):
    wf = Workflow(name="not_pending", description="", trigger=lambda: False, action=lambda: "x")
    engine.register(wf)
    result = engine.approve("not_pending")
    assert "no pending" in result.lower()


def test_approve_clears_pending_flag(engine):
    action_mock = MagicMock(return_value="done")
    wf = Workflow(name="clear_pending", description="", trigger=lambda: True, action=action_mock)
    engine.register(wf)
    engine.run_checks()
    engine.approve("clear_pending")
    status = {w["name"]: w for w in engine.status()}
    assert status["clear_pending"]["pending_approval"] is False


# ── cooldown ───────────────────────────────────────────────────────────────────

def test_cooldown_prevents_refiring(auto_engine):
    call_count = {"n": 0}

    def action():
        call_count["n"] += 1
        return "fired"

    wf = Workflow(name="cd_wf", description="", trigger=lambda: True, action=action, cooldown_hours=1)
    auto_engine.register(wf)
    auto_engine.run_checks()  # fires
    auto_engine.run_checks()  # blocked by cooldown
    assert call_count["n"] == 1


# ── run_now ────────────────────────────────────────────────────────────────────

def test_run_now_auto_executes(auto_engine):
    wf = Workflow(name="manual_wf", description="", trigger=lambda: False, action=lambda: "manual result")
    auto_engine.register(wf)
    result = auto_engine.run_now("manual_wf")
    assert result == "manual result"


def test_run_now_no_auto_queues(engine):
    wf = Workflow(name="queue_wf", description="", trigger=lambda: False, action=lambda: "x")
    engine.register(wf)
    result = engine.run_now("queue_wf")
    assert "queued" in result.lower() or "approval" in result.lower()


def test_run_now_unknown_workflow(engine):
    result = engine.run_now("ghost_workflow")
    assert "Unknown workflow" in result
