"""
BriefEngine — assembles a cross-adapter morning digest.

Calls all live adapters, synthesises their outputs through the LLM, and
returns a prioritised narrative. Adapters that are down are skipped
gracefully; the brief notes which are unavailable.

Results are stored in data/briefs.jsonl and pushed via jarvis.notifier.

Usage:
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    result = engine.generate()
    # result = {"text": "...", "sections": [...], "unavailable": [...], "timestamp": "..."}

API endpoint: GET /api/brief
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from typing import Any

import jarvis.agent_memory as agent_memory
import jarvis.notifier as notifier

BRIEFS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "briefs.jsonl")

# Ordered list of (adapter_name, capability) to query for the brief.
# Weather is included when preferences.brief_include_weather is True (default).
_BRIEF_SOURCES_BASE = [
    ("investor", "daily_brief"),
    ("summerpuppy", "dashboard_summary"),
    ("homeops_grocery", "dashboard"),
    ("grocery", "shopping_list"),
]

_BRIEF_SOURCES = _BRIEF_SOURCES_BASE  # kept for backwards compatibility


def _get_brief_sources() -> list[tuple[str, str]]:
    """Return the ordered list of brief sources, inserting weather if enabled."""
    try:
        from jarvis.preferences import get as prefs_get
        include_weather = prefs_get("brief_include_weather", True)
    except Exception:
        include_weather = True
    if not include_weather:
        return _BRIEF_SOURCES_BASE
    # Insert weather after investor (index 1)
    sources = list(_BRIEF_SOURCES_BASE)
    sources.insert(1, ("weather", "current"))
    return sources


class BriefEngine:
    """Assemble a morning brief from all live adapters."""

    def __init__(self) -> None:
        from jarvis.adapters import ALL_ADAPTERS
        self._adapter_map = {a.name: a for a in ALL_ADAPTERS}

    def generate(self) -> dict[str, Any]:
        """
        Collect adapter data, synthesise through LLM, push to Discord, and
        store the result. Returns a dict with keys:
          text, sections (list of adapter names used), unavailable, timestamp.
        """
        sections: dict[str, str] = {}
        unavailable: list[str] = []

        for adapter_name, capability in _get_brief_sources():
            adapter = self._adapter_map.get(adapter_name)
            if adapter is None:
                unavailable.append(adapter_name)
                continue
            result = adapter.safe_run(capability, {})
            if result.success:
                sections[adapter_name] = result.text
            else:
                unavailable.append(adapter_name)

        text = self._synthesize(sections, unavailable)

        agent_memory.log_decision(
            agent="brief_engine",
            capability="generate",
            decision="Morning brief generated",
            reasoning=f"Adapters used: {list(sections.keys())}; unavailable: {unavailable}",
            outcome="success" if sections else "failure",
        )

        now = datetime.now()
        notifier.notify(text, title=f"Jarvis Morning Brief — {now.strftime('%A, %B')} {now.day}")

        self._store(text, list(sections.keys()), unavailable)

        return {
            "text": text,
            "sections": list(sections.keys()),
            "unavailable": unavailable,
            "timestamp": datetime.now().isoformat(),
        }

    def _synthesize(self, sections: dict[str, str], unavailable: list[str]) -> str:
        """Ask the LLM to write a unified, prioritised narrative from adapter data."""
        if not sections:
            parts = ["Good morning. All monitored services are currently unavailable."]
            if unavailable:
                parts.append(f"Unavailable: {', '.join(unavailable)}.")
            return " ".join(parts)

        context = "\n\n".join(
            f"[{name.upper()}]\n{text}" for name, text in sections.items()
        )
        unavail_note = (
            f"\n\nNote: These services are unavailable: {', '.join(unavailable)}."
            if unavailable
            else ""
        )

        prompt = (
            "You are Jarvis, a personal AI assistant. Write a concise morning brief "
            "from the system data below. Be direct and prioritised — lead with what "
            "needs attention. Do not just repeat the data; synthesise it into an "
            "opinionated, actionable narrative."
            f"{unavail_note}\n\n"
            f"<system_data>\n{context}\n</system_data>\n\n"
            "Write the morning brief now:"
        )

        try:
            from jarvis.core import _ask_ollama
            return _ask_ollama(prompt)
        except Exception:
            # Fallback: plain concatenation
            lines = ["Good morning. Here is your status update:"]
            for name, text in sections.items():
                lines.append(f"\n{name.upper()}: {text}")
            if unavailable:
                lines.append(f"\nUnavailable services: {', '.join(unavailable)}")
            return "\n".join(lines)

    def _store(self, text: str, sections: list[str], unavailable: list[str]) -> None:
        """Append brief to data/briefs.jsonl for history."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "sections": sections,
            "unavailable": unavailable,
        }
        try:
            os.makedirs(os.path.dirname(os.path.abspath(BRIEFS_PATH)), exist_ok=True)
            with open(BRIEFS_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass
