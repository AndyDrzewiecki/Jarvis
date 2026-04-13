"""Tests for DevTeamAdapter — Architect→Developer→QA loop, fully mocked."""
from __future__ import annotations
import json
import os
import pytest
from unittest.mock import patch, MagicMock

import jarvis.agent_memory as am
from jarvis.adapters.devteam.adapter import DevTeamAdapter


# ── shared fixtures ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def tmp_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    # Redirect artifacts to tmp_path so tests don't write to the repo
    monkeypatch.setattr(
        "jarvis.adapters.devteam.adapter.ARTIFACTS_DIR", str(tmp_path / "artifacts")
    )
    return DevTeamAdapter()


def _design_response():
    return "## Overview\nA test app.\n## File Structure\napp.py, tests/test_app.py\n## Key Classes/Functions\ndef add(a,b)\n## Test Strategy\ntest_add"


def _dev_response(files=None):
    if files is None:
        files = {
            "app.py": "def add(a: int, b: int) -> int:\n    return a + b",
            "tests/test_app.py": "from app import add\ndef test_add():\n    assert add(1, 2) == 3",
        }
    parts = []
    for fname, code in files.items():
        parts.append(f"# FILE: {fname}\n```python\n{code}\n```")
    return "\n\n".join(parts)


def _qa_pass_response():
    return json.dumps({"pass": True, "issues": [], "fix_instructions": ""})


def _qa_fail_response(issues=None):
    return json.dumps({
        "pass": False,
        "issues": issues or ["Missing test functions"],
        "fix_instructions": "Add test_ functions",
    })


# ── adapter metadata ──────────────────────────────────────────────────────────

def test_devteam_adapter_metadata():
    a = DevTeamAdapter()
    assert a.name == "devteam"
    assert "build_app" in a.capabilities
    assert "review_code" in a.capabilities
    assert len(a.capabilities) == 6


# ── build_app — happy path ────────────────────────────────────────────────────

def test_build_app_success(adapter, tmp_path):
    pytest_result = MagicMock(returncode=0, stdout="2 passed", stderr="")

    with patch("jarvis.adapters.devteam.config._ask_ollama") as mock_ollama, \
         patch("subprocess.run", return_value=pytest_result):
        mock_ollama.side_effect = [
            _design_response(),   # architect
            _dev_response(),      # developer iteration 1
            _qa_pass_response(),  # qa iteration 1
        ]
        result = adapter.run("build_app", {"task": "build a simple adder"})

    assert result.success is True
    assert result.adapter == "devteam"


def test_build_app_writes_files_to_artifacts(adapter, tmp_path, monkeypatch):
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr("jarvis.adapters.devteam.adapter.ARTIFACTS_DIR", str(artifact_root))

    pytest_result = MagicMock(returncode=0, stdout="1 passed", stderr="")
    with patch("jarvis.adapters.devteam.config._ask_ollama") as mock_ollama, \
         patch("subprocess.run", return_value=pytest_result):
        mock_ollama.side_effect = [
            _design_response(),
            _dev_response(),
            _qa_pass_response(),
        ]
        adapter.run("build_app", {"task": "simple adder"})

    # Files should exist somewhere under artifact_root
    all_files = []
    for root, _, files in os.walk(str(artifact_root)):
        all_files.extend(files)
    assert len(all_files) > 0


# ── build_app — QA retry ──────────────────────────────────────────────────────

def test_build_app_qa_retry_succeeds(adapter, tmp_path):
    pytest_result = MagicMock(returncode=0, stdout="passed", stderr="")
    with patch("jarvis.adapters.devteam.config._ask_ollama") as mock_ollama, \
         patch("subprocess.run", return_value=pytest_result):
        mock_ollama.side_effect = [
            _design_response(),            # architect
            _dev_response(),               # developer iteration 1
            _qa_fail_response(),           # qa iteration 1 — fail
            _dev_response(),               # developer iteration 2 (retry)
            _qa_pass_response(),           # qa iteration 2 — pass
        ]
        result = adapter.run("build_app", {"task": "adder with retry"})

    assert result.success is True


