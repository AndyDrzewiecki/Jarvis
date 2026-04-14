from __future__ import annotations
import logging
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist, Insight

logger = logging.getLogger(__name__)


@register
class InvestorSpec(BaseSpecialist):
    name = "investor_specialist"
    domain = "investor"
    schedule = "0 9,16 * * 1-5"  # 9 AM and 4 PM weekdays

    def gather(self) -> list[dict]:
        items = []
        # Call InvestorAdapter
        try:
            from jarvis.adapters.investor import InvestorAdapter
            adapter = InvestorAdapter()
            result = adapter.safe_run("daily_brief", {})
            if result.success:
                items.append({"type": "daily_brief", "content": result.text[:500]})
            result2 = adapter.safe_run("market_check", {})
            if result2.success:
                items.append({"type": "market_check", "content": result2.text[:500]})
        except Exception as exc:
            logger.warning("InvestorSpec.gather adapter error: %s", exc)
        # News KB for market-relevant headlines
        try:
            news_facts = self.lake.query_facts(domain="news", limit=10)
            finance_facts = [f for f in news_facts if "finance" in f.get("tags", "").lower()
                             or "market" in f.get("content", "").lower()]
            items.extend(finance_facts[:5])
        except Exception as exc:
            logger.warning("InvestorSpec.gather KB error: %s", exc)
        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        if not gathered:
            return []

        summary = "\n".join(
            str(item.get("content", item.get("text", "")))[:200]
            for item in gathered[:8]
        )
        prompt = (
            "You are an investment analyst reviewing market data.\n\n"
            f"Data:\n{summary}\n\n"
            "Identify key market moves. Flag significant risks. Suggest 1-2 portfolio notes.\n"
            "Format: [RISK]/[MOVE]/[NOTE]: <content>\n"
        )

        insights = []
        try:
            from jarvis.core import _ask_ollama
            injected = self.context_engine.inject(self.domain, prompt)
            raw = _ask_ollama(injected, model=self.model)
            for line in raw.strip().splitlines():
                line = line.strip()
                for tag in ("[RISK]", "[MOVE]", "[NOTE]"):
                    if line.startswith(tag):
                        content = line[len(tag):].strip().lstrip(":").strip()
                        urgency = "high" if tag == "[RISK]" else "normal"
                        insights.append(Insight(
                            fact_type="knowledge",
                            content=content,
                            confidence=0.7,
                            tags=f"investor,{tag.strip('[]').lower()}",
                        ))
                        if tag == "[RISK]":
                            self.blackboard.post(
                                agent=self.name, topic="market_alert",
                                content=content, urgency=urgency,
                            )
        except Exception as exc:
            logger.warning("InvestorSpec.analyze LLM error: %s", exc)
        return insights

    def improve(self, insights: list[Insight] | None = None) -> list[str]:
        gaps: list[str] = []
        try:
            invest_facts = self.lake.query_facts(domain="investor", limit=5)
            if not invest_facts:
                self.blackboard.post(
                    agent=self.name, topic="investor",
                    content="No investor data in KB.",
                    urgency="low",
                )
                gaps.append("No investor data in KB.")
        except Exception as exc:
            logger.warning("InvestorSpec.improve error: %s", exc)
        return gaps
