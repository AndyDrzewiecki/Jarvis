from __future__ import annotations
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseResearchLibrarian(ABC):
    """Base class for domain-specific research librarians.

    Librarian cycle: survey → evaluate → catalog → curate.
    """

    domain: str = "base"

    def __init__(self):
        self._catalog = None
        self._lake = None

    @property
    def catalog(self):
        """Lazy LibraryCatalog accessor."""
        if self._catalog is None:
            from jarvis.library.catalog import LibraryCatalog
            self._catalog = LibraryCatalog()
        return self._catalog

    @property
    def lake(self):
        """Lazy KnowledgeLake accessor."""
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake

    def run_cycle(self) -> dict:
        """Run full librarian cycle: survey → evaluate → catalog → curate."""
        report = {"domain": self.domain, "surveyed": 0, "cataloged": 0, "curated": 0}
        try:
            findings = self.survey()
            report["surveyed"] = len(findings)

            evaluated = self.evaluate(findings)

            for item in evaluated:
                self.catalog.add_entry(
                    domain=self.domain,
                    title=item.get("title", ""),
                    source_type=item.get("source_type", "web"),
                    source_url=item.get("source_url"),
                    summary=item.get("summary"),
                    quality_score=item.get("quality_score", 0.5),
                    tags=item.get("tags", ""),
                )
                self.lake.store_fact(
                    domain=self.domain,
                    fact_type="research",
                    content=item.get("summary", item.get("title", "")),
                    source_agent=f"{self.domain}_librarian",
                    confidence=item.get("quality_score", 0.5),
                    tags=item.get("tags", ""),
                )
                report["cataloged"] += 1

            report["curated"] = self.curate()

        except Exception as exc:
            logger.exception("Librarian %s cycle failed: %s", self.domain, exc)
            report["error"] = str(exc)

        return report

    @abstractmethod
    def survey(self) -> list[dict]:
        """Scan sources for new information. Returns list of raw findings."""
        ...

    @abstractmethod
    def evaluate(self, findings: list[dict]) -> list[dict]:
        """Quality-score and deduplicate findings. Returns accepted items."""
        ...

    def curate(self) -> int:
        """Retire stale entries. Override for domain-specific curation."""
        return 0
