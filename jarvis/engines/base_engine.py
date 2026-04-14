from __future__ import annotations
import logging
from datetime import datetime, timezone

from jarvis.memory_tiers.types import CycleReport, Insight
from jarvis.specialists.base import BaseSpecialist

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

class BaseKnowledgeEngine(BaseSpecialist):
    """Base class for knowledge accumulation engines.

    Extends BaseSpecialist with IngestionBuffer access and
    engine-specific run_cycle() that routes through the buffer.
    """

    engine_type: str = "knowledge"

    def __init__(self):
        super().__init__()
        self._ingestion = None
        self._engine_store = None

    @property
    def ingestion(self):
        """Lazy IngestionBuffer accessor."""
        if not hasattr(self, '_ingestion') or self._ingestion is None:
            from jarvis.ingestion import IngestionBuffer
            self._ingestion = IngestionBuffer()
        return self._ingestion

    @property
    def engine_store(self):
        """Lazy EngineStore accessor."""
        if not hasattr(self, '_engine_store') or self._engine_store is None:
            from jarvis.engine_store import EngineStore
            self._engine_store = EngineStore()
        return self._engine_store

    def run_cycle(self) -> CycleReport:
        """Engine cycle: gather → prepare RawItems → ingest through buffer → improve."""
        report = CycleReport(specialist=self.name, started_at=_now())
        try:
            raw_data = self.gather()
            report.gathered = len(raw_data)

            raw_items = self.prepare_items(raw_data)
            if raw_items:
                ingest_report = self.ingestion.ingest(self.name, raw_items)
                report.insights = ingest_report.accepted

            gaps = self.improve()
            report.gaps_identified = len(gaps) if gaps else 0

        except Exception as exc:
            logger.exception("Engine %s cycle failed", self.name)
            report.error = str(exc)

        report.ended_at = _now()

        try:
            from jarvis import agent_memory
            agent_memory.log_decision(
                agent=self.name, capability="run_cycle",
                decision=f"Engine cycle: gathered={report.gathered}, ingested={report.insights}",
                reasoning=f"error={report.error}",
                outcome="success" if not report.error else "failure",
            )
        except Exception:
            pass

        return report

    def prepare_items(self, raw_data: list[dict]) -> list:
        """Convert raw gather() output to RawItem list. Subclasses must implement."""
        raise NotImplementedError

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        """Default: engines use ingestion pipeline, not direct analyze. Override if needed."""
        return []

    def improve(self) -> list[str]:
        """Check for data gaps and quality issues. Returns list of gap descriptions."""
        return []
