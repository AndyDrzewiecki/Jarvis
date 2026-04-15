"""AgentTrainer — reviews completed work, grades quality, writes improved guidelines back.

The Trainer closes the self-improvement loop:
  1. Read completed task interactions from ForgeMemoryStore
  2. Grade quality using the same 0.0–1.0 scale as DecisionGrader
  3. Identify patterns in good/poor outputs
  4. Write improved prompts (new prompt_versions) back to shared memory
  5. Update agent skill scores

This is called by the orchestrator or on a schedule (e.g., nightly).

Training pair export:
  The Trainer can also export Layer 3 correction pairs in ShareGPT / DPO format
  for downstream LoRA fine-tuning when Tier 3 self-modification is triggered.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from jarvis.forge.memory_store import ForgeMemoryStore

logger = logging.getLogger(__name__)

_REVIEW_PROMPT = """\
You are reviewing a batch of AI agent outputs to improve future performance.

Agent: {agent}
Batch size: {n}

Sample outputs (good):
{good_samples}

Sample outputs (poor):
{poor_samples}

Based on these patterns, write ONE improved system prompt for this agent that:
1. Reinforces behaviors seen in good outputs
2. Corrects/avoids behaviors seen in poor outputs
3. Is concise (max 300 words)

Respond with ONLY the improved system prompt text, no preamble.
"""

_PATTERN_PROMPT = """\
You are analyzing failure patterns in AI agent outputs.

Agent: {agent}
Poor outputs (sample):
{samples}

