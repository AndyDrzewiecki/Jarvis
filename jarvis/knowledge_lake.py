from __future__ import annotations
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_HALF_LIVES: dict[str, int] = {
    "price": 3, "schedule": 7, "budget": 30, "research": 90, "note": 180,
}

class KnowledgeLake:
    def __init__(self, data_dir: str | None = None):
        from jarvis.memory_bus import get_bus
        self._bus = get_bus(data_dir=data_dir)
        self._semantic = self._bus.semantic

    def store_fact(self, domain: str, fact_type: str, content: str,
                   source_agent: str, confidence: float = 0.8,
                   tags: str = "", expires_at: str | None = None, structured_data: dict | None = None) -> str:
        return self._semantic.add_fact(domain=domain, fact_type=fact_type, summary=content,
                                        source_agent=source_agent, confidence=confidence,
                                        tags=tags, expires_at=expires_at)

    def query_facts(self, domain: str | None = None, fact_type: str | None = None,
                    min_confidence: float = 0.5, limit: int = 20) -> list[dict]:
        return self._semantic.query_facts(domain, fact_type, min_confidence, limit)

    def search(self, query: str, n: int = 10, domain: str | None = None) -> list[dict]:
        return self._semantic.search(query, n=n, domain=domain)

    def store_price(self, item_name: str, store: str, price: float, unit: str = "each", source_agent: str = "") -> str:
        return self._semantic.store_price(item_name, store, price, unit)

    def store_schedule(self, title: str, who: str | None, start_time: str, **kwargs) -> str:
        return self._semantic.store_schedule(title, who, start_time, **kwargs)

    def store_budget(self, category: str, period: str, budgeted: float, spent: float = 0) -> str:
        return self._semantic.store_budget(category, period, budgeted, spent)

    def store_inventory(self, item_name: str, category: str | None = None, quantity: float = 1, **kwargs) -> str:
        return self._semantic.store_inventory(item_name, category, quantity, **kwargs)

    def store_maintenance(self, item: str, **kwargs) -> str:
        return self._semantic.store_maintenance(item, **kwargs)

    def recent_by_domain(self, limit_per_domain: int = 3) -> dict[str, list]:
        return self._semantic.recent_by_domain(limit_per_domain)

    def effective_confidence(self, fact: dict) -> float:
        try:
            updated = datetime.fromisoformat(
                fact.get("updated_at", fact.get("created_at", "")).replace("Z", "+00:00"))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - updated).total_seconds() / 86400
            half_life = _HALF_LIVES.get(fact.get("fact_type", ""), 30)
            decay = 0.5 ** (age_days / half_life)
            return float(fact.get("confidence", 0.8)) * decay
        except Exception:
            return float(fact.get("confidence", 0.8))
