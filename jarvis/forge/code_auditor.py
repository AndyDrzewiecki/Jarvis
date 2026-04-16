"""CodeAuditor — Brain 4 of Project Forge.

Reviews proposed code changes and prompt modifications before they are promoted.
Focuses on:
  - Bugs and logic errors
  - Security vulnerabilities (injection, data exposure, insecure defaults)
  - Regressions — does the change break existing behaviour?
  - Style/safety for prompt changes (safe output expectations, bounded completions)

Verdict schema:
    {
      "change_id":   str,
      "change_type": "code" | "prompt",
      "verdict":     "approve" | "reject" | "revise",
      "risk_level":  "low" | "medium" | "high" | "critical",
      "issues":      list[str],
      "suggestions": list[str],
      "reasoning":   str,
    }
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from jarvis.forge.agent_base import BaseDevAgent, TaskResult
from jarvis.forge.memory_store import ForgeMemoryStore
from jarvis.forge.ollama_gateway import forge_generate

logger = logging.getLogger(__name__)

_CODE_AUDIT_PROMPT = """\
You are a senior code reviewer and security auditor.

Change type: {change_type}
Agent/component: {component}

BEFORE (current):
{before}

AFTER (proposed):
{after}

Review this change for:
1. Bugs and logic errors
2. Security vulnerabilities (injection, data exposure, unsafe eval, open redirects)
3. Regressions — behaviour that existing callers rely on and could break
4. For prompt changes: ensure outputs are bounded, safe, and unambiguous

Respond in EXACTLY this format:
VERDICT: approve|reject|revise
RISK: low|medium|high|critical
ISSUES: semicolon-separated list of issues found (or NONE)
SUGGESTIONS: semicolon-separated list of improvements (or NONE)
REASONING: one concise paragraph
"""

_SECURITY_PATTERNS = [
    (re.compile(r"eval\s*\("),                "eval() usage — code injection risk"),
    (re.compile(r"exec\s*\("),                "exec() usage — code injection risk"),
    (re.compile(r"subprocess.*shell\s*=\s*True"), "shell=True subprocess — injection risk"),
    (re.compile(r"password\s*=\s*['\"][^'\"]+['\"]"), "hardcoded credential"),
    (re.compile(r"secret\s*=\s*['\"][^'\"]+['\"]"),   "hardcoded secret"),
    (re.compile(r"os\.system\s*\("),          "os.system() — prefer subprocess"),
    (re.compile(r"pickle\.loads?\s*\("),      "pickle deserialization — arbitrary code execution"),
    (re.compile(r"yaml\.load\s*\([^)]*\)(?!.*Loader)"), "unsafe yaml.load() — use safe_load()"),
    (re.compile(r"SQL.*%[sd]"),               "possible SQL string formatting — use parameters"),
    (re.compile(r"\.format\(.*request\b"),    "string format with request data — XSS/injection risk"),
]


@dataclass
class AuditVerdict:
    """The CodeAuditor's judgment on one proposed change."""
    change_id: str
    change_type: str           # code | prompt
    component: str
    verdict: str               # approve | reject | revise
    risk_level: str            # low | medium | high | critical
    issues: list[str]
    suggestions: list[str]
    reasoning: str
    static_flags: list[str] = field(default_factory=list)  # from pattern scanner


