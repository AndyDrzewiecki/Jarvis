"""DesignSession — interactive design-to-build CLI for Project Forge.

Supports three modes:
  1. BRAINSTORM  — user describes an idea; Jarvis asks clarifying questions
                   and expands it into a structured spec
  2. PLAN        — spec is converted into a phased roadmap (phases → tasks)
  3. EXECUTE     — roadmap tasks are dispatched autonomously to Forge agents
                   via the ForgeOrchestrator; progress tracked until completion

CLI entry point::

    python -m jarvis.forge.design_session

Or via API::

    session = DesignSession()
    spec = session.brainstorm("I want to build a meal planner")
    roadmap = session.plan(spec)
    results = session.execute(roadmap)
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.forge.memory_store import ForgeMemoryStore
from jarvis.forge.ollama_gateway import forge_generate

logger = logging.getLogger(__name__)

_BRAINSTORM_PROMPT = """\
You are Jarvis, a household AI assistant helping the user design a software project.

User idea: {idea}

Ask 3-5 targeted clarifying questions to understand:
1. The primary user and their pain point
2. Key features (must-have vs. nice-to-have)
3. Technical constraints (language, platform, integrations)
4. Success criteria

Format each question on its own line starting with "Q: ".
"""

_SPEC_PROMPT = """\
You are a software architect. Given this idea and the user's answers to clarifying questions,
write a concise project specification.

Idea: {idea}
Q&A: {qa}

Respond in this JSON format:
{{
  "project_name": "...",
  "summary": "one sentence",
  "user": "primary user description",
  "must_have": ["feature 1", "feature 2"],
  "nice_to_have": ["feature A"],
  "tech_stack": ["Python", "FastAPI"],
  "success_criteria": ["criterion 1"],
  "estimated_complexity": "low|medium|high"
}}
"""

_ROADMAP_PROMPT = """\
You are a software architect creating an implementation roadmap.

Project spec:
{spec_json}

Create a phased roadmap. Each phase has tasks that can be executed by a dev agent.
Respond in this JSON format:
{{
  "phases": [
    {{
      "phase": 1,
      "name": "Foundation",
      "description": "...",
      "tasks": [
        {{
          "id": "task-001",
          "title": "Set up project structure",
          "type": "code",
          "agent": "code_auditor",
          "description": "...",
          "acceptance_criteria": "..."
        }}
      ]
    }}
  ]
}}

Task types: code | test | docs | config | review
Agent choices: code_auditor | pattern_analyst | tester | trainer | critic
Keep phases small (2-4 tasks each). Max 5 phases for medium complexity projects.
"""

_TASK_EXEC_PROMPT = """\
You are a senior developer executing a software task autonomously.

Project: {project_name}
Phase {phase}: {phase_name}
Task: {title}
Description: {description}
Acceptance criteria: {acceptance_criteria}

Prior context (completed tasks):
{prior_context}

Execute this task. Provide:
1. A brief plan (2-3 bullet points)
2. The implementation or artifact
3. How to verify this meets the acceptance criteria