def test_build_app_max_iterations_failure(adapter, tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.adapters.devteam.adapter.MAX_ITERATIONS", 2)
    with patch("jarvis.adapters.devteam.config._ask_ollama") as mock_ollama:
        mock_ollama.side_effect = [
            _design_response(),   # architect
            _dev_response(),      # developer iter 1
            _qa_fail_response(),  # qa iter 1 — fail
            _dev_response(),      # developer iter 2
            _qa_fail_response(),  # qa iter 2 — fail
        ]
        result = adapter.run("build_app", {"task": "always fails"})

    assert result.success is False
    assert "iteration" in result.text.lower() or "fail" in result.text.lower()


def test_build_app_logs_decision_to_agent_memory(adapter, tmp_path):
    pytest_result = MagicMock(returncode=0, stdout="passed", stderr="")
    with patch("jarvis.adapters.devteam.config._ask_ollama") as mock_ollama, \
         patch("subprocess.run", return_value=pytest_result):
        mock_ollama.side_effect = [
            _design_response(),
            _dev_response(),
            _qa_pass_response(),
        ]
        adapter.run("build_app", {"task": "log test"})

    decisions = am.recent_decisions(n=50)
    devteam_decisions = [d for d in decisions if d["agent"].startswith("devteam")]
    assert len(devteam_decisions) > 0


# ── design capability ─────────────────────────────────────────────────────────

def test_design_capability(adapter):
    with patch("jarvis.adapters.devteam.config._ask_ollama", return_value=_design_response()):
        result = adapter.run("design", {"task": "build a calculator"})
    assert result.success is True
    assert "Overview" in result.text or "File Structure" in result.text


def test_design_missing_task(adapter):
    result = adapter.run("design", {})
    assert result.success is False
    assert "task" in result.text


# ── review_code capability ────────────────────────────────────────────────────

def test_review_code_pass(adapter):
    files = {"app.py": "def hello(): pass", "tests/test_app.py": "def test_hello(): pass"}
    with patch("jarvis.adapters.devteam.config._ask_ollama", return_value=_qa_pass_response()):
        result = adapter.run("review_code", {"files": files, "task": "review"})
    assert result.success is True


def test_review_code_fail(adapter):
    files = {"app.py": "def hello(): pass"}
    with patch("jarvis.adapters.devteam.config._ask_ollama", return_value=_qa_fail_response()):
        result = adapter.run("review_code", {"files": files, "task": "review"})
    assert result.success is False


def test_review_code_missing_files(adapter):
    result = adapter.run("review_code", {})
    assert result.success is False
    assert "files" in result.text


# ── run_tests capability ──────────────────────────────────────────────────────

def test_run_tests_missing_path(adapter):
    result = adapter.run("run_tests", {})
    assert result.success is False
    assert "path" in result.text


def test_run_tests_path_outside_whitelist(adapter, tmp_path):
    result = adapter.run("run_tests", {"path": str(tmp_path.parent)})
    assert result.success is False


# ── devops_scan capability ────────────────────────────────────────────────────

def test_devops_scan_missing_path(adapter):
    result = adapter.run("devops_scan", {})
    assert result.success is False
    assert "path" in result.text


def test_devops_scan_nonexistent_path(adapter):
    result = adapter.run("devops_scan", {"path": "/nonexistent/path/xyz"})
    assert result.success is False
    assert "not exist" in result.text


def test_devops_scan_runs_on_valid_dir(adapter, tmp_path):
    # Write a minimal Python file for scanning
    (tmp_path / "sample.py").write_text("x = 1\n")
    with patch("jarvis.adapters.devteam.agents.devops.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = adapter.run("devops_scan", {"path": str(tmp_path)})
    # Result may be success or advisory; should not error
    assert result.adapter == "devteam"
    assert result.text  # has some output


def test_devops_scan_in_capabilities(adapter):
    assert "devops_scan" in adapter.capabilities


# ── unknown capability ────────────────────────────────────────────────────────

def test_unknown_capability(adapter):
    result = adapter.run("unknown_thing", {})
    assert result.success is False
