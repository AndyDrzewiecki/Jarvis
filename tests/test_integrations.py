"""Tests for jarvis/integrations.py — integration path management."""
from __future__ import annotations
import os
import sys
import pytest


def test_import_integration_returns_none_for_unknown_name():
    from jarvis.integrations import import_integration
    result = import_integration("totally_nonexistent_module_xyz_abc_123")
    assert result is None


def test_import_integration_adds_path_to_sys_path(monkeypatch, tmp_path):
    """If we point an integration at a real directory, it gets added to sys.path."""
    import jarvis.config as config
    import importlib

    # Use stdlib's json module dir as a known real path
    import json
    json_dir = os.path.dirname(json.__file__)

    monkeypatch.setitem(config.INTEGRATION_PATHS, "test_path_inject", json_dir)

    from jarvis.integrations import import_integration
    # The module "json" should already be importable — just verify path was added
    import_integration("test_path_inject")
    # path should be in sys.path now (or was already there)
    normalized = os.path.normpath(json_dir)
    assert normalized in [os.path.normpath(p) for p in sys.path]


def test_import_integration_returns_module_on_success(monkeypatch, tmp_path):
    """Point integration path at stdlib location and import a stdlib module."""
    import jarvis.config as config

    # Use json module's parent directory so we can import json
    import json
    stdlib_dir = os.path.dirname(os.path.dirname(json.__file__))

    monkeypatch.setitem(config.INTEGRATION_PATHS, "json", stdlib_dir)

    from jarvis.integrations import import_integration
    mod = import_integration("json")
    assert mod is not None
    assert hasattr(mod, "dumps")


def test_import_integration_returns_none_on_import_error(monkeypatch, tmp_path):
    """Point to a real dir that doesn't contain the module — should return None."""
    import jarvis.config as config

    monkeypatch.setitem(config.INTEGRATION_PATHS, "no_such_module_here", str(tmp_path))

    from jarvis.integrations import import_integration
    result = import_integration("no_such_module_here")
    assert result is None


def test_import_integration_never_raises(monkeypatch, tmp_path):
    """Even with completely bogus path, import_integration must never raise."""
    import jarvis.config as config

    monkeypatch.setitem(config.INTEGRATION_PATHS, "bad_path_module", "/nonexistent/path/that/does/not/exist")

    from jarvis.integrations import import_integration
    try:
        result = import_integration("bad_path_module")
        assert result is None
    except Exception as e:
        pytest.fail(f"import_integration raised an exception: {e}")


def test_get_integration_path_returns_configured_path(monkeypatch):
    """_get_integration_path returns the path from config.INTEGRATION_PATHS."""
    import jarvis.config as config
    from jarvis.integrations import _get_integration_path

    monkeypatch.setitem(config.INTEGRATION_PATHS, "myintegration", "/some/path")
    assert _get_integration_path("myintegration") == "/some/path"
