"""
ArchitectAgent — turns a task description into a concrete design document.

Output: markdown text with sections:
  ## Overview, ## File Structure, ## Key Classes/Functions, ## Test Strategy

Uses real file/class names — not abstract placeholders.
"""
from __future__ import annotations
import jarvis.adapters.devteam.config as _cfg
import jarvis.agent_memory as _am

_SYSTEM = """\
You are a senior software architect. Given a task, produce a CONCRETE design document.

Your output MUST contain these markdown sections:
## Overview
One paragraph describing what the software does and why.

## File Structure
List every file with a one-line description. Use real filenames, not placeholders.

## Key Classes/Functions
For each file: list the classes/functions with their signatures and a sentence on purpose.

## Test Strategy
List the specific test cases (function names) and what each verifies.

Be specific. Use real Python names. No hand-wavy descriptions.
"""


class ArchitectAgent:
    def generate_design(self, task: str) -> str:
        """Return a markdown design document for the given task."""
        prompt = f"{_SYSTEM}\n\n## Task\n{task}\n\n## Design Document"
        raw = _cfg._ask_ollama(prompt)
        _am.log_decision(
            agent="devteam.architect",
            capability="generate_design",
            decision=f"Generated design for: {task[:80]}",
            reasoning=raw[:500],
            outcome="success",
        )
        return raw
