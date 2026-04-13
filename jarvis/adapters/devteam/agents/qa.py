"""
QAAgent — static code review that outputs structured JSON.

Output (ONLY valid JSON):
  {"pass": bool, "issues": ["issue1", ...], "fix_instructions": "..."}

Fails if: no tests exist, obvious syntax errors, missing imports, or known bugs.
"""
from __future__ import annotations
import json
import re

import jarvis.adapters.devteam.config as _cfg
import jarvis.agent_memory as _am

_SYSTEM = """\
You are a senior QA engineer performing a static code review.

You will be given Python source files. Review them carefully.

Respond with ONLY valid JSON — no markdown, no explanation, nothing else:
{"pass": <true|false>, "issues": ["<issue1>", "<issue2>", ...], "fix_instructions": "<what to fix>"}

FAIL the review if ANY of these are true:
- No test file exists
- A test file exists but has no test functions (def test_*)
- An import references a module that does not exist in the file list
- There are obvious Python syntax errors
- A required function/class from the design is missing

PASS if all imports resolve, at least one test function exists, and no obvious bugs.
fix_instructions must be empty string "" when passing.
"""


def _parse_qa_json(raw: str) -> dict:
    """Extract and parse the JSON from QA output. Returns failure dict on parse error."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {
            "pass": False,
            "issues": ["QA agent returned non-JSON output"],
            "fix_instructions": "Ensure output is valid JSON with keys: pass, issues, fix_instructions",
        }
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        return {
            "pass": False,
            "issues": [f"QA agent JSON parse error: {e}"],
            "fix_instructions": "Output must be valid JSON",
        }


class QAAgent:
    def review(self, files: dict[str, str], task: str) -> dict:
        """
        Review the provided files. Returns:
          {"pass": bool, "issues": list[str], "fix_instructions": str}
        """
        file_listing = "\n\n".join(
            f"# FILE: {fname}\n```python\n{content}\n```"
            for fname, content in files.items()
        )
        prompt = (
            f"{_SYSTEM}\n\n"
            f"## Original Task\n{task}\n\n"
            f"## Files to Review\n{file_listing}\n\n"
            f"## Your JSON Review"
        )

        raw = _cfg._ask_ollama(prompt)
        result = _parse_qa_json(raw)

        passed = bool(result.get("pass"))
        _am.log_decision(
            agent="devteam.qa",
            capability="review",
            decision=f"QA {'PASS' if passed else 'FAIL'} for: {task[:60]}",
            reasoning=f"Issues: {result.get('issues', [])}",
            outcome="success" if passed else "failure",
            params_summary=f"files={list(files.keys())}",
        )
        return result
