from __future__ import annotations
import logging
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist, Insight

logger = logging.getLogger(__name__)


@register
class FinanceSpec(BaseSpecialist):
    name = "finance_specialist"
    domain = "finance"
    schedule = "0 */6 * * *"

    def gather(self) -> list[dict]:
        items = []
        # Read budget/spending facts from KB
        try:
            facts = self.lake.query_facts(domain="finance", limit=20)
            items.extend(facts)
        except Exception as exc:
            logger.warning("FinanceSpec.gather KB error: %s", exc)
        # Read blackboard for finance/budget topics
        try:
            posts = self.blackboard.read(topics=["finance", "budget"], limit=10)
            items.extend(posts)
        except Exception as exc:
            logger.warning("FinanceSpec.gather blackboard error: %s", exc)
        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        if not gathered:
            return []

        budget_sensitive = self.household_state.is_budget_sensitive()
        budget_note = "BUDGET SENSITIVE MODE: Focus on spending reduction.\n" if budget_sensitive else ""

        summary = "\n".join(
            str(item.get("content", item.get("summary", item.get("text", ""))))[:150]
            for item in gathered[:10]
        )
        prompt = (
            f"{budget_note}You are analyzing household finances.\n\n"
            f"Recent financial data:\n{summary}\n\n"
            "Analyze spending patterns. Flag any budget overruns. Suggest 1-2 savings tips.\n"
            "Format each insight as: [ALERT]/[TIP]/[PATTERN]: <content>\n"
        )

        insights = []
        try:
            from jarvis.core import _ask_ollama
            injected = self.context_engine.inject(self.domain, prompt)
            raw = _ask_ollama(injected, model=self.model)
            for line in raw.strip().splitlines():
                line = line.strip()
                for tag in ("[ALERT]", "[TIP]", "[PATTERN]"):
                    if line.startswith(tag):
                        content = line[len(tag):].strip().lstrip(":").strip()
                        confidence = 0.8 if tag == "[ALERT]" else 0.6
                        insights.append(Insight(
                            fact_type="pattern" if tag == "[PATTERN]" else "knowledge",
                            content=content,
                            confidence=confidence,
                            tags=f"finance,{tag.strip('[]').lower()}",
                        ))
                        # Post high-urgency alerts to blackboard
                        if tag == "[ALERT]":
                            self.blackboard.post(
                                agent=self.name, topic="budget",
                                content=content, urgency="high",
                            )
        except Exception as exc:
            logger.warning("FinanceSpec.analyze LLM error: %s", exc)
        return insights

    def improve(self, insights: list[Insight] | None = None) -> list[str]:
        gaps: list[str] = []
        try:
            budget_facts = self.lake.query_facts(domain="finance", limit=5)
            if not budget_facts:
                self.blackboard.post(
                    agent=self.name, topic="finance",
                    content="No budget data in KB. Consider adding spending data.",
                    urgency="normal",
                )
                gaps.append("No budget data in KB.")
        except Exception as exc:
            logger.warning("FinanceSpec.improve error: %s", exc)
        return gaps
