from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta

from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist, Insight

logger = logging.getLogger(__name__)

_STALE_HOURS = 24  # KB data older than this triggers a fresh adapter call

@register
class GrocerySpec(BaseSpecialist):
    """Grocery domain specialist — prices, inventory, meal suggestions."""

    name = "grocery_specialist"
    domain = "grocery"
    schedule = "0 */4 * * *"  # every 4 hours

    def gather(self) -> list[dict]:
        """Gather grocery data: KB inventory + prices + preferences."""
        data: list[dict] = []

        # Pull existing KB facts
        try:
            prices = self.lake.query_facts(domain="grocery", fact_type="price", min_confidence=0.0, limit=50)
            data.extend({"source": "kb_price", **p} for p in prices)
        except Exception as exc:
            logger.warning("GrocerySpec.gather: price query failed: %s", exc)

        try:
            inv = self.lake.query_facts(domain="grocery", fact_type="inventory", min_confidence=0.0, limit=50)
            data.extend({"source": "kb_inventory", **i} for i in inv)
        except Exception as exc:
            logger.warning("GrocerySpec.gather: inventory query failed: %s", exc)

        # Check if data is stale — if so, pull from adapter
        if self._kb_data_is_stale(data):
            fresh = self._gather_from_adapter()
            data.extend(fresh)

        # Pull calendar context if CalendarSpec has written anything
        try:
            calendar = self.lake.query_facts(domain="calendar", min_confidence=0.0, limit=10)
            data.extend({"source": "kb_calendar", **c} for c in calendar)
        except Exception:
            pass

        return data

    def _kb_data_is_stale(self, data: list[dict]) -> bool:
        """Return True if no fresh KB data exists (>24h old or empty)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=_STALE_HOURS)).isoformat()
        fresh = [d for d in data if d.get("updated_at", "") >= cutoff]
        return len(fresh) == 0

    def _gather_from_adapter(self) -> list[dict]:
        """Call the existing grocery adapter for fresh data."""
        try:
            from jarvis.adapters.grocery import GroceryAdapter
            adapter = GroceryAdapter()
            result = adapter.safe_run("meal_plan", {})
            if result.success:
                return [{"source": "adapter", "type": "meal_plan", "content": result.text}]
        except Exception as exc:
            logger.warning("GrocerySpec._gather_from_adapter failed: %s", exc)
        return []

    def analyze(self, raw_data: list[dict], cross_context: dict) -> list[Insight]:
        """Use LLM to extract insights from gathered data."""
        if not raw_data:
            return []

        # Summarize input for LLM
        items_text = "\n".join(
            f"- [{d.get('source','?')}] {d.get('summary', d.get('content', str(d)[:200]))}"
            for d in raw_data[:20]
        )

        # Pull budget context from cross-domain KB
        budget_ctx = ""
        if "finance" in cross_context:
            budget_facts = cross_context["finance"][:2]
            budget_ctx = "\n".join(f"  Budget: {b.get('summary','')}" for b in budget_facts)

        prompt = (
            "You are the Jarvis grocery specialist. Analyze this household grocery data and "
            "generate 2-4 actionable insights (price changes, inventory alerts, meal suggestions).\n\n"
            f"Grocery data:\n{items_text}\n"
            f"{('Finance context:\n' + budget_ctx) if budget_ctx else ''}\n\n"
            "For each insight, respond on its own line starting with one of: "
            "[PRICE] [INVENTORY] [MEAL] [BUDGET]\n"
            "Example: [PRICE] Chicken breast up 25% — suggest switching to pork this week.\n"
            "Insights:"
        )

        try:
            from jarvis.core import _ask_ollama
            raw_response = _ask_ollama(prompt, model=self.model)
            return self._parse_insights(raw_response)
        except Exception as exc:
            logger.warning("GrocerySpec.analyze LLM call failed: %s", exc)
            return []

    def _parse_insights(self, llm_response: str) -> list[Insight]:
        """Parse LLM response into Insight objects."""
        insights = []
        type_map = {
            "[PRICE]": "price",
            "[INVENTORY]": "inventory",
            "[MEAL]": "meal_plan",
            "[BUDGET]": "budget",
        }
        for line in llm_response.strip().splitlines():
            line = line.strip()
            for tag, fact_type in type_map.items():
                if line.startswith(tag):
                    content = line[len(tag):].strip()
                    if content:
                        insights.append(Insight(fact_type=fact_type, content=content, confidence=0.75))
                    break
        return insights

    def improve(self) -> list[str]:
        """Identify knowledge gaps in the grocery domain."""
        gaps = []
        try:
            # Find low-confidence facts
            low_conf = self.lake.query_facts(domain="grocery", min_confidence=0.0, limit=100)
            stale = [f for f in low_conf if f.get("confidence", 1.0) < 0.5]
            for fact in stale[:3]:
                gaps.append(f"Low confidence ({fact.get('confidence'):.2f}): {fact.get('summary','?')[:80]}")
        except Exception as exc:
            logger.warning("GrocerySpec.improve failed: %s", exc)
        return gaps
