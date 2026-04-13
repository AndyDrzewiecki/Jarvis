"""Tests for DevTeam FileTool and CommandTool — path/command whitelist enforcement."""
from __future__ import annotations
import os
import subprocess
import pytest
from unittest.mock import patch

from jarvis.adapters.devteam.tools.file_tool import FileTool
from jarvis.adapters.devteam.tools.command_tool import CommandTool


# ── FileTool ──────────────────────────────────────────────────────────────────

@pytest.fixture
def allowed_dir(tmp_path):
    d = tmp_path / "artifacts"
    d.mkdir()
    return d


@pytest.fixture
def file_tool(allowed_dir):
    return FileTool(allowed_roots=[str(allowed_dir)])


def test_file_tool_write_and_read(file_tool, allowed_dir):
    path = str(allowed_dir / "hello.py")
    file_tool.write(path, "print('hello')")
    content = file_tool.read(path)
    assert content == "print('hello')"


def test_file_tool_write_creates_subdirectories(file_tool, allowed_dir):
    path = str(allowed_dir / "subdir" / "nested.py")
    file_tool.write(path, "# code")
    assert os.path.exists(path)


def test_file_tool_list(file_tool, allowed_dir):
    (allowed_dir / "a.py").write_text("a")
    (allowed_dir / "b.py").write_text("b")
    entries = file_tool.list(str(allowed_dir))
    assert "a.py" in entries
    assert "b.py" in entries


def test_file_tool_list_nonexistent_returns_empty(file_tool, allowed_dir):
    result = file_tool.list(str(allowed_dir / "missing_dir"))
    assert result == []


def test_file_tool_rejects_path_outside_allowed(file_tool, tmp_path):
    outside = str(tmp_path / "secret.py")
    with pytest.raises(PermissionError):
        file_tool.write(outside, "evil")


def test_file_tool_rejects_traversal_attack(file_tool, allowed_dir):
    traversal = str(allowed_dir / ".." / "escape.py")
    with pytest.raises(PermissionError):
        file_tool.write(traversal, "evil")


def test_file_tool_allows_subdirectory(file_tool, allowed_dir):
    subdir = allowed_dir / "sub"
    subdir.mkdir()
    path = str(subdir / "ok.py")
    file_tool.write(path, "ok")
    assert file_tool.read(path) == "ok"


def test_file_tool_exists(file_tool, allowed_dir):
    path = str(allowed_dir / "x.py")
    assert not file_tool.exists(path)
    file_tool.write(path, "x")
    assert file_tool.exists(path)


# ── CommandTool ───────────────────────────────────────────────────────────────

@pytest.fixture
def cmd_tool(tmp_path):
    return CommandTool(
        allowed_commands={"pytest", "python"},
        timeout=10,
        allowed_cwd_roots=[str(tmp_path)],
    )


def test_command_tool_rejects_disallowed_command(cmd_tool):
    with pytest.raises(PermissionError, match="not in the allowed list"):
        cmd_tool.run("rm", ["-rf", "/"])


def test_command_tool_rejects_shell_command(cmd_tool):
    with pytest.raises(PermissionError):
        cmd_tool.run("bash", ["-c", "echo hi"])


def test_command_tool_rejects_cwd_outside_whitelist(cmd_tool, tmp_path):
    outside = str(tmp_path.parent)
    with pytest.raises(PermissionError, match="outside allowed roots"):
        cmd_tool.run("python", ["--version"], cwd=outside)


def test_command_tool_allows_cwd_subdirectory(tmp_path):
    subdir = tmp_path / "sub"
    subdir.mkdir()
    tool = CommandTool(
        allowed_commands={"python"},
        timeout=10,
        allowed_cwd_roots=[str(tmp_path)],
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        tool.run("python", ["--version"], cwd=str(subdir))
    mock_run.assert_called_once()


def test_command_tool_timeout_raises(tmp_path):
    tool = CommandTool(
        allowed_commands={"python"},
        timeout=1,
        allowed_cwd_roots=[str(tmp_path)],
    )
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("python", 1)):
        with pytest.raises(subprocess.TimeoutExpired):
            tool.run("python", ["-c", "import time; time.sleep(100)"], cwd=str(tmp_path))


def test_command_tool_returns_stdout_stderr(tmp_path):
    tool = CommandTool(
        allowed_commands={"python"},
        timeout=10,
        allowed_cwd_roots=[str(tmp_path)],
    )
    mock_result = type("R", (), {"returncode": 0, "stdout": "hello\n", "stderr": ""})()
    with patch("subprocess.run", return_value=mock_result):
        result = tool.run("python", ["-c", "print('hello')"], cwd=str(tmp_path))
    assert result["returncode"] == 0
    assert result["stdout"] == "hello\n"