Identify the top failure pattern in one sentence, then suggest one fix.
Format:
PATTERN: <one sentence>
FIX: <one sentence>
"""


@dataclass
class TrainingReport:
    """Result of one trainer review cycle."""
    agent: str
    interactions_reviewed: int
    good_count: int
    poor_count: int
    skills_updated: list[str]
    new_prompt_version: int | None
    patterns_found: list[str]
    training_pairs_available: int


class AgentTrainer:
    """Reviews agent output history and writes improvements back to shared memory.

    Usage::

        trainer = AgentTrainer()
        report = trainer.review(agent="critic", min_interactions=10)
        print(report.new_prompt_version)  # version number if prompt was updated
    """

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        self._store = memory_store or ForgeMemoryStore()

    # ------------------------------------------------------------------
    # Main review cycle
    # ------------------------------------------------------------------

    def review(self, agent: str, min_interactions: int = 5) -> TrainingReport:
        """Read interaction history for agent, grade, and write improvements.

        Steps:
          1. Load recent interactions
          2. Estimate quality via critic verdicts (if available) or heuristics
          3. Split into good/poor buckets
          4. If enough poor outputs → rewrite system prompt
          5. Update skill scores
          6. Log any detected patterns as meta-patterns (Layer 7)
        """
        interactions = self._store.query_interactions(agent=agent, limit=100)
        n = len(interactions)

        if n < min_interactions:
            logger.info("Trainer: not enough interactions for %s (%d/%d)", agent, n, min_interactions)
            return TrainingReport(
                agent=agent,
                interactions_reviewed=n,
                good_count=0, poor_count=0,
                skills_updated=[], new_prompt_version=None,
                patterns_found=[],
                training_pairs_available=0,
            )

        # Bucket by output length heuristic + hallucination flags as proxy for quality
        # (In production, wire in Critic verdicts from routing_decisions)
        hallucinations = {
            h["interaction_id"]
            for h in self._store.query_hallucinations(agent=agent, limit=200)
            if h.get("interaction_id")
        }

        good, poor = [], []
        for ix in interactions:
            if ix["id"] in hallucinations:
                poor.append(ix)
            elif len(ix.get("output_text", "")) > 20:
                good.append(ix)
            else:
                poor.append(ix)

        good_count, poor_count = len(good), len(poor)
        quality_score = good_count / n if n > 0 else 0.5

        # Update skill score
        self._store.update_skill(
            agent=agent,
            skill_name="output_quality",
            score=round(quality_score, 3),
            evidence=f"Reviewed {n} interactions: {good_count} good, {poor_count} poor",
        )
        skills_updated = ["output_quality"]

        # Detect patterns in poor outputs if any exist
        patterns_found: list[str] = []
        if poor_count > 0:
            pattern = self._detect_pattern(agent, poor)
            if pattern:
                patterns_found.append(pattern)
                self._store.log_meta_pattern(
                    pattern=pattern,
                    source_layers=[1, 4],
                    impact="high" if poor_count > good_count else "medium",
                )

        # Rewrite system prompt if poor outputs are ≥ 30%
        new_version: int | None = None
        if poor_count >= max(3, int(n * 0.3)):
            new_prompt = self._generate_improved_prompt(agent, good, poor)
            if new_prompt:
                current = self._store.get_current_prompt(agent)
                if not current or current.get("prompt_text", "") != new_prompt:
                    new_version = self._store.save_prompt_version(
                        agent=agent,
                        prompt_text=new_prompt,
                        change_reason=f"Auto-improved: {poor_count}/{n} poor outputs",
                        changed_by="trainer",
                        delta_summary=f"Addressed {len(patterns_found)} patterns",
                    )
                    logger.info("Trainer: wrote new prompt v%d for %s", new_version, agent)

        training_pairs = len(self._store.get_training_pairs(agent=agent))

        return TrainingReport(
            agent=agent,
            interactions_reviewed=n,
            good_count=good_count,
            poor_count=poor_count,
            skills_updated=skills_updated,
            new_prompt_version=new_version,
            patterns_found=patterns_found,
            training_pairs_available=training_pairs,
        )

    def review_all(self, min_interactions: int = 5) -> list[TrainingReport]:
        """Run review cycle for every agent that has interactions."""
        all_skills = self._store.get_all_skills()
        agents = list(all_skills.keys())

        # Also include agents with interactions but no skills yet
        for ix in self._store.query_interactions(limit=500):
            if ix["agent"] not in agents:
                agents.append(ix["agent"])

        # Deduplicate
        return [self.review(a, min_interactions) for a in set(agents)]

    # ------------------------------------------------------------------
    # Training pair export (Layer 3 → LoRA)
    # ------------------------------------------------------------------

    def export_training_pairs(
        self, agent: str | None = None, format: str = "sharegpt"
    ) -> list[dict]:
        """Export unused correction pairs for LoRA fine-tuning.

        format="sharegpt" → [{"conversations": [{"from": "human", "value": bad},
                                                 {"from": "gpt",   "value": good}]}]
        format="dpo"      → [{"prompt": bad, "chosen": good, "rejected": ""}]
        """
        pairs = self._store.get_training_pairs(agent=agent)
        if not pairs:
            return []

        if format == "dpo":
            return [
                {"prompt": p["bad_output"], "chosen": p["good_output"], "rejected": ""}
                for p in pairs
            ]

        # Default: ShareGPT
        return [
            {
                "conversations": [
                    {"from": "human", "value": p["bad_output"]},
                    {"from": "gpt",   "value": p["good_output"]},
                ]
            }
            for p in pairs
        ]

    def mark_pairs_exported(self, agent: str | None = None) -> int:
        """Mark all available training pairs as used. Returns count marked."""
        pairs = self._store.get_training_pairs(agent=agent)
        if pairs:
            self._store.mark_training_used([p["id"] for p in pairs])
        return len(pairs)

    # ------------------------------------------------------------------
    # Write skills / guidelines
    # ------------------------------------------------------------------

    def write_skill(
        self, agent: str, skill_name: str, score: float, evidence: str | None = None
    ) -> None:
        """Directly write a skill score for an agent (used by external reviewers)."""
        self._store.update_skill(agent, skill_name, score, evidence)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _detect_pattern(self, agent: str, poor_interactions: list[dict]) -> str | None:
        if not poor_interactions:
            return None
        samples = "\n".join(
            f"- {ix.get('output_text', '')[:150]}" for ix in poor_interactions[:5]
        )
        prompt = _PATTERN_PROMPT.format(agent=agent, samples=samples)
        try:
            raw = self._call_llm(prompt)
            for line in raw.splitlines():
                if line.startswith("PATTERN:"):
                    return line.split(":", 1)[1].strip()
        except Exception as exc:
            logger.warning("Trainer._detect_pattern LLM error: %s", exc)
        return None

    def _generate_improved_prompt(
        self, agent: str, good: list[dict], poor: list[dict]
    ) -> str | None:
        good_samples = "\n".join(
            f"- {ix.get('output_text', '')[:150]}" for ix in good[:3]
        )
        poor_samples = "\n".join(
            f"- {ix.get('output_text', '')[:150]}" for ix in poor[:3]
        )
        prompt = _REVIEW_PROMPT.format(
            agent=agent,
            n=len(good) + len(poor),
            good_samples=good_samples or "(none)",
            poor_samples=poor_samples or "(none)",
        )
        try:
            return self._call_llm(prompt).strip()
        except Exception as exc:
            logger.warning("Trainer._generate_improved_prompt LLM error: %s", exc)
        return None

    def _call_llm(self, prompt: str) -> str:
        from jarvis.core import _ask_ollama, FALLBACK_MODEL
        return _ask_ollama(prompt, model=FALLBACK_MODEL)
