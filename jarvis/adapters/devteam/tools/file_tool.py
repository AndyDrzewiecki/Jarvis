"""
FileTool — safe file I/O constrained to an allowed directory whitelist.

Write operations are only permitted inside ARTIFACTS_DIR (or custom roots
supplied at construction time for testing). Any path outside the whitelist
raises PermissionError — no exceptions.
"""
from __future__ import annotations
import os
from typing import Optional


class FileTool:
    def __init__(self, allowed_roots: Optional[list[str]] = None) -> None:
        if allowed_roots is None:
            from jarvis.adapters.devteam.config import ARTIFACTS_DIR
            allowed_roots = [ARTIFACTS_DIR]
        self.allowed_roots: list[str] = [os.path.abspath(r) for r in allowed_roots]

    def _check_path(self, path: str) -> str:
        """Resolve path and verify it's inside an allowed root. Raises PermissionError if not."""
        abs_path = os.path.abspath(path)
        for root in self.allowed_roots:
            if abs_path == root or abs_path.startswith(root + os.sep):
                return abs_path
        raise PermissionError(
            f"Path '{path}' (resolved: '{abs_path}') is outside allowed roots: {self.allowed_roots}"
        )

    def write(self, path: str, content: str) -> None:
        """Write text content to path. Creates parent directories as needed."""
        abs_path = self._check_path(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

    def read(self, path: str) -> str:
        """Read text content from path."""
        abs_path = self._check_path(path)
        with open(abs_path, "r", encoding="utf-8") as f:
            return f.read()

    def list(self, path: str) -> list[str]:
        """List entries in a directory. Returns [] if path doesn't exist."""
        abs_path = self._check_path(path)
        if not os.path.isdir(abs_path):
            return []
        return os.listdir(abs_path)

    def exists(self, path: str) -> bool:
        """Return True if path exists within allowed roots."""
        try:
            abs_path = self._check_path(path)
            return os.path.exists(abs_path)
        except PermissionError:
            return False
