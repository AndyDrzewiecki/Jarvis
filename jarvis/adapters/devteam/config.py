"""
DevTeam configuration — env vars, constants, and the shared Ollama client.

All devteam agents import from here so tests can mock _ask_ollama once.
"""
from __future__ import annotations
import os

import requests as _requests

DEVTEAM_MODEL: str = os.getenv("DEVTEAM_MODEL", "gemma3:27b")
MAX_ITERATIONS: int = int(os.getenv("DEVTEAM_MAX_ITERATIONS", "3"))
COMMAND_TIMEOUT: int = int(os.getenv("DEVTEAM_COMMAND_TIMEOUT", "60"))

ARTIFACTS_DIR: str = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "artifacts")
)

ALLOWED_COMMANDS: set[str] = {"pytest", "python", "black", "pip", "bandit", "flake8"}

DEVTEAM_DEVOPS_ENABLED: bool = (
    os.getenv("DEVTEAM_DEVOPS_ENABLED", "true").lower() == "true"
)

OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")


def _ask_ollama(prompt: str, model: str = DEVTEAM_MODEL) -> str:
    """Send a prompt to Ollama and return the response text."""
    url = f"{OLLAMA_HOST}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False}
    r = _requests.post(url, json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["response"]
