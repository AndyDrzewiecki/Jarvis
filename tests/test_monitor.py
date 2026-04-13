"""Tests for HealthMonitor — adapter calls and notifier mocked."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

from jarvis.adapters.base import AdapterResult


def _make_adapter(name: str, success: bool = True, data: dict = None, text: str = "ok"):
    a = MagicMock()
    a.name = name
    a.safe_run.return_value = AdapterResult(
        success=success, text=text, data=data or {}, adapter=name
    )
    return a


@pytest.fixture
def monitor(tmp_path):
    from jarvis.monitor import HealthMonitor
    return HealthMonitor(state_path=str(tmp_path / "monitor_state.json"))


# ── state persistence ──────────────────────────────────────────────────────────

def test_initial_state_empty(tmp_path):
    from jarvis.monitor import HealthMonitor
    m = HealthMonitor(state_path=str(tmp_path / "state.json"))
    assert m._load_state() == {}


def test_save_and_load_state(monitor):
    monitor._save_state({"foo": "bar"})
    assert monitor._load_state() == {"foo": "bar"}


def test_state_file_created_on_save(monitor, tmp_path):
    monitor._save_state({"key": "val"})
    assert (tmp_path / "monitor_state.json").exists()


# ── investor regime check ──────────────────────────────────────────────────────

def test_investor_regime_shift_sends_alert(monitor):
    investor = _make_adapter("investor", data={"regime": "bear"})
    adapters = {"investor": investor}
    state = {"investor_regime": "bull"}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_investor(adapters, state, "important")
    assert len(alerts) == 1
    assert "bull" in alerts[0] and "bear" in alerts[0]
    mock_notify.assert_called_once()


def test_investor_no_regime_change_no_alert(monitor):
    investor = _make_adapter("investor", data={"regime": "bull"})
    adapters = {"investor": investor}
    state = {"investor_regime": "bull"}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_investor(adapters, state, "important")
    assert len(alerts) == 0
    mock_notify.assert_not_called()


def test_investor_first_run_no_alert(monitor):
    """First check: no previous regime stored, so no alert even if regime set."""
    investor = _make_adapter("investor", data={"regime": "bull"})
    adapters = {"investor": investor}
    state = {}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_investor(adapters, state, "important")
    assert len(alerts) == 0


def test_investor_skipped_at_critical_level(monitor):
    investor = _make_adapter("investor", data={"regime": "bear"})
    adapters = {"investor": investor}
    state = {"investor_regime": "bull"}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_investor(adapters, state, "critical")
    assert len(alerts) == 0
    mock_notify.assert_not_called()


# ── summerpuppy check ──────────────────────────────────────────────────────────

def test_summerpuppy_pending_fires_alert(monitor):
    sp = _make_adapter("summerpuppy", data={"pending_approvals": 3})
    adapters = {"summerpuppy": sp}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_summerpuppy(adapters, {}, "important")
    assert len(alerts) == 1
    assert "3" in alerts[0]
    mock_notify.assert_called_once()


def test_summerpuppy_no_pending_no_alert(monitor):
    sp = _make_adapter("summerpuppy", data={"pending_approvals": 0})
    adapters = {"summerpuppy": sp}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_summerpuppy(adapters, {}, "important")
    assert len(alerts) == 0
    mock_notify.assert_not_called()


def test_summerpuppy_refire_blocked_within_window(monitor):
    """If alerted less than 4h ago, no re-alert."""
    import time
    sp = _make_adapter("summerpuppy", data={"pending_approvals": 2})
    adapters = {"summerpuppy": sp}
    state = {"summerpuppy_alert_time": str(time.time())}  # just now
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_summerpuppy(adapters, state, "important")
    assert len(alerts) == 0
    mock_notify.assert_not_called()


# ── expiring items check ───────────────────────────────────────────────────────

def test_expiring_items_fires_alert(monitor):
    hg = _make_adapter(
        "homeops_grocery",
        data={"items": [{"name": "Chicken", "expires_at": "Fri"}]},
    )
    adapters = {"homeops_grocery": hg}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_expiring(adapters, {}, "important")
    assert len(alerts) == 1
    assert "Chicken" in alerts[0]
    mock_notify.assert_called_once()


def test_expiring_deduplication(monitor):
    hg = _make_adapter(
        "homeops_grocery",
        data={"items": [{"name": "Milk", "expires_at": "Thu"}]},
    )
    adapters = {"homeops_grocery": hg}
    state = {"expiring_alerted": ["Milk:Thu"]}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_expiring(adapters, state, "important")
    assert len(alerts) == 0
    mock_notify.assert_not_called()


def test_expiring_skipped_at_critical_level(monitor):
    hg = _make_adapter(
        "homeops_grocery",
        data={"items": [{"name": "Eggs", "expires_at": "Sat"}]},
    )
    adapters = {"homeops_grocery": hg}
    with patch("jarvis.monitor.notifier.notify") as mock_notify:
        alerts = monitor._check_expiring(adapters, {}, "critical")
    assert len(alerts) == 0


# ── full check integration ─────────────────────────────────────────────────────

def test_check_runs_without_error(monitor):
    with patch("jarvis.adapters.ALL_ADAPTERS", []):
        with patch("jarvis.preferences.get", return_value="important"):
            alerts = monitor.check()
    assert isinstance(alerts, list)
