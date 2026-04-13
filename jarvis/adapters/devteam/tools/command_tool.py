"""
CommandTool — safe subprocess execution with command and cwd whitelists.

Only commands in ALLOWED_COMMANDS may be executed.
cwd (when specified) must be inside ARTIFACTS_DIR or custom allowed roots.
Enforces a configurable timeout (default: DEVTEAM_COMMAND_TIMEOUT seconds).
"""
from __future__ import annotations
import os
import subprocess
from typing import Optional


class CommandTool:
    def __init__(
        self,
        allowed_commands: Optional[set[str]] = None,
        timeout: Optional[int] = None,
        allowed_cwd_roots: Optional[list[str]] = None,
    ) -> None:
        if allowed_commands is None:
            from jarvis.adapters.devteam.config import ALLOWED_COMMANDS
            allowed_commands = ALLOWED_COMMANDS
        if timeout is None:
            from jarvis.adapters.devteam.config import COMMAND_TIMEOUT
            timeout = COMMAND_TIMEOUT
        if allowed_cwd_roots is None:
            from jarvis.adapters.devteam.config import ARTIFACTS_DIR
            allowed_cwd_roots = [ARTIFACTS_DIR]

        self.allowed_commands: set[str] = set(allowed_commands)
        self.timeout: int = timeout
        self.allowed_cwd_roots: list[str] = [os.path.abspath(r) for r in allowed_cwd_roots]

    def _check_command(self, command: str) -> None:
        if command not in self.allowed_commands:
            raise PermissionError(
                f"Command '{command}' is not in the allowed list: {self.allowed_commands}"
            )

    def _check_cwd(self, cwd: str) -> str:
        abs_cwd = os.path.abspath(cwd)
        for root in self.allowed_cwd_roots:
            if abs_cwd == root or abs_cwd.startswith(root + os.sep):
                return abs_cwd
        raise PermissionError(
            f"cwd '{cwd}' (resolved: '{abs_cwd}') is outside allowed roots: {self.allowed_cwd_roots}"
        )

    def run(
        self,
        command: str,
        args: Optional[list[str]] = None,
        cwd: Optional[str] = None,
    ) -> dict:
        """
        Run a whitelisted command. Returns dict with returncode, stdout, stderr.
        Raises PermissionError for disallowed commands or cwd.
        Raises subprocess.TimeoutExpired if the command exceeds the timeout.
        """
        self._check_command(command)

        resolved_cwd: Optional[str] = None
        if cwd is not None:
            resolved_cwd = self._check_cwd(cwd)

        cmd = [command] + (args or [])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            cwd=resolved_cwd,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
