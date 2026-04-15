"""Critic — Brain 1 of Project Forge.

Continuously monitors agent output quality, catches hallucinations, and writes
verdicts to shared memory. Verdicts are consumed by the Pattern Analyst (Brain 2).

Verdict schema:
    {
      "interaction_id": str,
      "agent":         str,
      "quality":       "good" | "acceptable" | "poor",
      "score":         float (0.0 – 1.0),
      "flags":         list[str],   # e.g. ["hallucination", "off_topic"]
      "reasoning":     str,
      "hallucination_ids": list[str],  # IDs written to hallucinations table
    }
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from jarvis.forge.agent_base import BaseDevAgent, TaskResult
from jarvis.forge.memory_store import ForgeMemoryStore

logger = logging.getLogger(__name__)

_QUALITY_PROMPT = """\
You are a strict quality critic reviewing AI agent output.

Agent: {agent}
Task type: {task_type}
Input: {input_text}
Output: {output_text}

Evaluate this output and respond in EXACTLY this format (no extra text):
QUALITY: good|acceptable|poor
SCORE: 0.0-1.0
FLAGS: comma-separated list of issues (or NONE)
REASONING: one concise sentence

Definitions:
- good (0.7-1.0): accurate, relevant, complete, no hallucinations
- acceptable (0.4-0.69): mostly correct but minor gaps or imprecision
- poor (0.0-0.39): wrong, hallucinated, incomplete, or harmful
Possible flags: hallucination, off_topic, incomplete, unsafe, low_confidence, verbose, wrong_format
"""


@dataclass
class Verdict:
    """The Critic's judgment on a single agent output."""
    interaction_id: str
    agent: str
    quality: str
    score: float
    flags: list[str]
    reasoning: str
    hallucination_ids: list[str] = field(default_factory=list)


class Critic(BaseDevAgent):
    """Brain 1 — quality monitor for Project Forge agents.

    Usage::

        critic = Critic()
        verdict = critic.evaluate(
            interaction_id="abc123",
            agent="code_auditor",
            task_type="code_review",
            input_text="Review this PR...",
            output_text="Looks fine.",
        )
        print(verdict.quality, verdict.flags)
    """

    name = "critic"
    model = "qwen2.5:0.5b"  # lightweight 12B-class model for fast evaluation

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        super().__init__(memory_store)
        self._verdicts_written = 0

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def evaluate(
        self,
        interaction_id: str,
        agent: str,
        task_type: str,
        input_text: str,
        output_text: str,
    ) -> Verdict:
        """Evaluate a single agent output. Writes verdict + any hallucinations to memory."""
        prompt = _QUALITY_PROMPT.format(
            agent=agent,
            task_type=task_type,
            input_text=input_text[:800],
            output_text=output_text[:1200],
        )

        raw_verdict = self._call_llm(prompt)
        verdict = self._parse_verdict(raw_verdict, interaction_id, agent)

        # Persist hallucinations to Layer 4
        hallucination_ids: list[str] = []
        if "hallucination" in verdict.flags:
            hid = self._store.log_hallucination(
                agent=agent,
                claim=output_text[:500],
                interaction_id=interaction_id,
                evidence_against=verdict.reasoning,
                severity="high" if verdict.score < 0.2 else "medium",
            )
            hallucination_ids.append(hid)

        verdict.hallucination_ids = hallucination_ids
        self._verdicts_written += 1

        # Log the critic's own interaction in Layer 1
        self._store.log_interaction(
            agent=self.name,
            task_id=interaction_id,
            input_text=f"evaluate:{agent}:{task_type}",
            output_text=f"quality={verdict.quality} score={verdict.score} flags={verdict.flags}",
            model=self.model,
        )

        # Update skill tracking: how many hallucinations caught, accuracy
        if verdict.quality == "good":
            self.update_skill("accuracy_assessment", min(1.0, self._verdicts_written / 10))

        logger.info(
            "Critic verdict: agent=%s quality=%s score=%.2f flags=%s",
            agent, verdict.quality, verdict.score, verdict.flags,
        )
        return verdict

    def evaluate_batch(self, interactions: list[dict]) -> list[Verdict]:
        """Evaluate a batch of interaction dicts (each with keys matching evaluate() args)."""
        return [self.evaluate(**item) for item in interactions]

    # ------------------------------------------------------------------
    # BaseDevAgent interface
    # ------------------------------------------------------------------

    def execute_task(self, task: dict) -> TaskResult:
        """Task format: {"type": "evaluate", "payload": {interaction fields}}"""
        payload = task.get("payload", {})
        task_type = task.get("type", "evaluate")

        if task_type == "evaluate":
            verdict = self.evaluate(
                interaction_id=payload.get("interaction_id", task["id"]),
                agent=payload.get("agent", "unknown"),
                task_type=payload.get("task_type", "unknown"),
                input_text=payload.get("input_text", ""),
                output_text=payload.get("output_text", ""),
            )
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"quality={verdict.quality} score={verdict.score:.2f}",
                confidence=verdict.score,
                metadata={"verdict": {
                    "quality": verdict.quality,
                    "score": verdict.score,
                    "flags": verdict.flags,
                    "reasoning": verdict.reasoning,
                }},
            )

        return TaskResult(
            task_id=task["id"],
            agent=self.name,
            status="failure",
            output="",
            error=f"Unknown task type: {task_type}",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call_llm(self, prompt: str) -> str:
        try:
            from jarvis.core import _ask_ollama, FALLBACK_MODEL
            return _ask_ollama(prompt, model=FALLBACK_MODEL)
        except Exception as exc:
            logger.warning("Critic LLM call failed: %s", exc)
            return "QUALITY: acceptable\nSCORE: 0.5\nFLAGS: NONE\nREASONING: LLM unavailable, default verdict."

    def _parse_verdict(self, raw: str, interaction_id: str, agent: str) -> Verdict:
        lines = {
            k.strip(): v.strip()
            for line in raw.splitlines()
            if ":" in line
            for k, v in [line.split(":", 1)]
        }

        quality_raw = lines.get("QUALITY", "acceptable").strip().lower()
        quality = quality_raw if quality_raw in {"good", "acceptable", "poor"} else "acceptable"

        try:
            score = float(lines.get("SCORE", "0.5"))
            score = max(0.0, min(1.0, score))
        except ValueError:
            score = 0.5

        flags_raw = lines.get("FLAGS", "NONE")
        flags = (
            []
            if flags_raw.upper() == "NONE"
            else [f.strip().lower() for f in flags_raw.split(",") if f.strip()]
        )

        reasoning = lines.get("REASONING", "No reasoning provided.")

        return Verdict(
            interaction_id=interaction_id,
            agent=agent,
            quality=quality,
            score=score,
            flags=flags,
            reasoning=reasoning,
        )
