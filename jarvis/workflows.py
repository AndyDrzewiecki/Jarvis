"""
Workflow Engine — Trigger → Action chains with a human approval gate.

Workflows check conditions on a 30-minute schedule. Actions require explicit
approval unless JARVIS_AUTO_APPROVE_WORKFLOWS=true.

Pre-built workflows:
  grocery_closed_loop  — expiring items → add to shopping list → notify
  budget_warning       — spend > 80% of budget → notify
  security_watchdog    — SP pending_approvals > 0 → notify every 4h

Safety model:
  JARVIS_AUTO_APPROVE_WORKFLOWS=false (default) → trigger fires, action
      requires POST /api/workflows/{name}/approve
  JARVIS_AUTO_APPROVE_WORKFLOWS=true → action executes immediately

All executions logged to agent_memory with agent="workflow_engine".

Usage:
    from jarvis.workflows import WorkflowEngine
    engine = WorkflowEngine()
    engine.run_checks()     # called by scheduler
    engine.approve("name")  # approve a pending action
    engine.run_now("name")  # manual trigger
    engine.status()         # list all workflows + state
"""
from __future__ import annotations
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Any, Optional

import jarvis.agent_memory as agent_memory
import jarvis.notifier as notifier

_STATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "workflow_state.json"
)

AUTO_APPROVE: bool = os.getenv("JARVIS_AUTO_APPROVE_WORKFLOWS", "false").lower() == "true"


@dataclass
class Workflow:
    name: str
    description: str
    trigger: Callable[[], bool]
    action: Callable[[], str]
    auto_approve: bool = False
    cooldown_hours: int = 1


