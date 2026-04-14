from __future__ import annotations
import logging
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist, Insight

logger = logging.getLogger(__name__)


@register
class HomeSpec(BaseSpecialist):
    name = "home_specialist"
    domain = "home"
    schedule = "0 8 * * *"

    def gather(self) -> list[dict]:
        items = []
        try:
            facts = self.lake.query_facts(domain="home", limit=20)
            items.extend(facts)
        except Exception as exc:
            logger.warning("HomeSpec.gather KB error: %s", exc)
        # Read blackboard for weather/budget context
        try:
            posts = self.blackboard.read(topics=["weather", "maintenance", "home"], limit=10)
            items.extend(posts)
        except Exception as exc:
            logger.warning("HomeSpec.gather blackboard error: %s", exc)
        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        if not gathered:
            return []

        summary = "\n".join(
            str(item.get("content", item.get("summary", item.get("text", ""))))[:150]
            for item in gathered[:10]
        )
        prompt = (
            "You are managing home maintenance and household tasks.\n\n"
            f"Home data:\n{summary}\n\n"
            "Identify upcoming maintenance tasks. Prioritize by urgency. Estimate costs if possible.\n"
            "Format: [URGENT]/[UPCOMING]/[SEASONAL]: <task description>\n"
        )

        insights = []
        try:
            from jarvis.core import _ask_ollama
            injected = self.context_engine.inject(self.domain, prompt)
            raw = _ask_ollama(injected, model=self.model)
            for line in raw.strip().splitlines():
                line = line.strip()
                for tag in ("[URGENT]", "[UPCOMING]", "[SEASONAL]"):
                    if line.startswith(tag):
                        content = line[len(tag):].strip().lstrip(":").strip()
                        urgency = "high" if tag == "[URGENT]" else "normal"
                        insights.append(Insight(
                            fact_type="maintenance",
                            content=content,
                            confidence=0.7,
                            tags=f"home,{tag.strip('[]').lower()}",
                        ))
                        if tag == "[URGENT]":
                            self.blackboard.post(
                                agent=self.name, topic="maintenance",
                                content=content, urgency=urgency,
                            )
        except Exception as exc:
            logger.warning("HomeSpec.analyze LLM error: %s", exc)
        return insights

    def improve(self, insights: list[Insight] | None = None) -> list[str]:
        gaps: list[str] = []
        try:
            home_facts = self.lake.query_facts(domain="home", limit=5)
            if not home_facts:
                self.blackboard.post(
                    agent=self.name, topic="home",
                    content="No home maintenance data in KB. Consider adding maintenance schedule.",
                    urgency="low",
                )
                gaps.append("No home maintenance data in KB.")
        except Exception as exc:
            logger.warning("HomeSpec.improve error: %s", exc)
        return gaps
