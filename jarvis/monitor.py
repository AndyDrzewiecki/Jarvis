"""
HealthMonitor — checks live adapters every 15 minutes.

Pushes immediate Discord alerts on anomalies without waiting for 8am brief.

Alert conditions:
  investor        — market regime changed since last check
  summerpuppy     — pending_approvals > 0  (re-fires every 4h)
  homeops_grocery — items expiring within 2 days  (once per item)
  homeops_grocery — monthly_spend > 80% of budget

State persisted in data/monitor_state.json for deduplication.

Preferences:
  notification_level: critical = SummerPuppy only
                      important = all above (default)
                      all       = includes budget at any threshold

Usage:
    from jarvis.monitor import HealthMonitor
    monitor = HealthMonitor()
    monitor.check()
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Any

import jarvis.agent_memory as agent_memory
import jarvis.notifier as notifier

_STATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "monitor_state.json"
)

# Re-alert interval for pending approval alerts (4 hours)
_REFIRE_SECONDS = 4 * 3600


class HealthMonitor:
    """Check live adapters and fire Discord alerts on anomalies."""

    def __init__(self, state_path: str | None = None) -> None:
        self._state_path = state_path or os.environ.get(
            "JARVIS_MONITOR_STATE_PATH", _STATE_PATH
        )

    # ── state persistence ─────────────────────────────────────────────────────

    def _load_state(self) -> dict[str, Any]:
        try:
            with open(self._state_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(self._state_path)), exist_ok=True)
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)

    # ── main check ────────────────────────────────────────────────────────────

    def check(self) -> list[str]:
        """Run all checks and return list of alert messages sent."""
        from jarvis.adapters import ALL_ADAPTERS
        from jarvis.preferences import get as prefs_get

        adapter_map = {a.name: a for a in ALL_ADAPTERS}
        state = self._load_state()
        notification_level = prefs_get("notification_level", "important")
        alerts_sent: list[str] = []

        alerts_sent += self._check_investor(adapter_map, state, notification_level)
        alerts_sent += self._check_summerpuppy(adapter_map, state, notification_level)
        alerts_sent += self._check_expiring(adapter_map, state, notification_level)
        alerts_sent += self._check_budget(adapter_map, state, notification_level, prefs_get)

        self._save_state(state)

        agent_memory.log_decision(
            agent="health_monitor",
            capability="check",
            decision=f"Health check complete. {len(alerts_sent)} alert(s) sent.",
            reasoning=f"Notification level: {notification_level}",
            outcome="success",
        )
        return alerts_sent

    # ── individual checks ─────────────────────────────────────────────────────

    def _check_investor(
        self, adapters: dict, state: dict, level: str
    ) -> list[str]:
        if level == "critical":
            return []
        adapter = adapters.get("investor")
        if adapter is None:
            return []
        result = adapter.safe_run("market_check", {})
        if not result.success:
            return []
        data = result.data or {}
        regime = data.get("regime") or _extract_regime(result.text)
        if not regime:
            return []
        prev_regime = state.get("investor_regime")
        state["investor_regime"] = regime
        if prev_regime and prev_regime != regime:
            msg = f"⚠️ Market regime shift: {prev_regime} → {regime}"
            notifier.notify(msg, title="Jarvis — Market Alert")
            return [msg]
        return []

    def _check_summerpuppy(
        self, adapters: dict, state: dict, level: str
    ) -> list[str]:
        adapter = adapters.get("summerpuppy")
        if adapter is None:
            return []
        result = adapter.safe_run("dashboard_summary", {})
        if not result.success:
            return []
        data = result.data or {}
        try:
            pending = int(data.get("pending_approvals", 0))
        except (TypeError, ValueError):
            pending = 0
        if pending <= 0:
            state.pop("summerpuppy_alert_time", None)
            return []
        last_alert = state.get("summerpuppy_alert_time")
        now_ts = datetime.now(timezone.utc).timestamp()
        if last_alert is None or (now_ts - float(last_alert)) >= _REFIRE_SECONDS:
            msg = f"🔒 {pending} event(s) pending your approval"
            notifier.notify(msg, title="Jarvis — Security Alert")
            state["summerpuppy_alert_time"] = str(now_ts)
            return [msg]
        return []

    def _check_expiring(
        self, adapters: dict, state: dict, level: str
    ) -> list[str]:
        if level == "critical":
            return []
        adapter = adapters.get("homeops_grocery")
        if adapter is None:
            return []
        result = adapter.safe_run("expiring_soon", {"days": 2})
        if not result.success:
            return []
        items = (result.data or {}).get("items", [])
        if not items:
            return []
        alerted: set[str] = set(state.get("expiring_alerted", []))
        sent: list[str] = []
        for item in items:
            name = item.get("name", "Unknown item")
            expiry = item.get("expires_at") or item.get("expiry_date", "soon")
            key = f"{name}:{expiry}"
            if key not in alerted:
                msg = f"🥛 {name} expires {expiry}"
                notifier.notify(msg, title="Jarvis — Pantry Alert")
                alerted.add(key)
                sent.append(msg)
        state["expiring_alerted"] = list(alerted)
        return sent

    def _check_budget(
        self, adapters: dict, state: dict, level: str, prefs_get: Any
    ) -> list[str]:
        if level == "critical":
            return []
        adapter = adapters.get("homeops_grocery")
        if adapter is None:
            return []
        result = adapter.safe_run("dashboard", {})
        if not result.success:
            return []
        data = result.data or {}
        try:
            monthly_spend = float(data.get("monthly_spend", 0) or 0)
        except (TypeError, ValueError):
            return []
        budget = float(prefs_get("budget_monthly", 800))
        if budget <= 0:
            return []
        pct = monthly_spend / budget * 100
        threshold = 80.0 if level == "important" else 0.0
        if pct < threshold:
            state.pop("budget_alerted_pct", None)
            return []
        last_pct = float(state.get("budget_alerted_pct", 0))
        if pct > last_pct:
            msg = f"💸 Grocery budget {pct:.0f}% consumed (${monthly_spend:.0f}/${budget:.0f})"
            notifier.notify(msg, title="Jarvis — Budget Alert")
            state["budget_alerted_pct"] = str(pct)
            return [msg]
        return []


def _extract_regime(text: str) -> str:
    """Try to extract a regime label from free-text investor output."""
    text_lower = text.lower()
    for label in ("bull", "bear", "neutral", "risk-off", "risk-on", "volatile"):
        if label in text_lower:
            return label
    return ""
