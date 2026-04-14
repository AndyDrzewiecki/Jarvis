from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from jarvis.memory_tiers.types import CycleReport, Insight
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist

logger = logging.getLogger(__name__)


@dataclass
class SystemHealthReport:
    """Weekly system health analysis."""
    generated_at: str = ""
    specialist_scores: dict[str, float] = field(default_factory=dict)
    underperformers: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    kb_quality: dict[str, dict] = field(default_factory=dict)
    total_decisions: int = 0
    grade_distribution: dict[str, int] = field(default_factory=dict)


@register
class MetacognitiveSpec(BaseSpecialist):
    """System-level supervisor that monitors all specialist performance.

    Daily: analyzes specialist decision grades and performance.
    Weekly (Sundays): generates full system health report.
    """

    name = "metacognitive_supervisor"
    domain = "metacognitive"
    schedule = "0 6 * * *"  # daily at 6 AM

    def gather(self) -> list[dict]:
        """Collect recent decisions from all specialists plus KB quality metrics."""
        items = []
        try:
            from jarvis import agent_memory
            # Get decisions from last 7 days
            since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            decisions = agent_memory.recent_decisions(n=200)
            # Include grades
            for d in decisions:
                grade = agent_memory.get_grade(d["id"])
                items.append({"decision": d, "grade": grade})
        except Exception as exc:
            logger.warning("MetacognitiveSpec.gather decisions error: %s", exc)

        # Read urgent blackboard posts
        try:
            posts = self.blackboard.read(limit=20)
            urgent = [p for p in posts if p.get("urgency") in ("urgent", "high")]
            if urgent:
                items.append({"blackboard_urgent": len(urgent), "posts": urgent[:5]})
        except Exception as exc:
            logger.warning("MetacognitiveSpec.gather blackboard error: %s", exc)

        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        """Compute per-specialist scores, identify underperformers, generate recommendations."""
        insights = []

        # Extract decisions with grades
        decision_items = [item for item in gathered if "decision" in item]

        if not decision_items:
            return insights

        # Compute per-specialist performance scores
        specialist_stats: dict[str, dict] = {}
        for item in decision_items:
            d = item["decision"]
            agent = d.get("agent", "unknown")
            if agent not in specialist_stats:
                specialist_stats[agent] = {"good": 0, "neutral": 0, "poor": 0, "total": 0, "failures": 0}
            stats = specialist_stats[agent]
            stats["total"] += 1
            if d.get("outcome") == "failure":
                stats["failures"] += 1
            grade = item.get("grade")
            if grade:
                g = grade.get("short_term_grade") or grade.get("grade", "neutral")
                stats[g] = stats.get(g, 0) + 1

        # Score = (good + 0.5*neutral) / total
        scores = {}
        underperformers = []
        for agent, stats in specialist_stats.items():
            total = stats["total"]
            if total > 0:
                score = (stats.get("good", 0) + 0.5 * stats.get("neutral", 0)) / total
                scores[agent] = round(score, 3)
                failure_rate = stats["failures"] / total
                if score < 0.4 or failure_rate > 0.3:
                    underperformers.append(agent)
                    insights.append(Insight(
                        fact_type="knowledge",
                        content=f"{agent} underperforming: score={score:.2f}, failure_rate={failure_rate:.2f}",
                        confidence=0.8,
                        tags="metacognitive,underperformer",
                    ))

        # LLM recommendations
        try:
            from jarvis.core import _ask_ollama
            from jarvis import config
            score_text = "\n".join(f"  {a}: {s:.2f}" for a, s in scores.items())
            prompt = (
                "You are the metacognitive supervisor for an AI assistant system.\n\n"
                f"Specialist performance scores:\n{score_text}\n"
                f"Underperformers: {', '.join(underperformers) or 'none'}\n\n"
                "Generate 1-3 system improvement recommendations.\n"
                "Format: REC: <recommendation>\n"
            )
            raw = _ask_ollama(prompt, model=self.model)
            for line in raw.strip().splitlines():
                line = line.strip()
                if line.startswith("REC:"):
                    rec = line[4:].strip()
                    insights.append(Insight(
                        fact_type="knowledge",
                        content=rec,
                        confidence=0.6,
                        tags="metacognitive,recommendation",
                    ))
                    # Post to blackboard
                    self.blackboard.post(
                        agent=self.name,
                        topic="system_health",
                        content=rec,
                        urgency="normal",
                    )
        except Exception as exc:
            logger.warning("MetacognitiveSpec.analyze LLM error: %s", exc)

        return insights

    def improve(self) -> list[str]:
        """Track recommendation acceptance and log system state."""
        try:
            from jarvis import agent_memory
            agent_memory.log_decision(
                agent=self.name,
                capability="system_health_check",
                decision="Metacognitive improve() called",
                reasoning="Monitoring system health signals",
                outcome="success",
            )
        except Exception as exc:
            logger.warning("MetacognitiveSpec.improve error: %s", exc)
        return []
