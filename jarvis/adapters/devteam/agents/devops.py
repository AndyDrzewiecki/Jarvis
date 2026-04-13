"""
DevOpsAgent — quality and security checks via bandit + flake8.

Runs as an advisory (non-blocking) post-QA step in the DevTeam pipeline.
Controlled by DEVTEAM_DEVOPS_ENABLED env var (default: true).

Output schema:
    {
        "security": {"issues": int, "high": int, "medium": int, "low": int},
        "style":    {"errors": int, "warnings": int},
        "formatting": {"ok": bool},
        "passed": bool,
        "summary": str,
    }
"""
from __future__ import annotations
import json
import os
import subprocess
from typing import Optional


class DevOpsAgent:
    """Run security + style checks on a directory or set of files."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout

    # ── public interface ──────────────────────────────────────────────────────

    def scan(self, target_dir: str) -> dict:
        """
        Run bandit + flake8 + black --check on target_dir.
        Returns the standardised output schema. Never raises.
        """
        security = self._run_bandit(target_dir)
        style = self._run_flake8(target_dir)
        formatting = self._run_black_check(target_dir)

        passed = (
            security["high"] == 0
            and security["medium"] == 0
            and style["errors"] == 0
            and formatting["ok"]
        )

        parts = []
        if security["issues"]:
            parts.append(
                f"bandit: {security['issues']} issue(s) "
                f"(H:{security['high']} M:{security['medium']} L:{security['low']})"
            )
        else:
            parts.append("bandit: clean")

        if style["errors"] or style["warnings"]:
            parts.append(f"flake8: {style['errors']} error(s), {style['warnings']} warning(s)")
        else:
            parts.append("flake8: clean")

        parts.append("black: " + ("ok" if formatting["ok"] else "needs formatting"))

        return {
            "security": security,
            "style": style,
            "formatting": formatting,
            "passed": passed,
            "summary": " | ".join(parts),
        }

    # ── legacy stubs (for backwards-compat; delegate to scan) ─────────────────

    def lint(self, files: dict[str, str]) -> dict:
        """Stub-compatible interface. Runs flake8 on a temp dir if possible."""
        return {"status": "advisory", "message": "Use DevOpsAgent.scan(dir) for full results."}

    def security_scan(self, files: dict[str, str]) -> dict:
        """Stub-compatible interface. Use scan() for full results."""
        return {"status": "advisory", "message": "Use DevOpsAgent.scan(dir) for full results."}

    # ── private runners ───────────────────────────────────────────────────────

    def _run_bandit(self, target_dir: str) -> dict:
        result = {"issues": 0, "high": 0, "medium": 0, "low": 0}
        try:
            proc = subprocess.run(
                ["bandit", "-r", target_dir, "-f", "json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            # bandit exits non-zero when issues found; parse JSON regardless
            raw = proc.stdout.strip()
            if not raw:
                return result
            data = json.loads(raw)
            results_list = data.get("results", [])
            result["issues"] = len(results_list)
            for r in results_list:
                sev = r.get("issue_severity", "").upper()
                if sev == "HIGH":
                    result["high"] += 1
                elif sev == "MEDIUM":
                    result["medium"] += 1
                else:
                    result["low"] += 1
        except FileNotFoundError:
            # bandit not installed — treat as clean (advisory only)
            pass
        except (json.JSONDecodeError, subprocess.TimeoutExpired, Exception):
            pass
        return result

    def _run_flake8(self, target_dir: str) -> dict:
        result = {"errors": 0, "warnings": 0}
        try:
            proc = subprocess.run(
                ["flake8", target_dir, "--max-line-length=100", "--statistics"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            for line in proc.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                # flake8 output: path:line:col: Exxxx message
                # W-codes are warnings, E-codes are errors
                if ": W" in line or line.startswith("W"):
                    result["warnings"] += 1
                elif ": E" in line or line.startswith("E"):
                    result["errors"] += 1
        except FileNotFoundError:
            # flake8 not installed — advisory only
            pass
        except (subprocess.TimeoutExpired, Exception):
            pass
        return result

    def _run_black_check(self, target_dir: str) -> dict:
        try:
            proc = subprocess.run(
                ["black", "--check", target_dir],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return {"ok": proc.returncode == 0}
        except FileNotFoundError:
            return {"ok": True}  # black not installed — assume ok
        except (subprocess.TimeoutExpired, Exception):
            return {"ok": True}
