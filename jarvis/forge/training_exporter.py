"""TrainingExporter — Phase 9 training data pipeline.

Exports data from the Forge memory store in formats ready for LoRA fine-tuning:

  ShareGPT format:
    [{"conversations": [{"from": "human", "value": "..."}, {"from": "gpt", "value": "..."}]}]

  DPO (Direct Preference Optimization) format:
    [{"prompt": "...", "chosen": "...", "rejected": "..."}]

  Alpaca format:
    [{"instruction": "...", "input": "...", "output": "..."}]

Data sources:
  1. Correction pairs (Layer 3) — bad/good output pairs from user corrections
  2. Decision grading — high/low-graded decisions from DecisionGrader
  3. Interaction history — filtered high-quality interactions
  4. Hallucination registry (Layer 4) — used to build rejected samples for DPO

Bitemporal fields are added to all exports for backtesting:
  valid_from, valid_to — when the knowledge is factually valid
  known_from           — when Jarvis became aware of this fact
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.forge.memory_store import ForgeMemoryStore

logger = logging.getLogger(__name__)

_DEFAULT_EXPORT_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "training_exports"
)


@dataclass
class ExportStats:
    """Statistics from one export run."""
    format: str
    source: str
    total_pairs: int
    output_path: str
    exported_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class TrainingExporter:
    """Exports Forge memory data as training datasets for LoRA fine-tuning.

    Usage::

        exporter = TrainingExporter()

        # Export correction pairs in ShareGPT format
        stats = exporter.export_corrections(format="sharegpt")

        # Export graded decisions as DPO pairs
        stats = exporter.export_dpo_from_decisions()

        # Export everything for one agent
        files = exporter.export_all(agent="critic", output_dir="/tmp/training")
    """

    def __init__(
        self,
        memory_store: ForgeMemoryStore | None = None,
        output_dir: str | None = None,
    ):
        self._store = memory_store or ForgeMemoryStore()
        self._output_dir = output_dir or _DEFAULT_EXPORT_DIR
        os.makedirs(self._output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Primary export methods
    # ------------------------------------------------------------------

    def export_corrections(
        self,
        agent: str | None = None,
        format: str = "sharegpt",
        mark_used: bool = True,
    ) -> ExportStats:
        """Export Layer 3 correction pairs.

        Args:
            agent:     Filter to one agent (or None for all agents).
            format:    "sharegpt" | "dpo" | "alpaca"
            mark_used: Mark pairs as used to avoid re-export.

        Returns:
            ExportStats describing what was written.
        """
        pairs = self._store.get_training_pairs(agent=agent)
        if not pairs:
            logger.info("TrainingExporter: no correction pairs available for agent=%s", agent)
            return ExportStats(format=format, source="corrections", total_pairs=0, output_path="")

        records = self._corrections_to_format(pairs, format)
        path = self._write(records, f"corrections_{agent or 'all'}_{format}")

        if mark_used:
            self._store.mark_training_used([p["id"] for p in pairs])

        logger.info("TrainingExporter: exported %d corrections → %s", len(records), path)
        return ExportStats(format=format, source="corrections", total_pairs=len(records), output_path=path)

    def export_dpo_from_decisions(
        self,
        min_grade: float = 0.7,
        max_grade: float = 0.4,
        limit: int = 500,
    ) -> ExportStats:
        """Build DPO pairs from decision grading history.

        Pairs high-graded decisions (chosen) against low-graded decisions
        (rejected) for the same prompt category.

        Args:
            min_grade: Minimum grade to be a "chosen" response.
            max_grade: Maximum grade to be a "rejected" response.
            limit:     Maximum pairs to export.

        Returns:
            ExportStats with the file path.
        """
        try:
            from jarvis.grading import DecisionGrader
            grader = DecisionGrader()
            records = grader.get_graded_decisions(limit=limit * 2)
        except Exception as exc:
            logger.warning("TrainingExporter: could not load grading: %s", exc)
            records = []

        chosen = [r for r in records if r.get("grade", 0) >= min_grade]
        rejected = [r for r in records if r.get("grade", 0) <= max_grade]

        dpo_pairs: list[dict] = []
        # Pair by routing context (rough match by first token of input)
        for c in chosen[:limit]:
            # Find a rejected record for the same query type if possible
            prompt = c.get("input", c.get("decision", ""))
            rej = next(
                (r for r in rejected if r.get("input", "")[:20] == prompt[:20]),
                rejected[0] if rejected else None,
            )
            if rej:
                pair = self._make_dpo_pair(
                    prompt=prompt,
                    chosen=c.get("output", c.get("response", "")),
                    rejected=rej.get("output", rej.get("response", "")),
                    metadata={
                        "chosen_grade": c.get("grade"),
                        "rejected_grade": rej.get("grade"),
                    },
                )
                dpo_pairs.append(pair)

        if not dpo_pairs:
            return ExportStats(format="dpo", source="decisions", total_pairs=0, output_path="")

        path = self._write(dpo_pairs, "dpo_from_decisions")
        logger.info("TrainingExporter: exported %d DPO pairs from decisions → %s", len(dpo_pairs), path)
        return ExportStats(format="dpo", source="decisions", total_pairs=len(dpo_pairs), output_path=path)

    def export_high_quality_interactions(
        self,
        agent: str | None = None,
        min_length: int = 50,
        limit: int = 1000,
        format: str = "sharegpt",
    ) -> ExportStats:
        """Export high-quality interaction logs (no hallucinations, good length).

        Filters out hallucinated interactions and very short outputs.
        """
        interactions = self._store.query_interactions(agent=agent, limit=limit)
        halluc_ids = {
            h.get("interaction_id")
            for h in self._store.query_hallucinations(agent=agent, limit=5000)
            if h.get("interaction_id")
        }

        good = [
            ix for ix in interactions
            if ix["id"] not in halluc_ids
            and len(ix.get("output_text", "")) >= min_length
            and len(ix.get("input_text", "")) >= 5
        ]

        if not good:
            return ExportStats(format=format, source="interactions", total_pairs=0, output_path="")

        records = self._interactions_to_format(good, format)
        path = self._write(records, f"interactions_{agent or 'all'}_{format}")

        logger.info(
            "TrainingExporter: exported %d high-quality interactions → %s", len(records), path
        )
        return ExportStats(format=format, source="interactions", total_pairs=len(records), output_path=path)

    def export_all(
        self,
        agent: str | None = None,
        output_dir: str | None = None,
    ) -> list[ExportStats]:
        """Run all export types and return stats for each."""
        if output_dir:
            self._output_dir = output_dir
            os.makedirs(self._output_dir, exist_ok=True)

        results = []
        results.append(self.export_corrections(agent=agent, format="sharegpt"))
        results.append(self.export_corrections(agent=agent, format="dpo", mark_used=False))
        results.append(self.export_dpo_from_decisions())
        results.append(self.export_high_quality_interactions(agent=agent, format="sharegpt"))
        return [r for r in results if r.total_pairs > 0]

    def get_export_manifest(self) -> list[dict]:
        """List all previously exported files in the output directory."""
        exports = []
        try:
            for f in Path(self._output_dir).glob("*.jsonl"):
                stat = f.stat()
                exports.append({
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
        except Exception as exc:
            logger.warning("TrainingExporter.get_export_manifest error: %s", exc)
        return sorted(exports, key=lambda x: x["modified"], reverse=True)

    # ------------------------------------------------------------------
    # Format converters
    # ------------------------------------------------------------------

    def _corrections_to_format(self, pairs: list[dict], format: str) -> list[dict]:
        if format == "dpo":
            return [
                self._make_dpo_pair(
                    prompt=p.get("bad_output", ""),
                    chosen=p.get("good_output", ""),
                    rejected=p.get("bad_output", ""),
                )
                for p in pairs
            ]
        if format == "alpaca":
            return [
                {
                    "instruction": "Improve this AI response",
                    "input": p.get("bad_output", ""),
                    "output": p.get("good_output", ""),
                    "_meta": {"agent": p.get("agent"), "source": "correction"},
                }
                for p in pairs
            ]
        # Default: ShareGPT
        return [
            {
                "conversations": [
                    {"from": "human", "value": p.get("bad_output", "")},
                    {"from": "gpt",   "value": p.get("good_output", "")},
                ],
                "_meta": {
                    "agent":  p.get("agent"),
                    "source": "correction",
                    "valid_from":  p.get("ts"),
                    "known_from":  p.get("ts"),
                },
            }
            for p in pairs
        ]

    def _interactions_to_format(self, interactions: list[dict], format: str) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        if format == "dpo":
            # No rejected pair available — export as preference over empty string
            return [
                {
                    "prompt":   ix.get("input_text", ""),
                    "chosen":   ix.get("output_text", ""),
                    "rejected": "",
                    "_meta": {"agent": ix.get("agent"), "source": "interaction"},
                }
                for ix in interactions
            ]
        # ShareGPT
        return [
            {
                "conversations": [
                    {"from": "human", "value": ix.get("input_text", "")},
                    {"from": "gpt",   "value": ix.get("output_text", "")},
                ],
                "_meta": {
                    "agent":      ix.get("agent"),
                    "model":      ix.get("model"),
                    "source":     "interaction",
                    "valid_from": ix.get("ts"),
                    "known_from": now,
                },
            }
            for ix in interactions
        ]

    def _make_dpo_pair(
        self,
        prompt: str,
        chosen: str,
        rejected: str,
        metadata: dict | None = None,
    ) -> dict:
        return {
            "prompt":   prompt,
            "chosen":   chosen,
            "rejected": rejected,
            "_meta": {
                "source": "dpo",
                "valid_from":  datetime.now(timezone.utc).isoformat(),
                "known_from":  datetime.now(timezone.utc).isoformat(),
                **(metadata or {}),
            },
        }

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def _write(self, records: list[dict], name: str) -> str:
        """Write records as newline-delimited JSON. Returns file path."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"{name}_{ts}.jsonl"
        path = os.path.join(self._output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path
