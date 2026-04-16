"""PatternAnalyst — Brain 2 of Project Forge.

Reads Critic verdicts and agent interaction history, identifies recurring failure
patterns, and proposes targeted fixes to the staging table (prompt_versions).

Responsibilities:
  1. Query recent Critic verdicts (from routing + hallucination tables)
  2. Cluster failures into trends (by flag type, agent, time window)
  3. Formulate fix proposals — new prompt fragments or routing rule tweaks
  4. Write proposals to prompt_versions table (status=staging) for the Tester (Brain 3)
  5. Log identified patterns as meta-patterns (Layer 7)

Brain role in the self-improvement loop:
  Critic (Brain 1) → PatternAnalyst (Brain 2) → AgentTester (Brain 3) → CodeAuditor (Brain 4)
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jarvis.forge.agent_base import BaseDevAgent, TaskResult
from jarvis.forge.memory_store import ForgeMemoryStore
from jarvis.forge.ollama_gateway import forge_generate

logger = logging.getLogger(__name__)

_TREND_PROMPT = """\
You are a pattern analyst reviewing AI agent failures.

Agent: {agent}
Failure flags observed (count): {flag_counts}
Sample poor outputs:
{samples}

Recent hallucination claims (if any):
{hallucinations}

Identify the single most impactful failure pattern and write a targeted fix.
Respond in EXACTLY this format:
PATTERN: <one sentence describing the root cause>
SEVERITY: high|medium|low
FIX_TYPE: prompt_rewrite|routing_rule|retry_logic|output_format
FIX: <concrete prompt addition or rule change, max 100 words>
RATIONALE: <one sentence>
"""


@dataclass
class TrendReport:
    """Summary of one pattern analysis cycle."""
    agent: str
    interactions_reviewed: int
    poor_count: int
    flag_distribution: dict[str, int]
    patterns_identified: list[str]
    proposals_staged: int
    top_flag: str | None


@dataclass
class FixProposal:
    """A staged prompt or routing fix waiting for the Tester (Brain 3)."""
    agent: str
    pattern: str
    fix_type: str           # prompt_rewrite | routing_rule | retry_logic | output_format
    fix_text: str
    severity: str
    rationale: str
    prompt_version_id: int | None = None


class PatternAnalyst(BaseDevAgent):
    """Brain 2 — identifies failure trends and stages fix proposals.

    Usage::

        analyst = PatternAnalyst()
        report = analyst.analyze(agent="critic", window=200)
        print(report.patterns_identified, report.proposals_staged)
    """

    name = "pattern_analyst"
    model = "qwen2.5:0.5b"

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        super().__init__(memory_store)
        self._proposals: list[FixProposal] = []

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def analyze(self, agent: str, window: int = 200) -> TrendReport:
        """Analyze recent interactions for agent, identify patterns, stage fixes.

        Args:
            agent:  Target agent to analyze (e.g. "critic", "code_auditor").
            window: How many recent interactions to examine.

        Returns:
            TrendReport with patterns found and number of proposals staged.
        """
        interactions = self._store.query_interactions(agent=agent, limit=window)
        n = len(interactions)

        # Pull hallucinations for context
        hallucinations = self._store.query_hallucinations(agent=agent, limit=50)
        halluc_ids = {h.get("interaction_id") for h in hallucinations if h.get("interaction_id")}

        # Infer quality from routing outcomes (poor = flagged or very short)
        poor: list[dict] = []
        flag_counter: Counter = Counter()

        for ix in interactions:
            is_poor = ix["id"] in halluc_ids or len(ix.get("output_text", "")) < 20
            if is_poor:
                poor.append(ix)
                # Simple heuristic flag extraction from output text
                output = ix.get("output_text", "").lower()
                if "hallucin" in output:
                    flag_counter["hallucination"] += 1
                if "error" in output or "exception" in output:
                    flag_counter["error"] += 1
                if len(ix.get("output_text", "")) < 10:
                    flag_counter["incomplete"] += 1
                if "off" in output and "topic" in output:
                    flag_counter["off_topic"] += 1
                if not flag_counter:
                    flag_counter["low_quality"] += 1

        # Also count from hallucination records
        for h in hallucinations:
            flag_counter["hallucination"] += 1

        patterns_found: list[str] = []
        proposals_staged = 0
        top_flag = flag_counter.most_common(1)[0][0] if flag_counter else None

        if poor and flag_counter:
            proposal = self._generate_proposal(agent, poor, hallucinations, flag_counter)
            if proposal:
                patterns_found.append(proposal.pattern)
                self._proposals.append(proposal)

                # Stage fix as new prompt version
                try:
                    current = self._store.get_current_prompt(agent)
                    current_text = current.get("prompt_text", "") if current else ""
                    staged_text = current_text + "\n\n[STAGED FIX]\n" + proposal.fix_text
                    vid = self._store.save_prompt_version(
                        agent=agent,
                        prompt_text=staged_text,
                        change_reason=f"PatternAnalyst staged: {proposal.pattern[:100]}",
                        changed_by="pattern_analyst",
                        delta_summary=f"fix_type={proposal.fix_type} severity={proposal.severity}",
                    )
                    proposal.prompt_version_id = vid
                    proposals_staged += 1
                except Exception as exc:
                    logger.warning("PatternAnalyst: failed to stage proposal: %s", exc)

                # Log to Layer 7
                try:
                    self._store.log_meta_pattern(
                        pattern=proposal.pattern,
                        source_layers=[1, 4],
                        impact=proposal.severity,
                    )
                except Exception:
                    pass

        # Log own interaction
        self._store.log_interaction(
            agent=self.name,
            task_id=f"analyze:{agent}",
            input_text=f"analyze agent={agent} window={window}",
            output_text=f"poor={len(poor)}/{n} patterns={len(patterns_found)} proposals={proposals_staged}",
            model=self.model,
        )

        logger.info(
            "PatternAnalyst: agent=%s reviewed=%d poor=%d patterns=%d proposals=%d",
            agent, n, len(poor), len(patterns_found), proposals_staged,
        )

        return TrendReport(
            agent=agent,
            interactions_reviewed=n,
            poor_count=len(poor),
            flag_distribution=dict(flag_counter),
            patterns_identified=patterns_found,
            proposals_staged=proposals_staged,
            top_flag=top_flag,
        )

    def analyze_all(self, window: int = 200) -> list[TrendReport]:
        """Run analysis for every agent that has interaction history."""
        all_ixns = self._store.query_interactions(limit=1000)
        agents = list({ix["agent"] for ix in all_ixns if ix["agent"] != self.name})
        return [self.analyze(agent, window) for agent in agents]

    def get_staged_proposals(self) -> list[FixProposal]:
        """Return all proposals generated this session."""
        return list(self._proposals)

    # ------------------------------------------------------------------
    # BaseDevAgent interface
    # ------------------------------------------------------------------

    def execute_task(self, task: dict) -> TaskResult:
        payload = task.get("payload", {})
        task_type = task.get("type", "analyze")

        if task_type == "analyze":
            agent = payload.get("agent", "")
            window = payload.get("window", 200)
            if not agent:
                return TaskResult(
                    task_id=task["id"], agent=self.name,
                    status="failure", output="", error="Missing 'agent' in payload",
                )
            report = self.analyze(agent, window)
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"patterns={len(report.patterns_identified)} proposals={report.proposals_staged}",
                confidence=0.8 if report.patterns_identified else 0.5,
                metadata={"report": {
                    "interactions_reviewed": report.interactions_reviewed,
                    "poor_count": report.poor_count,
                    "flag_distribution": report.flag_distribution,
                    "patterns": report.patterns_identified,
                    "proposals_staged": report.proposals_staged,
                }},
            )

        if task_type == "analyze_all":
            reports = self.analyze_all(window=payload.get("window", 200))
            total_proposals = sum(r.proposals_staged for r in reports)
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"analyzed={len(reports)} agents, total_proposals={total_proposals}",
                confidence=0.8,
            )

        return TaskResult(
            task_id=task["id"], agent=self.name,
            status="failure", output="", error=f"Unknown task type: {task_type}",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _generate_proposal(
        self,
        agent: str,
        poor: list[dict],
        hallucinations: list[dict],
        flag_counter: Counter,
    ) -> FixProposal | None:
        samples = "\n".join(
            f"- [{ix.get('task_id','?')}] {ix.get('output_text', '')[:120]}"
            for ix in poor[:5]
        )
        halluc_samples = "\n".join(
            f"- {h.get('claim', '')[:100]}" for h in hallucinations[:3]
        ) or "None"
        flag_counts = ", ".join(f"{k}={v}" for k, v in flag_counter.most_common(5))

        prompt = _TREND_PROMPT.format(
            agent=agent,
            flag_counts=flag_counts,
            samples=samples or "(no samples)",
            hallucinations=halluc_samples,
        )

        try:
            raw = forge_generate(prompt, agent=self.name)
        except Exception as exc:
            logger.warning("PatternAnalyst LLM error: %s", exc)
            return None

        return self._parse_proposal(raw, agent)

    def _parse_proposal(self, raw: str, agent: str) -> FixProposal | None:
        lines = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                lines[k.strip().upper()] = v.strip()

        pattern = lines.get("PATTERN", "").strip()
        if not pattern:
            return None

        severity_raw = lines.get("SEVERITY", "medium").lower()
        severity = severity_raw if severity_raw in {"high", "medium", "low"} else "medium"

        fix_type_raw = lines.get("FIX_TYPE", "prompt_rewrite").lower()
        valid_fix_types = {"prompt_rewrite", "routing_rule", "retry_logic", "output_format"}
        fix_type = fix_type_raw if fix_type_raw in valid_fix_types else "prompt_rewrite"

        fix_text = lines.get("FIX", "No fix generated.").strip()
        rationale = lines.get("RATIONALE", "").strip()

        return FixProposal(
            agent=agent,
            pattern=pattern,
            fix_type=fix_type,
            fix_text=fix_text,
            severity=severity,
            rationale=rationale,
        )
