"""
DevTeamAdapter — local unicorn-team that builds software using Ollama.

Pipeline: Architect → Developer → QA (up to MAX_ITERATIONS retries).
All generated code lands in jarvis/adapters/devteam/artifacts/{slug}/.

Capabilities:
  build_app      — full Architect → Developer → QA loop
  write_feature  — Developer → QA loop (no Architect; caller provides context)
  review_code    — QA only (read-only, no writes)
  run_tests      — pytest only via CommandTool
  design         — Architect only, returns design doc as text
"""
from __future__ import annotations
import os
import re
from typing import Any, Optional

import jarvis.agent_memory as _am
from jarvis.adapters.base import BaseAdapter, AdapterResult
from jarvis.adapters.devteam.config import MAX_ITERATIONS, ARTIFACTS_DIR, DEVTEAM_DEVOPS_ENABLED
from jarvis.adapters.devteam.agents import ArchitectAgent, DeveloperAgent, QAAgent
from jarvis.adapters.devteam.agents.devops import DevOpsAgent
from jarvis.adapters.devteam.tools import FileTool, CommandTool


def _slugify(text: str, max_len: int = 30) -> str:
    slug = re.sub(r"[^\w]", "_", text[:max_len]).strip("_").lower()
    return slug or "project"


class DevTeamAdapter(BaseAdapter):
    name = "devteam"
    description = (
        "Local AI development team: builds Python apps, writes features, reviews code, runs tests. "
        "Uses Architect → Developer → QA pipeline with Ollama LLMs."
    )
    capabilities = ["build_app", "write_feature", "review_code", "run_tests", "design", "devops_scan"]

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        if capability == "build_app":
            return self._build_app(params)
        elif capability == "write_feature":
            return self._write_feature(params)
        elif capability == "review_code":
            return self._review_code(params)
        elif capability == "run_tests":
            return self._run_tests(params)
        elif capability == "design":
            return self._design(params)
        elif capability == "devops_scan":
            return self._devops_scan(params)
        else:
            return AdapterResult(
                success=False,
                text=f"[devteam] Unknown capability: {capability}",
                adapter=self.name,
            )

    # ------------------------------------------------------------------ #
    # build_app  — full pipeline                                           #
    # ------------------------------------------------------------------ #

    def _build_app(
        self, params: dict[str, Any], linked_message_id: Optional[str] = None
    ) -> AdapterResult:
        task = params.get("task") or params.get("description", "unnamed project")
        slug = _slugify(task)
        artifact_dir = os.path.join(ARTIFACTS_DIR, slug)

        file_tool = FileTool(allowed_roots=[ARTIFACTS_DIR])
        cmd_tool = CommandTool(allowed_cwd_roots=[ARTIFACTS_DIR])
        architect = ArchitectAgent()
        developer = DeveloperAgent()
        qa_agent = QAAgent()

        # Step 1: Architect
        try:
            design_doc = architect.generate_design(task)
        except Exception as exc:
            return AdapterResult(
                success=False,
                text=f"[devteam] Architect failed: {exc}",
                adapter=self.name,
            )

        # Step 2-4: Developer → QA loop
        existing_files: dict[str, str] = {}
        fix_instructions = ""
        passed = False
        qa_result: dict = {}
        iteration = 0

        for iteration in range(1, MAX_ITERATIONS + 1):
            try:
                files = developer.generate_code(
                    design_doc=design_doc,
                    task=task,
                    fix_instructions=fix_instructions,
                    existing_files=existing_files if fix_instructions else None,
                    iteration=iteration,
                )
            except Exception as exc:
                return AdapterResult(
                    success=False,
                    text=f"[devteam] Developer failed on iteration {iteration}: {exc}",
                    adapter=self.name,
                )

            if not files:
                return AdapterResult(
                    success=False,
                    text=f"[devteam] Developer generated no files on iteration {iteration}",
                    adapter=self.name,
                )

            # Write files
            os.makedirs(artifact_dir, exist_ok=True)
            for filename, content in files.items():
                path = os.path.join(artifact_dir, filename)
                file_tool.write(path, content)

            existing_files = files

            # QA review
            try:
                qa_result = qa_agent.review(files=files, task=task)
            except Exception as exc:
                qa_result = {
                    "pass": False,
                    "issues": [str(exc)],
                    "fix_instructions": "QA agent encountered an error",
                }

            if qa_result.get("pass"):
                passed = True
                break

            fix_instructions = qa_result.get("fix_instructions", "")

        # Log orchestration decision
        _am.log_decision(
            agent="devteam",
            capability="build_app",
            decision=f"Completed build_app in {iteration} iteration(s) — {'success' if passed else 'failure'}",
            reasoning=f"QA result: {qa_result.get('issues', [])}",
            outcome="success" if passed else "failure",
            linked_message_id=linked_message_id,
            params_summary=f"task={task[:60]}, slug={slug}",
        )

        if passed:
            # Step 5: run pytest
            devops_summary = ""
            try:
                result = cmd_tool.run("pytest", ["-v"], cwd=artifact_dir)
                pytest_ok = result["returncode"] == 0
                pytest_output = result["stdout"][:2000] if pytest_ok else result["stderr"][:1000]
            except Exception as exc:
                pytest_ok = None
                pytest_output = f"Could not run pytest: {exc}"

            # Step 6: advisory DevOps scan (non-blocking)
            if DEVTEAM_DEVOPS_ENABLED:
                try:
                    devops_agent = DevOpsAgent()
                    devops_result = devops_agent.scan(artifact_dir)
                    devops_summary = f"\nDevOps: {devops_result['summary']}"
                    _am.log_decision(
                        agent="devteam",
                        capability="devops_scan",
                        decision=devops_result["summary"],
                        reasoning=f"passed={devops_result['passed']}",
                        outcome="success" if devops_result["passed"] else "advisory",
                        linked_message_id=linked_message_id,
                    )
                except Exception:
                    pass

            if pytest_ok is True:
                return AdapterResult(
                    success=True,
                    text=f"Build successful! Tests passed.{devops_summary}\n{pytest_output}",
                    data={"artifact_dir": artifact_dir, "files": list(files.keys())},
                    adapter=self.name,
                )
            elif pytest_ok is False:
                return AdapterResult(
                    success=False,
                    text=f"Build completed (QA passed) but pytest failed:{devops_summary}\n{pytest_output}",
                    data={"artifact_dir": artifact_dir, "returncode": result["returncode"]},
                    adapter=self.name,
                )
            else:
                return AdapterResult(
                    success=True,
                    text=f"Build completed (QA passed).{devops_summary} {pytest_output}\nFiles in: {artifact_dir}",
                    data={"artifact_dir": artifact_dir, "files": list(files.keys())},
                    adapter=self.name,
                )
        else:
            return AdapterResult(
                success=False,
                text=(
                    f"Build failed after {MAX_ITERATIONS} iterations. "
                    f"QA issues: {qa_result.get('issues', [])}"
                ),
                data={"qa_result": qa_result, "artifact_dir": artifact_dir},
                adapter=self.name,
            )

    # ------------------------------------------------------------------ #
    # write_feature  — Developer → QA only                                #
    # ------------------------------------------------------------------ #

    def _write_feature(self, params: dict[str, Any]) -> AdapterResult:
        task = params.get("task", "unnamed feature")
        context = params.get("context", "")
        slug = _slugify(task)
        artifact_dir = os.path.join(ARTIFACTS_DIR, slug)

        file_tool = FileTool(allowed_roots=[ARTIFACTS_DIR])
        developer = DeveloperAgent()
        qa_agent = QAAgent()

        design_doc = context or f"Feature request: {task}"
        existing_files: dict[str, str] = {}
        fix_instructions = ""
        passed = False
        qa_result: dict = {}
        iteration = 0

        for iteration in range(1, MAX_ITERATIONS + 1):
            try:
                files = developer.generate_code(
                    design_doc=design_doc,
                    task=task,
                    fix_instructions=fix_instructions,
                    existing_files=existing_files if fix_instructions else None,
                    iteration=iteration,
                )
            except Exception as exc:
                return AdapterResult(
                    success=False, text=f"[devteam] Developer failed: {exc}", adapter=self.name
                )

            if not files:
                break

            os.makedirs(artifact_dir, exist_ok=True)
            for filename, content in files.items():
                file_tool.write(os.path.join(artifact_dir, filename), content)

            existing_files = files
            try:
                qa_result = qa_agent.review(files=files, task=task)
            except Exception as exc:
                qa_result = {"pass": False, "issues": [str(exc)], "fix_instructions": ""}

            if qa_result.get("pass"):
                passed = True
                break
            fix_instructions = qa_result.get("fix_instructions", "")

        if passed:
            return AdapterResult(
                success=True,
                text=f"Feature written and QA passed. Files in: {artifact_dir}",
                data={"artifact_dir": artifact_dir, "files": list(files.keys())},
                adapter=self.name,
            )
        return AdapterResult(
            success=False,
            text=f"Feature write failed. QA issues: {qa_result.get('issues', [])}",
            data={"qa_result": qa_result},
            adapter=self.name,
        )

    # ------------------------------------------------------------------ #
    # review_code  — QA only, no writes                                   #
    # ------------------------------------------------------------------ #

    def _review_code(self, params: dict[str, Any]) -> AdapterResult:
        files: dict[str, str] = params.get("files", {})
        task = params.get("task", "code review")
        if not files:
            return AdapterResult(
                success=False,
                text="[devteam] review_code requires 'files' param: {filename: code_content}",
                adapter=self.name,
            )
        qa_agent = QAAgent()
        try:
            result = qa_agent.review(files=files, task=task)
        except Exception as exc:
            return AdapterResult(
                success=False, text=f"[devteam] QA agent error: {exc}", adapter=self.name
            )
        passed = result.get("pass", False)
        return AdapterResult(
            success=passed,
            text=f"Review: {'PASS' if passed else 'FAIL'}. Issues: {result.get('issues', [])}",
            data=result,
            adapter=self.name,
        )

    # ------------------------------------------------------------------ #
    # run_tests  — CommandTool pytest only                                 #
    # ------------------------------------------------------------------ #

    def _run_tests(self, params: dict[str, Any]) -> AdapterResult:
        path = params.get("path", "")
        if not path:
            return AdapterResult(
                success=False,
                text="[devteam] run_tests requires 'path' param (directory inside artifacts/)",
                adapter=self.name,
            )
        cmd_tool = CommandTool()
        try:
            result = cmd_tool.run("pytest", ["-v"], cwd=path)
            success = result["returncode"] == 0
            return AdapterResult(
                success=success,
                text=result["stdout"][:2000] if success else result["stderr"][:1000],
                data=result,
                adapter=self.name,
            )
        except PermissionError as exc:
            return AdapterResult(
                success=False, text=f"[devteam] Permission denied: {exc}", adapter=self.name
            )
        except Exception as exc:
            return AdapterResult(
                success=False, text=f"[devteam] Test run failed: {exc}", adapter=self.name
            )

    # ------------------------------------------------------------------ #
    # design  — Architect only                                             #
    # ------------------------------------------------------------------ #

    def _design(self, params: dict[str, Any]) -> AdapterResult:
        task = params.get("task", "")
        if not task:
            return AdapterResult(
                success=False,
                text="[devteam] design requires 'task' param",
                adapter=self.name,
            )
        architect = ArchitectAgent()
        try:
            design_doc = architect.generate_design(task)
            return AdapterResult(
                success=True, text=design_doc, data={"design": design_doc}, adapter=self.name
            )
        except Exception as exc:
            return AdapterResult(
                success=False, text=f"[devteam] Architect failed: {exc}", adapter=self.name
            )

    # ------------------------------------------------------------------ #
    # devops_scan  — standalone security + style scan                      #
    # ------------------------------------------------------------------ #

    def _devops_scan(self, params: dict[str, Any]) -> AdapterResult:
        path = params.get("path", "")
        if not path:
            return AdapterResult(
                success=False,
                text="[devteam] devops_scan requires 'path' param (directory to scan)",
                adapter=self.name,
            )
        if not os.path.isdir(path):
            return AdapterResult(
                success=False,
                text=f"[devteam] devops_scan path does not exist: {path}",
                adapter=self.name,
            )
        devops_agent = DevOpsAgent()
        try:
            result = devops_agent.scan(path)
            _am.log_decision(
                agent="devteam",
                capability="devops_scan",
                decision=result["summary"],
                reasoning=f"path={path}, passed={result['passed']}",
                outcome="success" if result["passed"] else "advisory",
            )
            return AdapterResult(
                success=result["passed"],
                text=result["summary"],
                data=result,
                adapter=self.name,
            )
        except Exception as exc:
            return AdapterResult(
                success=False,
                text=f"[devteam] devops_scan failed: {exc}",
                adapter=self.name,
            )
