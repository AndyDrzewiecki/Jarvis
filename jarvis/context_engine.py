from __future__ import annotations
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ContextEngine:
    """Self-improving prompt context for a specialist.

    Builds context blocks combining: domain KB facts, decision patterns,
    guidelines, household state, cross-domain facts.
    Stored at {library_root}/{domain}/context_engine.md.
    """

    def __init__(self, library_root: str | None = None):
        from jarvis import config
        self._root = library_root or os.path.join(config.DATA_DIR, "library")

    def rebuild(self, domain: str) -> str:
        """Full rebuild of domain context from all sources. Returns generated text."""
        sections = []

        guidelines = self._load_file(domain, "guidelines.md")
        if guidelines:
            sections.append(f"## Operating Guidelines\n{guidelines[:1500]}")

        try:
            from jarvis.knowledge_lake import KnowledgeLake
            lake = KnowledgeLake()
            facts = lake.query_facts(domain=domain, limit=30)
            if facts:
                fact_lines = [f"- {f.get('summary', f.get('content', ''))[:150]}" for f in facts[:15]]
                sections.append("## Domain Knowledge\n" + "\n".join(fact_lines))
        except Exception as exc:
            logger.warning("context_engine.rebuild: KB query failed for %s: %s", domain, exc)

        try:
            from jarvis import agent_memory
            decisions = agent_memory.query(agent=f"{domain}_specialist", limit=20)
            good = [d for d in decisions if d.get("outcome") == "success"]
            poor = [d for d in decisions if d.get("outcome") == "failure"]
            if good or poor:
                pattern_lines = []
                if good:
                    pattern_lines.append(f"Recent successes: {len(good)}")
                    for d in good[:3]:
                        pattern_lines.append(f"  + {d.get('decision', '')[:120]}")
                if poor:
                    pattern_lines.append(f"Recent failures: {len(poor)}")
                    for d in poor[:3]:
                        pattern_lines.append(f"  - {d.get('decision', '')[:120]}")
                sections.append("## Decision Patterns\n" + "\n".join(pattern_lines))
        except Exception:
            pass

        try:
            from jarvis.household_state import HouseholdState
            state = HouseholdState()
            current = state.current()
            state_text = f"Primary: {current['primary']}"
            if current.get("modifiers"):
                state_text += f"\nModifiers: {', '.join(current['modifiers'])}"
            sections.append(f"## Household State\n{state_text}")
        except Exception:
            pass

        try:
            from jarvis.knowledge_lake import KnowledgeLake
            lake = KnowledgeLake()
            cross = lake.recent_by_domain(limit_per_domain=2)
            cross_lines = []
            for d, facts in cross.items():
                if d != domain and facts:
                    for f in facts[:2]:
                        cross_lines.append(f"- [{d}] {f.get('summary', '')[:120]}")
            if cross_lines:
                sections.append("## Cross-Domain Context\n" + "\n".join(cross_lines))
        except Exception:
            pass

        # 6. Learned preferences
        try:
            from jarvis.preference_learning import PreferenceMiner
            miner = PreferenceMiner()
            prefs = miner.get_preferences(domain=domain, min_confidence=0.5)
            if prefs:
                pref_lines = [f"- {p['rule']} (confidence: {p['confidence']:.2f})" for p in prefs[:10]]
                sections.append("## Learned Preferences\n" + "\n".join(pref_lines))
        except Exception:
            pass

        context_text = "\n\n".join(sections)
        self._save_file(domain, "context_engine.md", context_text)

        from jarvis import agent_memory
        agent_memory.log_decision(
            agent="context_engine",
            capability="rebuild",
            decision=f"Context rebuilt for {domain}: {len(sections)} sections, {len(context_text)} chars",
            reasoning="Weekly scheduled rebuild",
            outcome="success",
        )

        return context_text

    def patch(self, domain: str, section: str, update: str) -> None:
        """Patch a specific section of the context document."""
        current = self._load_file(domain, "context_engine.md") or ""
        marker = f"## {section}"
        if marker in current:
            parts = current.split(marker)
            if len(parts) > 1:
                rest = parts[1]
                next_section = rest.find("\n## ")
                if next_section >= 0:
                    current = parts[0] + marker + "\n" + update + rest[next_section:]
                else:
                    current = parts[0] + marker + "\n" + update
        else:
            current += f"\n\n{marker}\n{update}"
        self._save_file(domain, "context_engine.md", current)

    def inject(self, domain: str, base_prompt: str, token_budget: int = 3000) -> str:
        """Inject context into a specialist LLM prompt, respecting token budget."""
        context = self._load_file(domain, "context_engine.md")
        if not context:
            return base_prompt
        char_budget = token_budget * 4
        if len(context) > char_budget:
            context = context[:char_budget] + "\n[...context truncated...]"
        return f"{base_prompt}\n\n--- DOMAIN CONTEXT ---\n{context}\n--- END CONTEXT ---\n"

    def _load_file(self, domain: str, filename: str) -> str:
        """Load a file from the library wing."""
        path = os.path.join(self._root, domain, filename)
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return f.read()
        except Exception:
            pass
        return ""

    def _save_file(self, domain: str, filename: str, content: str) -> None:
        """Save a file to the library wing."""
        dir_path = os.path.join(self._root, domain)
        os.makedirs(dir_path, exist_ok=True)
        with open(os.path.join(dir_path, filename), "w") as f:
            f.write(content)
