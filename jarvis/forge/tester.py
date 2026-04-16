"""AgentTester — Brain 3 of Project Forge.

Picks up staged fix proposals from the prompt_versions table, runs sandboxed A/B
comparisons between the current prompt and the staged fix, then promotes or discards.

A/B test methodology:
  - Take N recent inputs for the target agent
  - Run each input through both prompts (current vs. staged)
  - Ask the Critic (Brain 1) to score both outputs
  - If staged version scores ≥ PROMOTION_THRESHOLD better → promote
  - Otherwise discard with a recorded reason

Promotion writes the new prompt as the current version (removing [STAGED FIX] tag).
Discard leaves the current prompt unchanged but records the failure reason.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.forge.agent_base import BaseDevAgent, TaskResult
from jarvis.forge.memory_store import ForgeMemoryStore, _open as _db_open
from jarvis.forge.ollama_gateway import forge_generate

logger = logging.getLogger(__name__)

# Minimum score improvement for promotion (absolute difference on 0-1 scale)
PROMOTION_THRESHOLD = float(__import__("os").getenv("FORGE_PROMOTION_THRESHOLD", "0.05"))

_SCORE_PROMPT = """\
You are scoring two AI agent responses for the same input.

Input: {input_text}

Response A (current):
{response_a}

Response B (candidate):
{response_b}

Score each on a 0.0-1.0 scale for: accuracy, completeness, conciseness.
Respond in EXACTLY this format:
SCORE_A: 0.0-1.0
SCORE_B: 0.0-1.0
WINNER: A|B|TIE
REASON: one sentence
"""


@dataclass
class ABResult:
    """Result of one A/B comparison run."""
    input_text: str
    score_a: float
    score_b: float
    winner: str       # A | B | TIE
    reason: str


@dataclass
class TestReport:
    """Summary of a full A/B test cycle for one staged fix."""
    agent: str
    prompt_version_id: int
    runs: int
    mean_score_a: float
    mean_score_b: float
    improvement: float
    decision: str   # promoted | discarded
    reason: str
    ab_results: list[ABResult] = field(default_factory=list)


class AgentTester(BaseDevAgent):
    """Brain 3 — A/B tests staged prompt fixes and promotes or discards them.

    Usage::

        tester = AgentTester()
        # Test a specific staged prompt version
        report = tester.test_staged(agent="critic", prompt_version_id=3, n_runs=5)
        print(report.decision, report.improvement)

        # Auto-discover and test all staged proposals
        reports = tester.test_all_staged(n_runs=5)
    """

    name = "tester"
    model = "qwen2.5:0.5b"

    STAGED_MARKER = "[STAGED FIX]"

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        super().__init__(memory_store)
        self._test_reports: list[TestReport] = []

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def test_staged(
        self,
        agent: str,
        prompt_version_id: int | None = None,
        n_runs: int = 5,
    ) -> TestReport | None:
        """A/B test the most recent staged version for agent.

        If prompt_version_id is None, finds the latest staged version automatically.
        Returns None if no staged version exists.
        """
        # Find the staged prompt
        staged = self._find_staged(agent, prompt_version_id)
        if not staged:
            logger.info("AgentTester: no staged version found for agent=%s", agent)
            return None

        staged_id = staged.get("version", 0)
        staged_text = staged.get("prompt_text", "")
        current_text = self._current_prompt_text(agent, exclude_version=staged_id)

        # Gather recent inputs as test cases
        inputs = self._gather_test_inputs(agent, limit=max(n_runs, 10))
        if not inputs:
            logger.info("AgentTester: no test inputs available for agent=%s", agent)
            return None

        # Run A/B pairs
        ab_results: list[ABResult] = []
        for inp in inputs[:n_runs]:
            result = self._run_ab(inp, current_text, staged_text, agent)
            if result:
                ab_results.append(result)

        if not ab_results:
            return None

        # Aggregate scores
        mean_a = sum(r.score_a for r in ab_results) / len(ab_results)
        mean_b = sum(r.score_b for r in ab_results) / len(ab_results)
        improvement = mean_b - mean_a

        # Decision
        if improvement >= PROMOTION_THRESHOLD:
            decision = "promoted"
            reason = f"Score improved by {improvement:.3f} (A={mean_a:.3f} → B={mean_b:.3f})"
            self._promote(agent, staged_text, staged_id)
        else:
            decision = "discarded"
            reason = f"Insufficient improvement {improvement:.3f} < {PROMOTION_THRESHOLD}"

        report = TestReport(
            agent=agent,
            prompt_version_id=staged_id,
            runs=len(ab_results),
            mean_score_a=round(mean_a, 3),
            mean_score_b=round(mean_b, 3),
            improvement=round(improvement, 3),
            decision=decision,
            reason=reason,
            ab_results=ab_results,
        )
        self._test_reports.append(report)

        # Log meta-pattern for the decision
        try:
            self._store.log_meta_pattern(
                pattern=f"AB test {decision}: agent={agent} improvement={improvement:.3f}",
                source_layers=[2, 6],
                impact="high" if decision == "promoted" else "low",
                action_taken=decision,
            )
        except Exception:
            pass

        logger.info(
            "AgentTester: agent=%s v%s %s (Δ=%.3f)",
            agent, staged_id, decision, improvement,
        )
        return report

    def test_all_staged(self, n_runs: int = 5) -> list[TestReport]:
        """Find all agents with staged proposals and test them."""
        # Scan prompt_versions for staged markers
        try:
            conn = _db_open(self._store._db)
            rows = conn.execute(
                "SELECT DISTINCT agent FROM prompt_versions WHERE prompt_text LIKE ?",
                (f"%{self.STAGED_MARKER}%",),
            ).fetchall()
            conn.close()
            agents = [r[0] for r in rows]
        except Exception as exc:
            logger.warning("AgentTester.test_all_staged: DB error %s", exc)
            return []

        reports = []
        for agent in agents:
            report = self.test_staged(agent, n_runs=n_runs)
            if report:
                reports.append(report)
        return reports

    def get_reports(self) -> list[TestReport]:
        return list(self._test_reports)

    # ------------------------------------------------------------------
    # BaseDevAgent interface
    # ------------------------------------------------------------------

    def execute_task(self, task: dict) -> TaskResult:
        payload = task.get("payload", {})
        task_type = task.get("type", "test_staged")

        if task_type == "test_staged":
            agent = payload.get("agent", "")
            if not agent:
                return TaskResult(
                    task_id=task["id"], agent=self.name,
                    status="failure", output="", error="Missing 'agent' in payload",
                )
            report = self.test_staged(
                agent=agent,
                prompt_version_id=payload.get("prompt_version_id"),
                n_runs=payload.get("n_runs", 5),
            )
            if report is None:
                return TaskResult(
                    task_id=task["id"], agent=self.name,
                    status="success", output="no_staged_version", confidence=0.5,
                )
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"decision={report.decision} improvement={report.improvement:.3f}",
                confidence=0.9 if report.decision == "promoted" else 0.6,
                metadata={
                    "decision": report.decision,
                    "improvement": report.improvement,
                    "runs": report.runs,
                    "reason": report.reason,
                },
            )

        if task_type == "test_all":
            reports = self.test_all_staged(n_runs=payload.get("n_runs", 5))
            promoted = sum(1 for r in reports if r.decision == "promoted")
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"tested={len(reports)} promoted={promoted}",
                confidence=0.8,
            )

        return TaskResult(
            task_id=task["id"], agent=self.name,
            status="failure", output="", error=f"Unknown task type: {task_type}",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_staged(self, agent: str, version_id: int | None) -> dict | None:
        try:
            conn = _db_open(self._store._db)
            if version_id is not None:
                row = conn.execute(
                    "SELECT * FROM prompt_versions WHERE agent = ? AND version = ?",
                    (agent, version_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM prompt_versions WHERE agent = ? AND prompt_text LIKE ?"
                    " ORDER BY version DESC LIMIT 1",
                    (agent, f"%{self.STAGED_MARKER}%"),
                ).fetchone()
            conn.close()
            return dict(row) if row else None
        except Exception as exc:
            logger.warning("AgentTester._find_staged error: %s", exc)
            return None

    def _current_prompt_text(self, agent: str, exclude_version: int | None = None) -> str:
        try:
            if exclude_version is not None:
                conn = _db_open(self._store._db)
                row = conn.execute(
                    "SELECT prompt_text FROM prompt_versions"
                    " WHERE agent = ? AND version != ? AND prompt_text NOT LIKE ?"
                    " ORDER BY version DESC LIMIT 1",
                    (agent, exclude_version, f"%{self.STAGED_MARKER}%"),
                ).fetchone()
                conn.close()
                return row[0] if row else ""
            else:
                current = self._store.get_current_prompt(agent)
                return current.get("prompt_text", "") if current else ""
        except Exception:
            return ""

    def _gather_test_inputs(self, agent: str, limit: int = 10) -> list[str]:
        interactions = self._store.query_interactions(agent=agent, limit=limit)
        return [ix.get("input_text", "") for ix in interactions if ix.get("input_text")]

    def _run_ab(
        self, input_text: str, prompt_a: str, prompt_b: str, agent: str
    ) -> ABResult | None:
        try:
            response_a = forge_generate(
                prompt=input_text,
                agent=agent,
                system=prompt_a or None,
            )
            response_b = forge_generate(
                prompt=input_text,
                agent=agent,
                system=self._strip_staged_marker(prompt_b),
            )
        except Exception as exc:
            logger.warning("AgentTester._run_ab generation error: %s", exc)
            return None

        score_prompt = _SCORE_PROMPT.format(
            input_text=input_text[:300],
            response_a=response_a[:400],
            response_b=response_b[:400],
        )
        try:
            raw = forge_generate(score_prompt, agent=self.name)
            return self._parse_ab(raw, input_text)
        except Exception as exc:
            logger.warning("AgentTester._run_ab scoring error: %s", exc)
            return None

    def _parse_ab(self, raw: str, input_text: str) -> ABResult:
        lines: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                lines[k.strip().upper()] = v.strip()

        def _safe_float(key: str, default: float = 0.5) -> float:
            try:
                return max(0.0, min(1.0, float(lines.get(key, default))))
            except ValueError:
                return default

        score_a = _safe_float("SCORE_A")
        score_b = _safe_float("SCORE_B")
        winner_raw = lines.get("WINNER", "TIE").strip().upper()
        winner = winner_raw if winner_raw in {"A", "B", "TIE"} else "TIE"
        reason = lines.get("REASON", "")
        return ABResult(input_text=input_text, score_a=score_a, score_b=score_b, winner=winner, reason=reason)

    def _promote(self, agent: str, staged_text: str, staged_version: int) -> None:
        """Write staged text (without the marker) as new canonical prompt."""
        clean_text = self._strip_staged_marker(staged_text)
        try:
            self._store.save_prompt_version(
                agent=agent,
                prompt_text=clean_text,
                change_reason=f"Promoted from staged v{staged_version} by AgentTester",
                changed_by="tester",
                delta_summary="A/B test passed — prompt promoted",
            )
        except Exception as exc:
            logger.warning("AgentTester._promote error: %s", exc)

    def _strip_staged_marker(self, text: str) -> str:
        if self.STAGED_MARKER in text:
            return text.split(self.STAGED_MARKER)[0].strip()
        return text