class CodeAuditor(BaseDevAgent):
    """Brain 4 — security and quality gate for proposed changes.

    Usage::

        auditor = CodeAuditor()
        verdict = auditor.audit(
            change_id="fix-001",
            change_type="code",
            component="critic.py",
            before="def foo(): return eval(input())",
            after="def foo(): return safe_parse(input())",
        )
        print(verdict.verdict, verdict.risk_level, verdict.issues)
    """

    name = "code_auditor"
    model = "qwen2.5:0.5b"

    def __init__(self, memory_store: ForgeMemoryStore | None = None):
        super().__init__(memory_store)
        self._verdicts: list[AuditVerdict] = []

    # ------------------------------------------------------------------
    # Primary interface
    # ------------------------------------------------------------------

    def audit(
        self,
        change_id: str,
        change_type: str,
        component: str,
        before: str,
        after: str,
    ) -> AuditVerdict:
        """Audit a single proposed change.

        Args:
            change_id:   Unique identifier for this change.
            change_type: "code" or "prompt".
            component:   File name or agent name being changed.
            before:      Current content/prompt text.
            after:       Proposed content/prompt text.

        Returns:
            AuditVerdict with verdict, risk level, issues, and suggestions.
        """
        # Static pattern scan (fast, deterministic)
        static_flags = self._static_scan(after)

        # Escalate risk immediately for critical static flags
        critical_patterns = {"eval() usage", "exec() usage", "pickle deserialization"}
        has_critical = any(any(p in f for p in critical_patterns) for f in static_flags)

        prompt = _CODE_AUDIT_PROMPT.format(
            change_type=change_type,
            component=component,
            before=before[:800],
            after=after[:800],
        )

        try:
            raw = forge_generate(prompt, agent=self.name)
            verdict = self._parse_verdict(raw, change_id, change_type, component)
        except Exception as exc:
            logger.warning("CodeAuditor LLM error: %s", exc)
            verdict = AuditVerdict(
                change_id=change_id,
                change_type=change_type,
                component=component,
                verdict="revise",
                risk_level="medium",
                issues=["LLM unavailable — manual review required"],
                suggestions=[],
                reasoning="Could not obtain LLM verdict; defaulting to revise.",
            )

        verdict.static_flags = static_flags

        # Override verdict if critical static flags found
        if has_critical and verdict.verdict == "approve":
            verdict.verdict = "reject"
            verdict.risk_level = "critical"
            verdict.issues = static_flags + verdict.issues

        self._verdicts.append(verdict)

        # Log to memory
        self._store.log_interaction(
            agent=self.name,
            task_id=change_id,
            input_text=f"audit:{change_type}:{component}",
            output_text=(
                f"verdict={verdict.verdict} risk={verdict.risk_level}"
                f" issues={len(verdict.issues)} static_flags={len(static_flags)}"
            ),
            model=self.model,
        )

        logger.info(
            "CodeAuditor: %s → verdict=%s risk=%s issues=%d static_flags=%d",
            component, verdict.verdict, verdict.risk_level, len(verdict.issues), len(static_flags),
        )
        return verdict

    def audit_prompt_versions(self, agent: str | None = None) -> list[AuditVerdict]:
        """Audit all unaudited staged prompt versions in the store."""
        from jarvis.forge.memory_store import _open as _db_open
        try:
            conn = _db_open(self._store._db)
            query = "SELECT * FROM prompt_versions WHERE prompt_text LIKE '%[STAGED FIX]%'"
            params: list = []
            if agent:
                query += " AND agent = ?"
                params.append(agent)
            rows = conn.execute(query, params).fetchall()
            conn.close()
        except Exception as exc:
            logger.warning("CodeAuditor.audit_prompt_versions DB error: %s", exc)
            return []

        verdicts = []
        for row in rows:
            d = dict(row)
            v = self.audit(
                change_id=f"prompt_v{d['version']}",
                change_type="prompt",
                component=d["agent"],
                before="(previous prompt version)",
                after=d.get("prompt_text", ""),
            )
            verdicts.append(v)
        return verdicts

    def get_verdicts(self, verdict_filter: str | None = None) -> list[AuditVerdict]:
        """Return all verdicts this session, optionally filtered by verdict value."""
        if verdict_filter:
            return [v for v in self._verdicts if v.verdict == verdict_filter]
        return list(self._verdicts)

    def summary(self) -> dict[str, Any]:
        total = len(self._verdicts)
        by_verdict: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        for v in self._verdicts:
            by_verdict[v.verdict] = by_verdict.get(v.verdict, 0) + 1
            by_risk[v.risk_level] = by_risk.get(v.risk_level, 0) + 1
        return {
            "total_audits": total,
            "by_verdict": by_verdict,
            "by_risk": by_risk,
            "critical_count": by_risk.get("critical", 0),
        }

    # ------------------------------------------------------------------
    # BaseDevAgent interface
    # ------------------------------------------------------------------

    def execute_task(self, task: dict) -> TaskResult:
        payload = task.get("payload", {})
        task_type = task.get("type", "audit")

        if task_type == "audit":
            verdict = self.audit(
                change_id=payload.get("change_id", task["id"]),
                change_type=payload.get("change_type", "code"),
                component=payload.get("component", "unknown"),
                before=payload.get("before", ""),
                after=payload.get("after", ""),
            )
            approved = verdict.verdict == "approve"
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"verdict={verdict.verdict} risk={verdict.risk_level} issues={len(verdict.issues)}",
                confidence=0.9 if approved else 0.4,
                metadata={
                    "verdict": verdict.verdict,
                    "risk_level": verdict.risk_level,
                    "issues": verdict.issues,
                    "suggestions": verdict.suggestions,
                    "static_flags": verdict.static_flags,
                },
            )

        if task_type == "audit_prompts":
            verdicts = self.audit_prompt_versions(agent=payload.get("agent"))
            approved = sum(1 for v in verdicts if v.verdict == "approve")
            return TaskResult(
                task_id=task["id"],
                agent=self.name,
                status="success",
                output=f"audited={len(verdicts)} approved={approved}",
                confidence=0.8,
            )

        return TaskResult(
            task_id=task["id"], agent=self.name,
            status="failure", output="", error=f"Unknown task type: {task_type}",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _static_scan(self, code: str) -> list[str]:
        """Run deterministic pattern scan for common security issues."""
        flags = []
        for pattern, description in _SECURITY_PATTERNS:
            if pattern.search(code):
                flags.append(description)
        return flags

    def _parse_verdict(
        self, raw: str, change_id: str, change_type: str, component: str
    ) -> AuditVerdict:
        lines: dict[str, str] = {}
        for line in raw.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                lines[k.strip().upper()] = v.strip()

        verdict_raw = lines.get("VERDICT", "revise").lower()
        verdict = verdict_raw if verdict_raw in {"approve", "reject", "revise"} else "revise"

        risk_raw = lines.get("RISK", "medium").lower()
        risk = risk_raw if risk_raw in {"low", "medium", "high", "critical"} else "medium"

        issues_raw = lines.get("ISSUES", "NONE")
        issues = (
            []
            if issues_raw.upper() == "NONE"
            else [i.strip() for i in issues_raw.split(";") if i.strip()]
        )

        suggestions_raw = lines.get("SUGGESTIONS", "NONE")
        suggestions = (
            []
            if suggestions_raw.upper() == "NONE"
            else [s.strip() for s in suggestions_raw.split(";") if s.strip()]
        )

        reasoning = lines.get("REASONING", "No reasoning provided.")

        return AuditVerdict(
            change_id=change_id,
            change_type=change_type,
            component=component,
            verdict=verdict,
            risk_level=risk,
            issues=issues,
            suggestions=suggestions,
            reasoning=reasoning,
        )
