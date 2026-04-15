"""ForgeOrchestrator — dispatches tasks to dev agents, tracks progress, checks results.

The orchestrator is the coordination layer. It:
  - Accepts task definitions and routes them to the right agent
  - Tracks in-flight and completed tasks in shared memory (Layer 2)
  - Checks results when tasks complete
  - Can run agents sequentially or dispatch multiple independent tasks

Task schema (input):
    {
      "type":    str,      # "evaluate" | "review" | "audit" | "train"
      "target":  str,      # agent name to do the work
      "payload": dict,     # task-specific data
      "priority": int,     # 1 (high) – 3 (low), default 2
    }
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.forge.agent_base import BaseDevAgent, TaskResult
from jarvis.forge.memory_store import ForgeMemoryStore

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OrchestratorStatus:
    """Summary of orchestrator state."""
    agents_registered: int
    tasks_dispatched: int
    tasks_succeeded: int
    tasks_failed: int
    active_task_ids: list[str]


class ForgeOrchestrator:
    """Routes tasks to dev agents and tracks outcomes.

    Usage::

        orch = ForgeOrchestrator()
        orch.register(my_critic)
        result = orch.dispatch({"type": "evaluate", "target": "critic", "payload": {...}})
    """

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        self._store = memory_store or ForgeMemoryStore()
        self._agents: dict[str, BaseDevAgent] = {}
        self._active: dict[str, dict] = {}   # task_id → task metadata
        self._history: list[TaskResult] = []  # in-memory history (last 500)
        self._dispatched = 0
        self._succeeded = 0
        self._failed = 0

    # ------------------------------------------------------------------
    # Agent registry
    # ------------------------------------------------------------------

    def register(self, agent: BaseDevAgent) -> None:
        """Register a dev agent so it can receive tasks."""
        self._agents[agent.name] = agent
        logger.info("Orchestrator: registered agent '%s' (model=%s)", agent.name, agent.model)

    def unregister(self, agent_name: str) -> None:
        self._agents.pop(agent_name, None)

    def registered_agents(self) -> list[str]:
        return list(self._agents.keys())

    # ------------------------------------------------------------------
    # Task dispatch
    # ------------------------------------------------------------------

    def dispatch(self, task: dict) -> TaskResult:
        """Dispatch a task to the named agent. Runs synchronously and returns result.

        Args:
            task: dict with at minimum {"type": str, "target": str, "payload": dict}

        Returns:
            TaskResult from the agent.
        """
        task_id = task.get("id") or str(uuid.uuid4())
        task["id"] = task_id

        target = task.get("target", "")
        agent = self._agents.get(target)

        if agent is None:
            logger.warning("Orchestrator: no agent named '%s' registered", target)
            result = TaskResult(
                task_id=task_id,
                agent=target or "unknown",
                status="failure",
                output="",
                error=f"No agent named '{target}' is registered",
            )
            self._record(task, result)
            return result

        # Log routing decision (Layer 2)
        routing_id = self._store.log_routing(
            agent="orchestrator",
            routed_to=target,
            reason=f"task_type={task.get('type')}",
            task_id=task_id,
            confidence=1.0,
        )

        self._active[task_id] = {"task": task, "routing_id": routing_id, "started_at": _now()}
        self._dispatched += 1

        try:
            result = agent.run(task)
        except Exception as exc:
            logger.exception("Orchestrator: agent '%s' raised during run", target)
            result = TaskResult(
                task_id=task_id,
                agent=target,
                status="failure",
                output="",
                error=str(exc),
            )

        # Update routing outcome
        try:
            self._store.update_routing_outcome(
                routing_id,
                "success" if result.status == "success" else "failure",
            )
        except Exception:
            pass

        self._active.pop(task_id, None)
        self._record(task, result)

        if result.status == "success":
            self._succeeded += 1
        else:
            self._failed += 1

        logger.info(
            "Orchestrator: task %s → %s [%s] %.0fms",
            task_id, target, result.status, result.duration_ms,
        )
        return result

    def dispatch_many(self, tasks: list[dict]) -> list[TaskResult]:
        """Dispatch multiple tasks sequentially. Returns results in input order."""
        return [self.dispatch(t) for t in tasks]

    # ------------------------------------------------------------------
    # Progress / results
    # ------------------------------------------------------------------

    def track_progress(self) -> dict[str, Any]:
        """Return count of active, completed, and failed tasks."""
        return {
            "active": len(self._active),
            "active_ids": list(self._active.keys()),
            "dispatched": self._dispatched,
            "succeeded": self._succeeded,
            "failed": self._failed,
        }

    def check_results(
        self,
        agent: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[TaskResult]:
        """Return recent task results, optionally filtered."""
        results = self._history[-500:]
        if agent:
            results = [r for r in results if r.agent == agent]
        if status:
            results = [r for r in results if r.status == status]
        return results[-limit:]

    def report_status(self) -> OrchestratorStatus:
        return OrchestratorStatus(
            agents_registered=len(self._agents),
            tasks_dispatched=self._dispatched,
            tasks_succeeded=self._succeeded,
            tasks_failed=self._failed,
            active_task_ids=list(self._active.keys()),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record(self, task: dict, result: TaskResult) -> None:
        self._history.append(result)
        if len(self._history) > 500:
            self._history = self._history[-500:]