class WorkflowEngine:
    def __init__(
        self,
        state_path: Optional[str] = None,
        auto_approve: Optional[bool] = None,
    ) -> None:
        self._state_path = state_path or os.environ.get(
            "JARVIS_WORKFLOW_STATE_PATH", _STATE_PATH
        )
        self._auto_approve = auto_approve if auto_approve is not None else AUTO_APPROVE
        self._workflows: dict[str, Workflow] = {}
        self._register_builtins()

    # ── registration ──────────────────────────────────────────────────────────

    def register(self, workflow: Workflow) -> None:
        self._workflows[workflow.name] = workflow

    def _register_builtins(self) -> None:
        self.register(Workflow(
            name="grocery_closed_loop",
            description="Expiring items detected → add to shopping list → notify",
            trigger=self._trigger_expiring,
            action=self._action_add_expiring_to_list,
            cooldown_hours=4,
        ))
        self.register(Workflow(
            name="budget_warning",
            description="Monthly grocery spend > 80% of budget → notify",
            trigger=self._trigger_over_budget,
            action=self._action_budget_notify,
            cooldown_hours=24,
        ))
        self.register(Workflow(
            name="security_watchdog",
            description="SummerPuppy pending approvals > 0 → notify every 4h",
            trigger=self._trigger_security_pending,
            action=self._action_security_notify,
            cooldown_hours=4,
        ))

    # ── state persistence ──────────────────────────────────────────────────────

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

    # ── scheduling ────────────────────────────────────────────────────────────

    def run_checks(self) -> list[str]:
        """Run all trigger checks; execute or queue actions. Returns log."""
        state = self._load_state()
        results: list[str] = []

        for name, wf in self._workflows.items():
            wf_state = state.setdefault(name, {})
            if not self._cooldown_ok(wf_state, wf.cooldown_hours):
                continue
            try:
                fired = wf.trigger()
            except Exception as exc:
                agent_memory.log_decision(
                    agent="workflow_engine",
                    capability=name,
                    decision="Trigger check failed",
                    reasoning=str(exc),
                    outcome="failure",
                )
                continue

            if not fired:
                continue

            auto = self._auto_approve or wf.auto_approve
            if auto:
                try:
                    result_text = wf.action()
                except Exception as exc:
                    result_text = f"Action failed: {exc}"
                wf_state["last_triggered"] = datetime.now(timezone.utc).isoformat()
                wf_state["pending_approval"] = False
                results.append(f"{name}: {result_text}")
                agent_memory.log_decision(
                    agent="workflow_engine",
                    capability=name,
                    decision=f"Auto-executed: {result_text[:200]}",
                    reasoning="JARVIS_AUTO_APPROVE_WORKFLOWS=true",
                    outcome="success",
                )
            else:
                wf_state["pending_approval"] = True
                results.append(f"{name}: pending approval")
                agent_memory.log_decision(
                    agent="workflow_engine",
                    capability=name,
                    decision="Triggered — awaiting approval",
                    reasoning="Manual approval required (auto_approve=false)",
                    outcome="pending",
                )

        self._save_state(state)
        return results

    def approve(self, name: str) -> str:
        """Approve and execute a pending workflow action."""
        if name not in self._workflows:
            return f"Unknown workflow: {name}"
        state = self._load_state()
        wf_state = state.setdefault(name, {})
        if not wf_state.get("pending_approval"):
            return f"Workflow '{name}' has no pending action."
        wf = self._workflows[name]
        try:
            result_text = wf.action()
        except Exception as exc:
            result_text = f"Action failed: {exc}"
        wf_state["last_triggered"] = datetime.now(timezone.utc).isoformat()
        wf_state["pending_approval"] = False
        self._save_state(state)
        agent_memory.log_decision(
            agent="workflow_engine",
            capability=name,
            decision=f"Approved and executed: {result_text[:200]}",
            reasoning="Manual approval received",
            outcome="success",
        )
        return result_text

    def run_now(self, name: str) -> str:
        """Manually trigger a workflow, bypassing cooldown and trigger check."""
        if name not in self._workflows:
            return f"Unknown workflow: {name}"
        wf = self._workflows[name]
        state = self._load_state()
        wf_state = state.setdefault(name, {})
        auto = self._auto_approve or wf.auto_approve
        if not auto:
            wf_state["pending_approval"] = True
            self._save_state(state)
            return f"Workflow '{name}' queued for approval."
        try:
            result_text = wf.action()
        except Exception as exc:
            result_text = f"Action failed: {exc}"
        wf_state["last_triggered"] = datetime.now(timezone.utc).isoformat()
        wf_state["pending_approval"] = False
        self._save_state(state)
        return result_text

    def status(self) -> list[dict[str, Any]]:
        """Return status of all workflows."""
        state = self._load_state()
        result = []
        for name, wf in self._workflows.items():
            wf_state = state.get(name, {})
            result.append({
                "name": name,
                "description": wf.description,
                "last_triggered": wf_state.get("last_triggered"),
                "pending_approval": wf_state.get("pending_approval", False),
                "cooldown_hours": wf.cooldown_hours,
                "auto_approve": self._auto_approve or wf.auto_approve,
            })
        return result

    # ── helpers ───────────────────────────────────────────────────────────────

    def _cooldown_ok(self, wf_state: dict, cooldown_hours: int) -> bool:
        last = wf_state.get("last_triggered")
        if not last:
            return True
        try:
            last_dt = datetime.fromisoformat(last)
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
            return elapsed >= cooldown_hours
        except Exception:
            return True

    # ── builtin triggers ──────────────────────────────────────────────────────

    def _trigger_expiring(self) -> bool:
        try:
            from jarvis.adapters import ALL_ADAPTERS
            adapter_map = {a.name: a for a in ALL_ADAPTERS}
            adapter = adapter_map.get("homeops_grocery")
            if adapter is None:
                return False
            result = adapter.safe_run("expiring_soon", {"days": 2})
            return result.success and bool((result.data or {}).get("items"))
        except Exception:
            return False

    def _trigger_over_budget(self) -> bool:
        try:
            from jarvis.adapters import ALL_ADAPTERS
            from jarvis.preferences import get as prefs_get
            adapter_map = {a.name: a for a in ALL_ADAPTERS}
            adapter = adapter_map.get("homeops_grocery")
            if adapter is None:
                return False
            result = adapter.safe_run("dashboard", {})
            if not result.success:
                return False
            data = result.data or {}
            spend = float(data.get("monthly_spend", 0) or 0)
            budget = float(prefs_get("budget_monthly", 800))
            return budget > 0 and (spend / budget) >= 0.8
        except Exception:
            return False

    def _trigger_security_pending(self) -> bool:
        try:
            from jarvis.adapters import ALL_ADAPTERS
            adapter_map = {a.name: a for a in ALL_ADAPTERS}
            adapter = adapter_map.get("summerpuppy")
            if adapter is None:
                return False
            result = adapter.safe_run("dashboard_summary", {})
            if not result.success:
                return False
            data = result.data or {}
            return int(data.get("pending_approvals", 0)) > 0
        except Exception:
            return False

    # ── builtin actions ───────────────────────────────────────────────────────

    def _action_add_expiring_to_list(self) -> str:
        try:
            from jarvis.adapters import ALL_ADAPTERS
            adapter_map = {a.name: a for a in ALL_ADAPTERS}
            hg = adapter_map.get("homeops_grocery")
            if hg is None:
                return "homeops_grocery adapter not available"
            result = hg.safe_run("expiring_soon", {"days": 2})
            if not result.success:
                return "Could not get expiring items"
            items = (result.data or {}).get("items", [])
            added = []
            for item in items:
                name = item.get("name", "Unknown")
                hg.safe_run("shopping_add", {"name": name, "quantity": 1})
                added.append(name)
            msg = f"Added {len(added)} expiring item(s) to shopping list: {', '.join(added)}"
            notifier.notify(msg, title="Jarvis — Grocery Loop")
            return msg
        except Exception as exc:
            return f"Failed: {exc}"

    def _action_budget_notify(self) -> str:
        try:
            from jarvis.adapters import ALL_ADAPTERS
            from jarvis.preferences import get as prefs_get
            adapter_map = {a.name: a for a in ALL_ADAPTERS}
            adapter = adapter_map.get("homeops_grocery")
            if adapter is None:
                return "homeops_grocery adapter not available"
            result = adapter.safe_run("dashboard", {})
            if not result.success:
                return "Could not get dashboard data"
            data = result.data or {}
            spend = float(data.get("monthly_spend", 0) or 0)
            budget = float(prefs_get("budget_monthly", 800))
            pct = spend / budget * 100 if budget > 0 else 0
            msg = f"💸 Grocery budget at {pct:.0f}% (${spend:.0f}/${budget:.0f})"
            notifier.notify(msg, title="Jarvis — Budget Warning")
            return msg
        except Exception as exc:
            return f"Failed: {exc}"

    def _action_security_notify(self) -> str:
        try:
            from jarvis.adapters import ALL_ADAPTERS
            adapter_map = {a.name: a for a in ALL_ADAPTERS}
            adapter = adapter_map.get("summerpuppy")
            if adapter is None:
                return "summerpuppy adapter not available"
            result = adapter.safe_run("dashboard_summary", {})
            if not result.success:
                return "Could not get security data"
            data = result.data or {}
            pending = int(data.get("pending_approvals", 0))
            msg = f"🔒 {pending} security event(s) pending approval"
            notifier.notify(msg, title="Jarvis — Security Alert")
            return msg
        except Exception as exc:
            return f"Failed: {exc}"
