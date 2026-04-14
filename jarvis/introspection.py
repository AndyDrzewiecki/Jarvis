from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_STALE_DAYS = 7  # Facts older than this are considered stale


class MemoryIntrospector:
    """Provides introspective views into Jarvis memory and decision provenance."""

    def __init__(self):
        self._lake = None

    @property
    def lake(self):
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake

    def explain_recommendation(self, decision_id: str) -> dict:
        """Trace a decision through its provenance chain.

        Returns a dict with keys: decision, related_facts, grade (if available).
        If not found, returns {"error": ...}.
        """
        try:
            from jarvis import agent_memory
            conn = agent_memory._open(agent_memory.DB_PATH)
            row = conn.execute(
                "SELECT * FROM decisions WHERE id = ?", (decision_id,)
            ).fetchone()
            conn.close()
        except Exception as exc:
            logger.warning("MemoryIntrospector.explain_recommendation DB error: %s", exc)
            return {"error": f"DB error: {exc}"}

        if row is None:
            return {"error": f"Decision '{decision_id}' not found"}

        decision = dict(row)

        # Search for related facts in knowledge lake
        related_facts = []
        try:
            query_text = decision.get("decision", "") or decision.get("reasoning", "")
            if query_text:
                related_facts = self.lake.search(query_text[:200], n=5)
        except Exception as exc:
            logger.warning("MemoryIntrospector.explain_recommendation search error: %s", exc)

        # Get grade if available
        grade = None
        try:
            from jarvis import agent_memory
            grade = agent_memory.get_grade(decision_id)
        except Exception:
            pass

        return {
            "decision": decision,
            "related_facts": related_facts,
            "grade": grade,
        }

    def knowledge_audit(self, domain: str | None = None) -> dict:
        """Audit knowledge quality for a domain (or all domains).

        Returns dict with: status, fact_count, confidence_distribution, stale_count, domains.
        """
        try:
            facts = self.lake.query_facts(domain=domain, min_confidence=0.0, limit=500)
        except Exception as exc:
            logger.warning("MemoryIntrospector.knowledge_audit error: %s", exc)
            return {"status": "error", "error": str(exc)}

        if not facts:
            return {"status": "empty", "fact_count": 0, "domain": domain}

        now = datetime.now(timezone.utc)
        stale_cutoff = (now - timedelta(days=_STALE_DAYS)).isoformat()

        high_conf = sum(1 for f in facts if f.get("confidence", 0) >= 0.5)
        low_conf = len(facts) - high_conf
        stale_count = sum(
            1 for f in facts
            if f.get("updated_at", f.get("created_at", "")) < stale_cutoff
        )

        domains = _count_domains(facts)

        return {
            "status": "ok",
            "fact_count": len(facts),
            "confidence_distribution": {
                "high_confidence": high_conf,
                "low_confidence": low_conf,
            },
            "stale_count": stale_count,
            "domains": domains,
            "domain_filter": domain,
        }

    def memory_diff(self, since: str) -> dict:
        """Return knowledge changes since a given ISO timestamp.

        Returns dict with: new_count, new_facts, since.
        """
        try:
            facts = self.lake.query_facts(min_confidence=0.0, limit=1000)
        except Exception as exc:
            logger.warning("MemoryIntrospector.memory_diff error: %s", exc)
            return {"new_count": 0, "new_facts": [], "since": since, "error": str(exc)}

        new_facts = [
            f for f in facts
            if f.get("created_at", "") >= since or f.get("updated_at", "") >= since
        ]

        return {
            "new_count": len(new_facts),
            "new_facts": new_facts[:50],
            "since": since,
        }


def _count_domains(facts: list[dict]) -> dict[str, int]:
    """Count facts per domain."""
    counts: dict[str, int] = {}
    for f in facts:
        d = f.get("domain", "unknown")
        counts[d] = counts.get(d, 0) + 1
    return counts
