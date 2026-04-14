from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class Insight:
    """A piece of knowledge extracted by a specialist."""
    fact_type: str
    content: str
    confidence: float = 0.8
    tags: str = ""

@dataclass
class CycleReport:
    """Result of one specialist run_cycle() execution."""
    specialist: str
    started_at: str = field(default_factory=_now)
    ended_at: str = ""
    gathered: int = 0
    insights: int = 0
    gaps_identified: int = 0
    error: str | None = None

class BaseSpecialist:
    """Background AI loop that owns a knowledge domain.

    Subclasses must set class attributes: name, domain, schedule.
    Subclasses must implement: gather(), analyze(), improve().
    """

    name: str = "base_specialist"
    domain: str = "base"
    model: str = ""          # set in __init__ from config
    schedule: str = "0 */4 * * *"

    def __init__(self):
        self._bus = None
        self._lake = None
        if not self.model:
            from jarvis import config
            self.model = config.FALLBACK_MODEL

    @property
    def bus(self):
        """Lazy MemoryBus accessor."""
        if self._bus is None:
            from jarvis.memory_bus import get_bus
            self._bus = get_bus()
        return self._bus

    @property
    def lake(self):
        """Lazy KnowledgeLake accessor."""
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake

    @property
    def household_state(self):
        """Lazy HouseholdState accessor."""
        if not hasattr(self, '_household_state') or self._household_state is None:
            from jarvis.household_state import HouseholdState
            self._household_state = HouseholdState()
        return self._household_state

    @property
    def context_engine(self):
        """Lazy ContextEngine accessor."""
        if not hasattr(self, '_context_engine') or self._context_engine is None:
            from jarvis.context_engine import ContextEngine
            self._context_engine = ContextEngine()
        return self._context_engine

    @property
    def blackboard(self):
        """Lazy SharedBlackboard accessor."""
        if not hasattr(self, '_blackboard') or self._blackboard is None:
            from jarvis.blackboard import SharedBlackboard
            self._blackboard = SharedBlackboard()
        return self._blackboard

    def run_cycle(self) -> CycleReport:
        """Full specialist loop: gather -> analyze -> write to KB -> improve."""
        report = CycleReport(specialist=self.name)
        try:
            raw_data = self.gather()
            report.gathered = len(raw_data)

            cross_context = self.lake.recent_by_domain(limit_per_domain=3)

            insights = self.analyze(raw_data, cross_context)
            report.insights = len(insights)

            for insight in insights:
                self.lake.store_fact(
                    domain=self.domain,
                    fact_type=insight.fact_type,
                    content=insight.content,
                    source_agent=self.name,
                    confidence=insight.confidence,
                    tags=insight.tags,
                )

            gaps = self.improve()
            report.gaps_identified = len(gaps)

        except Exception as exc:
            logger.exception("Specialist %s cycle failed: %s", self.name, exc)
            report.error = str(exc)

        report.ended_at = _now()
        try:
            from jarvis import agent_memory
            agent_memory.log_decision(
                agent=self.name,
                capability="run_cycle",
                decision=f"Cycle: {report.gathered} gathered, {report.insights} insights, {report.gaps_identified} gaps",
                reasoning=f"error={report.error}",
                outcome="success" if not report.error else "failure",
            )
        except Exception:
            pass
        return report

    def gather(self) -> list[dict]:
        """Pull raw data from sources. Subclasses must implement."""
        raise NotImplementedError

    def analyze(self, raw_data: list[dict], cross_context: dict) -> list[Insight]:
        """Use LLM to extract insights. Subclasses must implement."""
        raise NotImplementedError

    def improve(self) -> list[str]:
        """Self-critique: what's stale or missing? Subclasses must implement."""
        raise NotImplementedError
