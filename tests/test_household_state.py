from __future__ import annotations
import json
import os
from unittest.mock import patch, MagicMock
import pytest


# ── test_default_state_is_normal ─────────────────────────────────────────────

def test_default_state_is_normal(tmp_path):
    """New HouseholdState → primary == 'normal', modifiers == set()."""
    from jarvis.household_state import HouseholdState
    hs = HouseholdState(state_path=str(tmp_path / "state.json"))
    assert hs.current()["primary"] == "normal"
    assert hs.current()["modifiers"] == []


# ── test_transition_changes_primary ──────────────────────────────────────────

def test_transition_changes_primary(tmp_path):
    """transition('summer', reason) → primary == 'summer'."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.transition("summer", "school's out")
    assert hs.current()["primary"] == "summer"


# ── test_transition_invalid_raises ───────────────────────────────────────────

def test_transition_invalid_raises(tmp_path):
    """transition('invalid_mode', reason) → raises ValueError."""
    from jarvis.household_state import HouseholdState
    hs = HouseholdState(state_path=str(tmp_path / "state.json"))
    with pytest.raises(ValueError):
        hs.transition("invalid_mode", "test")


# ── test_add_modifier ────────────────────────────────────────────────────────

def test_add_modifier(tmp_path):
    """add_modifier('grocery_day', reason) → 'grocery_day' in modifiers."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.add_modifier("grocery_day", "it's friday")
    assert "grocery_day" in hs.current()["modifiers"]


# ── test_add_invalid_modifier_raises ─────────────────────────────────────────

def test_add_invalid_modifier_raises(tmp_path):
    """add_modifier with invalid value → raises ValueError."""
    from jarvis.household_state import HouseholdState
    hs = HouseholdState(state_path=str(tmp_path / "state.json"))
    with pytest.raises(ValueError):
        hs.add_modifier("not_valid", "test")


# ── test_remove_modifier ─────────────────────────────────────────────────────

def test_remove_modifier(tmp_path):
    """add then remove → modifier not in modifiers."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.add_modifier("grocery_day", "test")
        hs.remove_modifier("grocery_day", "test")
    assert "grocery_day" not in hs.current()["modifiers"]


# ── test_remove_nonexistent_modifier_noop ────────────────────────────────────

def test_remove_nonexistent_modifier_noop(tmp_path):
    """remove_modifier on non-existent modifier → no error."""
    from jarvis.household_state import HouseholdState
    hs = HouseholdState(state_path=str(tmp_path / "state.json"))
    # Should not raise
    hs.remove_modifier("grocery_day", "test")
    assert "grocery_day" not in hs.current()["modifiers"]


# ── test_persistence ─────────────────────────────────────────────────────────

def test_persistence(tmp_path):
    """transition + add_modifier, then new instance at same path → same state."""
    state_path = str(tmp_path / "state.json")
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs1 = HouseholdState(state_path=state_path)
        hs1.transition("summer", "hot outside")
        hs1.add_modifier("grocery_day", "friday")

    from jarvis.household_state import HouseholdState
    hs2 = HouseholdState(state_path=state_path)
    state = hs2.current()
    assert state["primary"] == "summer"
    assert "grocery_day" in state["modifiers"]


# ── test_current_returns_dict ─────────────────────────────────────────────────

def test_current_returns_dict(tmp_path):
    """current() returns {'primary': 'normal', 'modifiers': []}."""
    from jarvis.household_state import HouseholdState
    hs = HouseholdState(state_path=str(tmp_path / "state.json"))
    state = hs.current()
    assert isinstance(state, dict)
    assert "primary" in state
    assert "modifiers" in state
    assert isinstance(state["modifiers"], list)


# ── test_is_budget_sensitive_primary ─────────────────────────────────────────

def test_is_budget_sensitive_primary(tmp_path):
    """transition to 'budget_tight' → is_budget_sensitive() True."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.transition("budget_tight", "overspent")
    assert hs.is_budget_sensitive() is True


# ── test_is_budget_sensitive_no_payday ───────────────────────────────────────

def test_is_budget_sensitive_no_payday(tmp_path):
    """Default state, 'payday' not in modifiers → is_budget_sensitive() True."""
    from jarvis.household_state import HouseholdState
    hs = HouseholdState(state_path=str(tmp_path / "state.json"))
    assert hs.is_budget_sensitive() is True


# ── test_is_budget_sensitive_payday ──────────────────────────────────────────

def test_is_budget_sensitive_payday(tmp_path):
    """add_modifier('payday') → is_budget_sensitive() False."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.add_modifier("payday", "friday is payday")
    assert hs.is_budget_sensitive() is False


# ── test_get_history_returns_transitions ─────────────────────────────────────

def test_get_history_returns_transitions(tmp_path):
    """3 transitions → get_history(2) returns 2 entries, most recent first."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.transition("summer", "reason 1")
        hs.transition("budget_tight", "reason 2")
        hs.transition("normal", "reason 3")

    history = hs.get_history(2)
    assert len(history) == 2
    # Most recent first
    assert history[0]["to"] == "normal"
    assert history[1]["to"] == "budget_tight"


# ── test_transitions_log_to_agent_memory ─────────────────────────────────────

def test_transitions_log_to_agent_memory(tmp_path):
    """transition() calls agent_memory.log_decision."""
    with patch("jarvis.agent_memory.log_decision", return_value="did") as mock_log:
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        hs.transition("summer", "school out")
    mock_log.assert_called_once()


# ── test_has_modifier ────────────────────────────────────────────────────────

def test_has_modifier(tmp_path):
    """has_modifier('grocery_day') False initially, True after add."""
    with patch("jarvis.agent_memory.log_decision", return_value="did"):
        from jarvis.household_state import HouseholdState
        hs = HouseholdState(state_path=str(tmp_path / "state.json"))
        assert hs.has_modifier("grocery_day") is False
        hs.add_modifier("grocery_day", "friday")
        assert hs.has_modifier("grocery_day") is True
