from __future__ import annotations
import logging
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist, Insight

logger = logging.getLogger(__name__)


@register
class CalendarSpec(BaseSpecialist):
    name = "calendar_specialist"
    domain = "calendar"
    schedule = "0 */2 * * *"

    def gather(self) -> list[dict]:
        items = []
        # Read schedule facts from KB
        try:
            facts = self.lake.query_facts(domain="calendar", limit=20)
            items.extend(facts)
        except Exception as exc:
            logger.warning("CalendarSpec.gather KB error: %s", exc)
        # Try Google Calendar (gracefully degrade)
        try:
            from jarvis.integrations.google import GoogleSync
            gsync = GoogleSync()
            if gsync.is_configured():
                events = gsync.sync_calendar()
                items.extend(events)
        except Exception as exc:
            logger.debug("CalendarSpec.gather Google: %s", exc)
        # Read blackboard for events from other specialists
        try:
            posts = self.blackboard.read(topics=["calendar", "event", "schedule"], limit=10)
            items.extend(posts)
        except Exception as exc:
            logger.warning("CalendarSpec.gather blackboard error: %s", exc)
        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        if not gathered:
            return []

        household = self.household_state.current()
        hs_note = f"Household mode: {household['primary']}. " if household else ""

        summary = "\n".join(
            str(item.get("content", item.get("summary", item.get("text", ""))))[:150]
            for item in gathered[:10]
        )
        prompt = (
            f"{hs_note}You are managing household calendar and schedule.\n\n"
            f"Schedule data:\n{summary}\n\n"
            "Detect conflicts. Identify upcoming important events. Suggest schedule optimizations.\n"
            "Format each insight as: [CONFLICT]/[EVENT]/[SUGGESTION]: <content>\n"
        )

        insights = []
        try:
            from jarvis.core import _ask_ollama
            injected = self.context_engine.inject(self.domain, prompt)
            raw = _ask_ollama(injected, model=self.model)
            for line in raw.strip().splitlines():
                line = line.strip()
                for tag in ("[CONFLICT]", "[EVENT]", "[SUGGESTION]"):
                    if line.startswith(tag):
                        content = line[len(tag):].strip().lstrip(":").strip()
                        urgency = "high" if tag == "[CONFLICT]" else "normal"
                        insights.append(Insight(
                            fact_type="schedule" if tag == "[EVENT]" else "knowledge",
                            content=content,
                            confidence=0.7,
                            tags=f"calendar,{tag.strip('[]').lower()}",
                        ))
                        if tag == "[CONFLICT]":
                            self.blackboard.post(
                                agent=self.name, topic="calendar",
                                content=content, urgency=urgency,
                            )
        except Exception as exc:
            logger.warning("CalendarSpec.analyze LLM error: %s", exc)
        return insights

    def improve(self, insights: list[Insight] | None = None) -> list[str]:
        gaps: list[str] = []
        try:
            sched_facts = self.lake.query_facts(domain="calendar", limit=5)
            if not sched_facts:
                self.blackboard.post(
                    agent=self.name, topic="calendar",
                    content="No schedule data in KB. Consider syncing calendar.",
                    urgency="low",
                )
                gaps.append("No schedule data in KB.")
        except Exception as exc:
            logger.warning("CalendarSpec.improve error: %s", exc)
        return gaps
