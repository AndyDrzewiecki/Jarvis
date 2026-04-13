"""
DeveloperAgent — turns a design doc into actual Python source files.

Output format (strict):
  # FILE: path/to/file.py
  ```python
  ...code...
  ```

  # FILE: tests/test_something.py
  ```python
  ...tests...
  ```

Allowed dependencies: stdlib + fastapi, pydantic, requests, sqlalchemy, pytest.
All code must include type hints and docstrings.
"""
from __future__ import annotations
import re
from typing import Optional

import jarvis.adapters.devteam.config as _cfg
import jarvis.agent_memory as _am

_SYSTEM = """\
You are a senior Python developer. Given a design document and task, write the complete implementation.

STRICT OUTPUT FORMAT — use ONLY this format, nothing else:
# FILE: <relative/path/to/file.py>
```python
<complete file contents>
```

Rules:
- Include ALL files listed in the design (source + tests).
- Use only: stdlib, fastapi, pydantic, requests, sqlalchemy, pytest.
- Every function/class must have type hints and a docstring.
- Tests must use pytest. Import from the source module directly.
- Do NOT include any explanation outside of code blocks.
"""


def _parse_code_files(llm_output: str) -> dict[str, str]:
    """Parse LLM output into {filename: code_content} dict."""
    files: dict[str, str] = {}
    pattern = r"#\s*FILE:\s*(.+?)\n```(?:python)?\n(.*?)```"
    for match in re.finditer(pattern, llm_output, re.DOTALL):
        filename = match.group(1).strip()
        code = match.group(2).rstrip()
        if filename:
            files[filename] = code
    return files


class DeveloperAgent:
    def generate_code(
        self,
        design_doc: str,
        task: str,
        fix_instructions: str = "",
        existing_files: Optional[dict[str, str]] = None,
        iteration: int = 1,
    ) -> dict[str, str]:
        """Return {filename: code} for the given design and task."""
        fix_section = ""
        if fix_instructions:
            fix_section = f"\n\n## QA Fix Instructions (iteration {iteration})\n{fix_instructions}"

        existing_section = ""
        if existing_files:
            snippets = []
            for fname, content in existing_files.items():
                snippets.append(f"# FILE: {fname}\n```python\n{content}\n```")
            existing_section = "\n\n## Existing Files (fix these)\n" + "\n\n".join(snippets)

        prompt = (
            f"{_SYSTEM}\n\n"
            f"## Task\n{task}\n\n"
            f"## Design Document\n{design_doc}"
            f"{fix_section}"
            f"{existing_section}\n\n"
            f"## Implementation"
        )

        raw = _cfg._ask_ollama(prompt)
        files = _parse_code_files(raw)

        _am.log_decision(
            agent="devteam.developer",
            capability="generate_code",
            decision=f"Generated {len(files)} file(s) on iteration {iteration} for: {task[:60]}",
            reasoning=f"Files: {list(files.keys())}",
            outcome="success" if files else "failure",
            params_summary=f"iteration={iteration}, fix={bool(fix_instructions)}",
        )
        return files