Be concrete and complete.
"""


@dataclass
class ProjectSpec:
    """Structured project specification from brainstorm."""
    session_id: str
    project_name: str
    summary: str
    user: str
    must_have: list[str]
    nice_to_have: list[str]
    tech_stack: list[str]
    success_criteria: list[str]
    estimated_complexity: str
    raw_idea: str
    qa_pairs: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class RoadmapTask:
    """One autonomous task in the roadmap."""
    id: str
    phase: int
    phase_name: str
    title: str
    type: str
    agent: str
    description: str
    acceptance_criteria: str
    status: str = "pending"   # pending | running | done | failed
    output: str = ""
    error: str = ""


@dataclass
class Roadmap:
    """Full phased roadmap for a project."""
    session_id: str
    project_name: str
    phases: list[dict]
    tasks: list[RoadmapTask]
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ExecutionResult:
    """Result of executing an entire roadmap."""
    session_id: str
    project_name: str
    total_tasks: int
    completed: int
    failed: int
    task_results: list[RoadmapTask]
    duration_ms: int


class DesignSession:
    """Interactive design-to-build pipeline.

    Lifecycle::

        session = DesignSession()

        # Step 1: brainstorm — returns spec
        spec = session.brainstorm("I want a meal planner")
        # (Optionally feed in answers interactively)

        # Step 2: plan — converts spec to roadmap
        roadmap = session.plan(spec)

        # Step 3: execute — dispatches tasks autonomously
        result = session.execute(roadmap)
    """

    def __init__(
        self,
        memory_store: ForgeMemoryStore | None = None,
        orchestrator: Any | None = None,
    ):
        self._store = memory_store or ForgeMemoryStore()
        self._orchestrator = orchestrator
        self._session_id = str(uuid.uuid4())
        self._history: list[dict] = []

    # ------------------------------------------------------------------
    # Step 1: Brainstorm
    # ------------------------------------------------------------------

    def brainstorm(
        self,
        idea: str,
        answers: list[str] | None = None,
    ) -> ProjectSpec:
        """Expand a raw idea into a structured ProjectSpec.

        Args:
            idea:    User's initial project idea (free text).
            answers: Answers to clarifying questions. If None, questions are
                     printed to stdout and read from stdin (interactive mode).

        Returns:
            ProjectSpec — structured project definition.
        """
        # Generate clarifying questions
        questions_prompt = _BRAINSTORM_PROMPT.format(idea=idea)
        raw_questions = forge_generate(questions_prompt, agent="orchestrator")
        questions = [
            line[2:].strip()
            for line in raw_questions.splitlines()
            if line.startswith("Q:")
        ]

        qa_pairs: list[tuple[str, str]] = []
        if answers is None:
            # Interactive mode
            print("\nJarvis: I have some clarifying questions:\n")
            for i, q in enumerate(questions, 1):
                print(f"  {i}. {q}")
                try:
                    ans = input(f"\nYour answer: ").strip()
                except EOFError:
                    ans = "(no answer)"
                qa_pairs.append((q, ans))
        else:
            for q, a in zip(questions, answers):
                qa_pairs.append((q, a))

        # Build spec from idea + Q&A
        qa_text = "\n".join(f"Q: {q}\nA: {a}" for q, a in qa_pairs)
        spec_prompt = _SPEC_PROMPT.format(idea=idea, qa=qa_text)
        raw_spec = forge_generate(spec_prompt, agent="orchestrator")

        spec = self._parse_spec(raw_spec, idea, qa_pairs)

        self._history.append({
            "step": "brainstorm",
            "idea": idea,
            "qa_pairs": [{"q": q, "a": a} for q, a in qa_pairs],
            "spec": spec.project_name,
        })

        logger.info("DesignSession brainstorm: project='%s' complexity=%s",
                    spec.project_name, spec.estimated_complexity)
        return spec

    # ------------------------------------------------------------------
    # Step 2: Plan
    # ------------------------------------------------------------------

    def plan(self, spec: ProjectSpec) -> Roadmap:
        """Convert a ProjectSpec into a phased Roadmap.

        Args:
            spec: Output of brainstorm().

        Returns:
            Roadmap with phases and tasks.
        """
        spec_json = json.dumps({
            "project_name": spec.project_name,
            "summary": spec.summary,
            "must_have": spec.must_have,
            "tech_stack": spec.tech_stack,
            "estimated_complexity": spec.estimated_complexity,
        }, indent=2)

        roadmap_prompt = _ROADMAP_PROMPT.format(spec_json=spec_json)
        raw_roadmap = forge_generate(roadmap_prompt, agent="orchestrator")

        roadmap = self._parse_roadmap(raw_roadmap, spec)

        self._history.append({
            "step": "plan",
            "project": spec.project_name,
            "phases": len(roadmap.phases),
            "tasks": len(roadmap.tasks),
        })

        logger.info("DesignSession plan: project='%s' phases=%d tasks=%d",
                    spec.project_name, len(roadmap.phases), len(roadmap.tasks))
        return roadmap

    # ------------------------------------------------------------------
    # Step 3: Execute
    # ------------------------------------------------------------------

    def execute(self, roadmap: Roadmap, dry_run: bool = False) -> ExecutionResult:
        """Autonomously execute all tasks in the roadmap.

        Args:
            roadmap: Output of plan().
            dry_run: If True, simulate execution without calling LLM.

        Returns:
            ExecutionResult with per-task outcomes.
        """
        import time
        start = time.monotonic()

        completed = 0
        failed = 0
        prior_outputs: list[str] = []

        for task in roadmap.tasks:
            task.status = "running"
            logger.info("DesignSession execute: task %s — %s", task.id, task.title)

            if dry_run:
                task.output = f"[DRY RUN] Would execute: {task.title}"
                task.status = "done"
                completed += 1
                prior_outputs.append(f"[{task.id}] {task.title}: completed")
                continue

            # Build context from prior completed tasks
            prior_context = "\n".join(prior_outputs[-5:]) if prior_outputs else "None"

            exec_prompt = _TASK_EXEC_PROMPT.format(
                project_name=roadmap.project_name,
                phase=task.phase,
                phase_name=task.phase_name,
                title=task.title,
                description=task.description,
                acceptance_criteria=task.acceptance_criteria,
                prior_context=prior_context,
            )

            try:
                if self._orchestrator:
                    # Dispatch through registered orchestrator
                    result = self._orchestrator.dispatch({
                        "type": task.type,
                        "target": task.agent,
                        "payload": {
                            "task_id": task.id,
                            "title": task.title,
                            "prompt": exec_prompt,
                        },
                    })
                    task.output = result.output
                    task.status = "done" if result.status == "success" else "failed"
                else:
                    # Direct LLM execution
                    task.output = forge_generate(exec_prompt, agent=task.agent)
                    task.status = "done"
            except Exception as exc:
                task.error = str(exc)
                task.status = "failed"
                logger.warning("DesignSession: task %s failed: %s", task.id, exc)

            if task.status == "done":
                completed += 1
                prior_outputs.append(f"[{task.id}] {task.title}: {task.output[:100]}")
            else:
                failed += 1

            # Write to forge memory
            self._store.log_interaction(
                agent="design_session",
                task_id=task.id,
                input_text=f"{roadmap.project_name}:{task.title}",
                output_text=task.output[:500] or task.error,
                model="orchestrated",
            )

        duration_ms = int((time.monotonic() - start) * 1000)

        self._history.append({
            "step": "execute",
            "project": roadmap.project_name,
            "completed": completed,
            "failed": failed,
        })

        result = ExecutionResult(
            session_id=roadmap.session_id,
            project_name=roadmap.project_name,
            total_tasks=len(roadmap.tasks),
            completed=completed,
            failed=failed,
            task_results=roadmap.tasks,
            duration_ms=duration_ms,
        )
        logger.info(
            "DesignSession execute DONE: project='%s' completed=%d failed=%d %.1fs",
            roadmap.project_name, completed, failed, duration_ms / 1000,
        )
        return result

    def get_history(self) -> list[dict]:
        """Return session step history."""
        return list(self._history)

    def print_roadmap(self, roadmap: Roadmap) -> None:
        """Print a human-readable roadmap summary."""
        print(f"\n{'='*60}")
        print(f"ROADMAP: {roadmap.project_name}")
        print(f"{'='*60}")
        current_phase = None
        for task in roadmap.tasks:
            if task.phase != current_phase:
                current_phase = task.phase
                print(f"\nPhase {task.phase}: {task.phase_name}")
                print("-" * 40)
            icon = {"pending": "○", "running": "→", "done": "✓", "failed": "✗"}.get(task.status, "?")
            print(f"  {icon} [{task.id}] {task.title}")
            if task.status in ("done", "failed") and task.output:
                print(f"      → {task.output[:80]}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_spec(
        self, raw: str, idea: str, qa_pairs: list[tuple[str, str]]
    ) -> ProjectSpec:
        try:
            # Extract JSON block from response
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            data = json.loads(raw[json_start:json_end])
        except (json.JSONDecodeError, ValueError):
            data = {}

        return ProjectSpec(
            session_id=self._session_id,
            project_name=data.get("project_name", "Unnamed Project"),
            summary=data.get("summary", idea[:100]),
            user=data.get("user", "Andy"),
            must_have=data.get("must_have", []),
            nice_to_have=data.get("nice_to_have", []),
            tech_stack=data.get("tech_stack", ["Python"]),
            success_criteria=data.get("success_criteria", []),
            estimated_complexity=data.get("estimated_complexity", "medium"),
            raw_idea=idea,
            qa_pairs=qa_pairs,
        )

    def _parse_roadmap(self, raw: str, spec: ProjectSpec) -> Roadmap:
        try:
            json_start = raw.find("{")
            json_end = raw.rfind("}") + 1
            data = json.loads(raw[json_start:json_end])
        except (json.JSONDecodeError, ValueError):
            data = {"phases": []}

        tasks: list[RoadmapTask] = []
        phases = data.get("phases", [])
        for phase_data in phases:
            phase_num = phase_data.get("phase", 1)
            phase_name = phase_data.get("name", f"Phase {phase_num}")
            for t in phase_data.get("tasks", []):
                tasks.append(RoadmapTask(
                    id=t.get("id", str(uuid.uuid4())[:8]),
                    phase=phase_num,
                    phase_name=phase_name,
                    title=t.get("title", "Unnamed Task"),
                    type=t.get("type", "code"),
                    agent=t.get("agent", "code_auditor"),
                    description=t.get("description", ""),
                    acceptance_criteria=t.get("acceptance_criteria", ""),
                ))

        return Roadmap(
            session_id=self._session_id,
            project_name=spec.project_name,
            phases=phases,
            tasks=tasks,
        )


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def _cli_main() -> None:
    """Interactive design session CLI."""
    logging.basicConfig(level=logging.WARNING)
    print("\nJarvis Project Forge — Design Session")
    print("=" * 40)
    print("Type your project idea and press Enter.\n")

    try:
        idea = input("Your idea: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if not idea:
        print("No idea provided. Exiting.")
        sys.exit(0)

    session = DesignSession()

    print("\n[BRAINSTORM] Expanding your idea...\n")
    spec = session.brainstorm(idea)

    print(f"\n[SPEC] Project: {spec.project_name}")
    print(f"       Summary: {spec.summary}")
    print(f"       Complexity: {spec.estimated_complexity}")
    print(f"       Must-haves: {', '.join(spec.must_have[:3])}")

    try:
        proceed = input("\n[PLAN] Generate roadmap? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if proceed in ("n", "no"):
        print("Done — spec saved.")
        sys.exit(0)

    print("\n[PLAN] Building roadmap...\n")
    roadmap = session.plan(spec)
    session.print_roadmap(roadmap)

    try:
        proceed = input("\n[EXECUTE] Run autonomously? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if proceed not in ("y", "yes"):
        print("Done — roadmap saved.")
        sys.exit(0)

    print("\n[EXECUTE] Running tasks...\n")
    result = session.execute(roadmap)

    print(f"\n{'='*60}")
    print(f"EXECUTION COMPLETE: {result.project_name}")
    print(f"  Tasks: {result.total_tasks} total, {result.completed} done, {result.failed} failed")
    print(f"  Duration: {result.duration_ms/1000:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    _cli_main()
