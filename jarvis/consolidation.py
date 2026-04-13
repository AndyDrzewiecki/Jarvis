"""
Consolidation Engine — processes unconsolidated episodic memories and extracts
semantic knowledge into the KnowledgeLake.

Each unconsolidated episode is:
1. Summarised into a conversation transcript
2. Sent to the LLM (fallback model) for knowledge extraction
3. Parsed into Insight objects (FACT: type | content | confidence)
4. Merged into the SemanticStore (create new or reinforce existing)
5. Marked as consolidated in the EpisodicStore
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ConsolidationReport:
    """Result of one consolidation run."""
    started_at: str = field(default_factory=_now)
    ended_at: str = ""
    episodes_processed: int = 0
    facts_created: int = 0
    facts_reinforced: int = 0
    episodes_pruned: int = 0
    error: str | None = None


class ConsolidationEngine:
    """Nightly engine that consolidates episodic memories into semantic knowledge."""

    def __init__(self, data_dir: str | None = None):
        self._data_dir = data_dir
        self._bus = None
        self._lake = None

    @property
    def bus(self):
        """Lazy MemoryBus accessor."""
        if self._bus is None:
            from jarvis.memory_bus import get_bus
            self._bus = get_bus(data_dir=self._data_dir)
        return self._bus

    @property
    def lake(self):
        """Lazy KnowledgeLake accessor."""
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake(data_dir=self._data_dir)
        return self._lake

    def run(self) -> ConsolidationReport:
        """Process all unconsolidated episodes. Returns a ConsolidationReport."""
        report = ConsolidationReport()
        try:
            episodes = self.bus.episodic.get_unconsolidated(limit=50)
        except Exception as exc:
            logger.error("ConsolidationEngine.run: failed to get unconsolidated episodes: %s", exc)
            report.error = str(exc)
            report.ended_at = _now()
            return report

        for episode in episodes:
            try:
                self._process_episode(episode, report)
            except Exception as exc:
                logger.warning(
                    "ConsolidationEngine: episode %s processing failed: %s",
                    episode.get("id"), exc,
                )
            finally:
                # Always mark as consolidated to avoid reprocessing
                try:
                    self.bus.episodic.mark_consolidated(episode["id"])
                except Exception as exc:
                    logger.warning(
                        "ConsolidationEngine: mark_consolidated failed for %s: %s",
                        episode.get("id"), exc,
                    )
            report.episodes_processed += 1

        # Prune old low-satisfaction episodes
        try:
            pruned = self.bus.episodic.prune(older_than_days=90, min_satisfaction=0.3)
            report.episodes_pruned = pruned
        except Exception as exc:
            logger.warning("ConsolidationEngine: prune failed: %s", exc)

        report.ended_at = _now()
        logger.info(
            "Consolidation complete: episodes=%d created=%d reinforced=%d pruned=%d error=%s",
            report.episodes_processed, report.facts_created, report.facts_reinforced,
            report.episodes_pruned, report.error,
        )
        return report

    def _process_episode(self, episode: dict, report: ConsolidationReport) -> None:
        """Extract knowledge from one episode and merge into semantic store."""
        messages = self.bus.episodic.get_messages(episode["id"])
        if not messages:
            return

        try:
            raw = self._extract_knowledge(episode, messages)
        except Exception as exc:
            logger.warning(
                "ConsolidationEngine._extract_knowledge failed for episode %s: %s",
                episode.get("id"), exc,
            )
            return

        insights = self._parse_extraction(raw)
        for insight in insights:
            try:
                action = self._merge_into_semantic(insight, self.lake)
                if action == "created":
                    report.facts_created += 1
                elif action == "reinforced":
                    report.facts_reinforced += 1
            except Exception as exc:
                logger.warning("ConsolidationEngine._merge failed: %s", exc)

    def _extract_knowledge(self, episode: dict, messages: list[dict]) -> str:
        """Build transcript and call LLM for knowledge extraction."""
        transcript_lines = []
        for msg in messages[:30]:  # cap at 30 messages per episode
            role = msg.get("role", "?")
            content = msg.get("content", "")[:300]
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)

        domain = episode.get("domain") or "general"
        summary = episode.get("summary") or ""

        prompt = (
            "You are extracting long-term knowledge from a conversation episode.\n\n"
            f"Episode summary: {summary}\n"
            f"Domain: {domain}\n\n"
            f"Conversation:\n{transcript}\n\n"
            "Extract 0-5 reusable facts that should be remembered long-term.\n"
            "For each fact, respond on its own line in this exact format:\n"
            "FACT: <type> | <content> | <confidence 0.0-1.0>\n\n"
            "Valid types: preference, knowledge, schedule, price, budget, note\n"
            "If no reusable facts exist, respond with: NONE\n"
            "Facts:"
        )

        from jarvis.core import _ask_ollama, FALLBACK_MODEL
        return _ask_ollama(prompt, model=FALLBACK_MODEL)

    def _parse_extraction(self, raw: str) -> list:
        """Parse 'FACT: type | content | confidence' lines into Insight objects."""
        from jarvis.specialists.base import Insight
        insights = []
        if not raw or raw.strip().upper() == "NONE":
            return insights

        for line in raw.strip().splitlines():
            line = line.strip()
            if not line.startswith("FACT:"):
                continue
            rest = line[5:].strip()
            parts = [p.strip() for p in rest.split("|")]
            if len(parts) != 3:
                continue
            fact_type, content, confidence_str = parts
            if not fact_type or not content:
                continue
            try:
                confidence = float(confidence_str)
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                confidence = 0.7
            insights.append(Insight(fact_type=fact_type, content=content, confidence=confidence))

        return insights

    def _merge_into_semantic(self, insight, lake) -> str:
        """Search existing facts; reinforce if overlap exists, else create new."""
        try:
            existing = lake.search(insight.content, n=3)
        except Exception:
            existing = []

        if existing:
            # Overlap found — reinforce (log but don't re-store to avoid duplication)
            logger.debug(
                "ConsolidationEngine: reinforcing existing fact for '%s'", insight.content[:60]
            )
            return "reinforced"

        # No match — create new fact
        lake.store_fact(
            domain="general",
            fact_type=insight.fact_type,
            content=insight.content,
            source_agent="consolidation_engine",
            confidence=insight.confidence,
        )
        return "created"
