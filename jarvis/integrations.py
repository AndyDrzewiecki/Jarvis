"""
Integration path management — clean replacement for scattered sys.path.insert() calls.
Reads paths from jarvis.config.INTEGRATION_PATHS with env var overrides.
"""
from __future__ import annotations
import importlib
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _get_integration_path(name: str) -> str | None:
    """Return the configured filesystem path for the given integration name."""
    from jarvis import config
    return config.INTEGRATION_PATHS.get(name)


def import_integration(name: str) -> Any | None:
    """
    Import an external integration module by name.
    Adds its directory to sys.path if needed, then imports the module.
    Returns the module or None if unavailable (never raises).

    Usage:
        ga = import_integration("grocery_agent")
        if ga is None:
            return AdapterResult(success=False, text="Grocery agent not available.")
    """
    path = _get_integration_path(name)
    if path is None:
        logger.debug("No integration path configured for %r", name)
        return None

    normalized = os.path.normpath(path)
    if normalized not in sys.path:
        sys.path.insert(0, normalized)
        logger.debug("Added %s to sys.path for integration %r", normalized, name)

    try:
        return importlib.import_module(name)
    except ImportError as exc:
        logger.debug("Integration %r not available: %s", name, exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected error importing integration %r: %s", name, exc)
        return None
