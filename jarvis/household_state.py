"""
Household State Machine — tracks the current operational mode of the household.

The state has:
- A primary mode (e.g. "normal", "summer", "budget_tight")
- A set of active modifiers (e.g. "grocery_day", "payday", "guests_coming")
- A history of transitions (last 50)

State is persisted as JSON to HOUSEHOLD_STATE_PATH (default: data/household_state.json).
Every transition is logged to agent_memory.log_decision for traceability.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Valid primary states
VALID_PRIMARIES: set[str] = {
    "normal",
    "summer",
    "winter",
    "holiday",
    "budget_tight",
    "guests_coming",
    "vacation",
    "sick_day",
    "spring_cleaning",
}

# Valid modifier flags
VALID_MODIFIERS: set[str] = {
    "grocery_day",
    "payday",
    "date_night",
    "meal_prep",
    "leftovers",
    "school_night",
    "weekend",
    "long_weekend",
    "outdoor_dining",
    "guests_arriving_soon",
    "cooking_ahead",
    "low_pantry",
}

_DEFAULT_STATE: dict = {
    "primary": "normal",
    "modifiers": [],
    "history": [],
}


class HouseholdState:
    """Persistent household state machine."""

    def __init__(self, state_path: str | None = None):
        if state_path is None:
            from jarvis import config
            state_path = config.HOUSEHOLD_STATE_PATH
        self._path = state_path
        self._state = self._load()

    def _load(self) -> dict:
        """Load state from JSON file or return default."""
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Ensure all required keys exist
                return {
                    "primary": data.get("primary", "normal"),
                    "modifiers": list(data.get("modifiers", [])),
                    "history": list(data.get("history", [])),
                }
            except Exception as exc:
                logger.warning("HouseholdState: failed to load %s: %s", self._path, exc)
        return {
            "primary": "normal",
            "modifiers": [],
            "history": [],
        }

    def _save(self) -> None:
        """Persist current state to JSON file."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._path)), exist_ok=True)
            payload = {
                "primary": self._state["primary"],
                "modifiers": sorted(self._state["modifiers"]),
                "history": self._state["history"][-50:],
            }
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            logger.warning("HouseholdState: failed to save %s: %s", self._path, exc)

    def _log_transition(self, event: str, from_state: str, to_state: str, reason: str) -> None:
        """Append to history list and log to agent_memory."""
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "from": from_state,
            "to": to_state,
            "reason": reason,
        }
        self._state["history"].append(entry)
        try:
            import jarvis.agent_memory as am
            am.log_decision(
                agent="household_state",
                capability="transition",
                decision=f"{event}: {from_state} → {to_state}",
                reasoning=reason,
                outcome="success",
            )
        except Exception as exc:
            logger.warning("HouseholdState: log_decision failed: %s", exc)

    def transition(self, new_primary: str, reason: str) -> None:
        """Transition to a new primary state.

        Raises ValueError if new_primary is not in VALID_PRIMARIES.
        """
        if new_primary not in VALID_PRIMARIES:
            raise ValueError(
                f"Invalid primary state: {new_primary!r}. "
                f"Must be one of: {sorted(VALID_PRIMARIES)}"
            )
        old_primary = self._state["primary"]
        self._state["primary"] = new_primary
        self._log_transition("primary_transition", old_primary, new_primary, reason)
        self._save()

    def add_modifier(self, modifier: str, reason: str) -> None:
        """Add a modifier flag to the current state.

        Raises ValueError if modifier is not in VALID_MODIFIERS.
        """
        if modifier not in VALID_MODIFIERS:
            raise ValueError(
                f"Invalid modifier: {modifier!r}. "
                f"Must be one of: {sorted(VALID_MODIFIERS)}"
            )
        if modifier not in self._state["modifiers"]:
            self._state["modifiers"].append(modifier)
        self._log_transition("add_modifier", "", modifier, reason)
        self._save()

    def remove_modifier(self, modifier: str, reason: str) -> None:
        """Remove a modifier flag. No-op if not present."""
        if modifier in self._state["modifiers"]:
            self._state["modifiers"].remove(modifier)
            self._log_transition("remove_modifier", modifier, "", reason)
            self._save()

    def has_modifier(self, modifier: str) -> bool:
        """Return True if the modifier is currently active."""
        return modifier in self._state["modifiers"]

    def current(self) -> dict:
        """Return current state as a dict with 'primary' and 'modifiers' (sorted list)."""
        return {
            "primary": self._state["primary"],
            "modifiers": sorted(self._state["modifiers"]),
        }

    def is_budget_sensitive(self) -> bool:
        """Return True if household is in a budget-sensitive mode.

        Budget sensitive when:
        - primary == "budget_tight", OR
        - "payday" modifier is NOT active (we're spending cautiously until payday)
        """
        if self._state["primary"] == "budget_tight":
            return True
        return "payday" not in self._state["modifiers"]

    def get_history(self, n: int = 10) -> list[dict]:
        """Return last N history entries, most recent first."""
        return list(reversed(self._state["history"][-n:]))[-n:]
