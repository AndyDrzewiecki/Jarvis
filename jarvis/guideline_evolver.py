from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GuidelineUpdate:
    """Result of one guideline evolution cycle."""
    domain: str
    old_version: int
    new_version: int
    changes_summary: str
    patterns_analyzed: int
    corrective_count: int
    reinforcement_count: int


class GuidelineEvolver:
    """Reads decision grades → rewrites specialist operating guidelines.

    Guidelines are markdown files at {library_root}/{domain}/guidelines.md.
    Analyzes graded decisions, clusters patterns, rewrites guidelines with provenance.
    """

    def __init__(self, library_root: str | None = None):
        from jarvis import config
        self._root = library_root or os.path.join(config.DATA_DIR, "library")

    def evolve(self, domain: str) -> GuidelineUpdate:
        """Analyze graded decisions for domain → rewrite guidelines."""
        current_text, current_version = self._load_guidelines(domain)

        from jarvis import agent_memory
        decisions = agent_memory.query(agent=f"{domain}_specialist", limit=100)
        grades = []
        for d in decisions:
            grade = agent_memory.get_grade(d["id"])
            if grade:
                grades.append({"decision": d, "grade": grade})

        if not grades:
            return GuidelineUpdate(
                domain=domain, old_version=current_version,
                new_version=current_version, changes_summary="No graded decisions to analyze",
                patterns_analyzed=0, corrective_count=0, reinforcement_count=0,
            )

        poor = [g for g in grades if g["grade"].get("short_term_grade") == "poor"
                or g["grade"].get("long_term_grade") == "poor"]
        good = [g for g in grades if g["grade"].get("short_term_grade") == "good"
                or g["grade"].get("long_term_grade") == "good"]

        corrective_guidelines = []
        for pattern in poor[:5]:
            corrective = self._draft_corrective_guideline(pattern, domain)
            if corrective:
                corrective_guidelines.append(corrective)

        reinforcement_guidelines = []
        for pattern in good[:5]:
            reinforcement = self._draft_reinforcement_guideline(pattern, domain)
            if reinforcement:
                reinforcement_guidelines.append(reinforcement)

        new_text = self._merge_guidelines(
            current_text, corrective_guidelines, reinforcement_guidelines, domain
        )

        new_version = current_version + 1
        self._save_guidelines(domain, new_text, new_version)

        summary = (f"{len(corrective_guidelines)} corrective + "
                   f"{len(reinforcement_guidelines)} reinforcement guidelines merged")

        agent_memory.log_decision(
            agent="guideline_evolver",
            capability="evolve",
            decision=f"Evolved {domain} guidelines v{current_version}→v{new_version}: {summary}",
            reasoning=f"Analyzed {len(grades)} graded decisions",
            outcome="success",
        )

        return GuidelineUpdate(
            domain=domain, old_version=current_version, new_version=new_version,
            changes_summary=summary, patterns_analyzed=len(grades),
            corrective_count=len(corrective_guidelines),
            reinforcement_count=len(reinforcement_guidelines),
        )

    def _load_guidelines(self, domain: str) -> tuple[str, int]:
        """Load guidelines markdown and version number. Returns ('', 0) if none."""
        path = os.path.join(self._root, domain, "guidelines.md")
        if not os.path.exists(path):
            return "", 0
        try:
            with open(path, "r") as f:
                text = f.read()
            version = 0
            first_line = text.split("\n")[0] if text else ""
            if first_line.startswith("# ") and " v" in first_line:
                try:
                    version = int(first_line.split(" v")[-1])
                except ValueError:
                    pass
            return text, version
        except Exception:
            return "", 0

    def _save_guidelines(self, domain: str, text: str, version: int) -> None:
        """Save guidelines with version header."""
        dir_path = os.path.join(self._root, domain)
        os.makedirs(dir_path, exist_ok=True)
        if not text.startswith(f"# {domain.title()} Specialist Guidelines v{version}"):
            text = f"# {domain.title()} Specialist Guidelines v{version}\n\n{text}"
        path = os.path.join(dir_path, "guidelines.md")
        with open(path, "w") as f:
            f.write(text)

    def _draft_corrective_guideline(self, pattern: dict, domain: str) -> str | None:
        """Use LLM to draft a corrective guideline from a failure pattern."""
        decision = pattern["decision"]
        grade = pattern["grade"]
        prompt = (
            f"You are improving the {domain} specialist's operating guidelines.\n\n"
            f"This decision was graded as POOR:\n"
            f"Decision: {decision.get('decision', '')[:300]}\n"
            f"Reasoning: {decision.get('reasoning', '')[:200]}\n"
            f"Grade reason: {grade.get('short_term_reason', grade.get('long_term_reason', ''))[:200]}\n\n"
            "Write ONE corrective guideline (1-2 sentences) that would prevent this failure.\n"
            "Start with 'AVOID:' or 'WHEN ... THEN:'\nGuideline:"
        )
        try:
            from jarvis.core import _ask_ollama
            from jarvis import config
            result = _ask_ollama(prompt, model=config.FALLBACK_MODEL)
            line = result.strip().split("\n")[0].strip()
            return line if line else None
        except Exception:
            return None

    def _draft_reinforcement_guideline(self, pattern: dict, domain: str) -> str | None:
        """Use LLM to draft a reinforcement guideline from a success pattern."""
        decision = pattern["decision"]
        grade = pattern["grade"]
        prompt = (
            f"You are improving the {domain} specialist's operating guidelines.\n\n"
            f"This decision was graded as GOOD:\n"
            f"Decision: {decision.get('decision', '')[:300]}\n"
            f"Reasoning: {decision.get('reasoning', '')[:200]}\n"
            f"Grade reason: {grade.get('short_term_reason', grade.get('long_term_reason', ''))[:200]}\n\n"
            "Write ONE reinforcement guideline (1-2 sentences) to keep doing this.\n"
            "Start with 'PREFER:' or 'CONTINUE:'\nGuideline:"
        )
        try:
            from jarvis.core import _ask_ollama
            from jarvis import config
            result = _ask_ollama(prompt, model=config.FALLBACK_MODEL)
            line = result.strip().split("\n")[0].strip()
            return line if line else None
        except Exception:
            return None

    def _merge_guidelines(self, current: str, correctives: list[str],
                          reinforcements: list[str], domain: str) -> str:
        """Use LLM to merge new guidelines into existing text. Falls back to append."""
        if not correctives and not reinforcements:
            return current
        new_items = [f"CORRECTIVE: {c}" for c in correctives] + [f"REINFORCEMENT: {r}" for r in reinforcements]
        new_block = "\n".join(new_items)
        prompt = (
            f"You are editing the {domain} specialist's operating guidelines.\n\n"
            f"Current guidelines:\n{current[:2000]}\n\n"
            f"New items to integrate:\n{new_block}\n\n"
            "Rewrite the guidelines to incorporate these new items.\n"
            "Remove any contradicted old guidelines. Keep it concise (under 1000 words).\n"
            "Output ONLY the new guideline text, no preamble.\n"
        )
        try:
            from jarvis.core import _ask_ollama
            from jarvis import config
            result = _ask_ollama(prompt, model=config.FALLBACK_MODEL)
            return result.strip()
        except Exception:
            return current + "\n\n## Recent Updates\n\n" + new_block
