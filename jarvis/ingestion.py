from __future__ import annotations
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@dataclass
class RawItem:
    """A single piece of raw data from an engine's gather cycle."""
    content: str
    source: str
    source_url: str | None = None
    fact_type: str = "knowledge"
    domain: str = ""
    structured_data: dict | None = None
    quality_hint: float = 0.5
    tags: str = ""

@dataclass
class IngestionReport:
    """Result of one batch ingest."""
    engine: str
    total: int = 0
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: int = 0
    started_at: str = field(default_factory=_now)
    ended_at: str = ""

class IngestionBuffer:
    """Entry point for non-conversational world knowledge.

    Pipeline per item: deduplicate → quality score → Knowledge Lake → domain table → provenance.
    """

    def __init__(self):
        self._lake = None
        self._db_manager = None

    @property
    def lake(self):
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake

    @property
    def db_manager(self):
        if self._db_manager is None:
            from jarvis.engine_store import EngineStore
            self._db_manager = EngineStore()
        return self._db_manager

    def ingest(self, engine: str, items: list[RawItem]) -> IngestionReport:
        """Batch ingest from an engine's gather cycle."""
        report = IngestionReport(engine=engine, total=len(items))

        for item in items:
            try:
                item.domain = item.domain or engine

                if self._is_duplicate(item):
                    report.duplicates += 1
                    continue

                quality = self._score_quality(item)
                if quality < 0.2:
                    report.rejected += 1
                    continue

                self.lake.store_fact(
                    domain=item.domain,
                    fact_type=item.fact_type,
                    content=item.content,
                    source_agent=engine,
                    confidence=quality,
                    tags=item.tags,
                )

                if item.structured_data:
                    try:
                        self.db_manager.store(
                            engine=item.domain,
                            table=item.fact_type,
                            data=item.structured_data,
                        )
                    except Exception as exc:
                        logger.warning("Structured store failed for %s/%s: %s", item.domain, item.fact_type, exc)

                report.accepted += 1

            except Exception as exc:
                logger.warning("Ingest failed for item from %s: %s", engine, exc)
                report.errors += 1

        report.ended_at = _now()

        try:
            from jarvis import agent_memory
            agent_memory.log_decision(
                agent=engine, capability="ingest",
                decision=f"Ingested: {report.accepted}/{report.total} accepted, {report.duplicates} dupes, {report.rejected} rejected",
                reasoning=f"errors={report.errors}",
                outcome="success" if report.errors == 0 else "partial",
            )
        except Exception:
            pass

        return report

    def _is_duplicate(self, item: RawItem) -> bool:
        """Check if content already exists in KB."""
        try:
            existing = self.lake.search(query=item.content[:200], n=3, domain=item.domain)
            for fact in existing:
                summary = fact.get("summary", "")
                if (item.content.lower()[:80] in summary.lower() or
                        summary.lower()[:80] in item.content.lower()):
                    return True
        except Exception:
            pass
        return False

    def _score_quality(self, item: RawItem) -> float:
        """Score quality based on source reliability and data completeness."""
        score = item.quality_hint
        trusted_sources = {
            "fred", "sec_edgar", "bls", "treasury", "arxiv",
            "pubmed", "fda", "cdc", "congress_gov", "irs",
            "federal_register", "semantic_scholar",
        }
        if item.source.lower() in trusted_sources:
            score = min(1.0, score + 0.15)
        if len(item.content) < 20:
            score = max(0.0, score - 0.2)
        if item.structured_data:
            score = min(1.0, score + 0.1)
        return round(score, 3)
