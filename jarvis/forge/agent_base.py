"""BaseDevAgent — common interface for all Project Forge dev agents.

Every agent (Critic, Pattern Analyst, Tester, Code Auditor) inherits from this.
Key contract:
  - read_memory()   — fetch relevant context before acting
  - write_memory()  — persist results after acting
  - execute_task()  — do the work (subclasses implement)
  - report_status() — return current agent state
"""
from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.forge.memory_store import ForgeMemoryStore

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TaskResult:
    """Structured result from execute_task()."""
    task_id: str
    agent: str
    status: str           # success | failure | partial
    output: str
    confidence: float = 0.5
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)
    error: str | None = None


@dataclass
class AgentStatus:
    """Current state of a dev agent."""
    agent: str
    model: str
    tasks_completed: int
    tasks_failed: int
    avg_confidence: float
    top_skills: list[dict]
    last_active: str | None


class BaseDevAgent(ABC):
    """Abstract base for all Project Forge dev agents.

    Subclasses must implement:
        execute_task(task: dict) -> TaskResult

    They should call read_memory() before acting and write_memory() after.
    """

    #: Override in subclasses — used for memory keys and logging
    name: str = "base_agent"
    #: Ollama model this agent runs on
    model: str = "qwen2.5:0.5b"

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        self._store = memory_store or ForgeMemoryStore()
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._confidence_sum = 0.0

    # ------------------------------------------------------------------
    # Memory interface
    # ------------------------------------------------------------------

    def read_memory(
        self,
        context: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Fetch relevant context from shared memory before acting.

        Returns a dict with keys: recent_interactions, skills, routing_history.
        Optionally filters by context (task_id).
        """
        result: dict[str, Any] = {}
        try:
            result["recent_interactions"] = self._store.query_interactions(
                agent=self.name, task_id=context, limit=limit
            )
        except Exception as exc:
            logger.warning("%s.read_memory interactions error: %s", self.name, exc)
            result["recent_interactions"] = []

        try:
            result["skills"] = self._store.get_skills(self.name)
        except Exception as exc:
            logger.warning("%s.read_memory skills error: %s", self.name, exc)
            result["skills"] = []

        try:
            result["routing_history"] = self._store.query_routing(agent=self.name, limit=limit)
        except Exception as exc:
            logger.warning("%s.read_memory routing error: %s", self.name, exc)
            result["routing_history"] = []

        return result

    def write_memory(self, result: TaskResult) -> None:
        """Persist task result to shared memory after acting."""
        try:
            self._store.log_interaction(
                agent=self.name,
                task_id=result.task_id,
                input_text=result.metadata.get("input", ""),
                output_text=result.output,
                model=self.model,
                duration_ms=result.duration_ms,
            )
        except Exception as exc:
            logger.warning("%s.write_memory error: %s", self.name, exc)

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    @abstractmethod
    def execute_task(self, task: dict) -> TaskResult:
        """Execute a task. Subclasses must implement.

        Args:
            task: dict with at minimum {"id": str, "type": str, "payload": Any}

        Returns:
            TaskResult
        """

    def run(self, task: dict) -> TaskResult:
        """Full agent lifecycle: read → execute → write → return.

        Handles timing, error catching, and memory persistence automatically.
        """
        task_id = task.get("id") or str(uuid.uuid4())
        task["id"] = task_id

        logger.info("%s starting task %s (type=%s)", self.name, task_id, task.get("type", "?"))
        start = time.monotonic()

        # Read memory context before acting
        context = self.read_memory(context=task_id)
        task["_memory_context"] = context

        try:
            result = self.execute_task(task)
        except Exception as exc:
            logger.exception("%s task %s failed", self.name, task_id)
            elapsed = int((time.monotonic() - start) * 1000)
            result = TaskResult(
                task_id=task_id,
                agent=self.name,
                status="failure",
                output="",
                duration_ms=elapsed,
                error=str(exc),
            )

        result.duration_ms = int((time.monotonic() - start) * 1000)
        result.task_id = task_id
        result.agent = self.name

        # Write memory after acting
        self.write_memory(result)

        # Update stats
        if result.status == "success":
            self._tasks_completed += 1
        else:
            self._tasks_failed += 1
        self._confidence_sum += result.confidence

        return result

    # ------------------------------------------------------------------
    # Status reporting
    # ------------------------------------------------------------------

    def report_status(self) -> AgentStatus:
        """Return current agent state, including skill levels."""
        total = self._tasks_completed + self._tasks_failed
        avg_conf = (self._confidence_sum / total) if total > 0 else 0.0

        skills = []
        try:
            raw = self._store.get_skills(self.name)
            skills = sorted(raw, key=lambda s: s.get("score", 0), reverse=True)[:5]
        except Exception:
            pass

        last_active = None
        try:
            recent = self._store.query_interactions(agent=self.name, limit=1)
            if recent:
                last_active = recent[0].get("ts")
        except Exception:
            pass

        return AgentStatus(
            agent=self.name,
            model=self.model,
            tasks_completed=self._tasks_completed,
            tasks_failed=self._tasks_failed,
            avg_confidence=round(avg_conf, 3),
            top_skills=skills,
            last_active=last_active,
        )

    def update_skill(self, skill_name: str, score: float, evidence: str | None = None) -> None:
        """Convenience: update this agent's skill level in shared memory."""
        try:
            self._store.update_skill(self.name, skill_name, score, evidence)
        except Exception as exc:
            logger.warning("%s.update_skill error: %s", self.name, exc)
