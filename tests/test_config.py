"""Tests for jarvis/config.py — unified configuration module."""
from __future__ import annotations
import importlib
import os
import pytest


def test_defaults_are_sane():
    import jarvis.config as config
    assert "localhost" in config.OLLAMA_HOST
    assert config.MODEL  # non-empty
    assert config.ADAPTER_TIMEOUT_S == 30


def test_env_override_ollama_host(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://myhost:1234")
    import jarvis.config as config
    importlib.reload(config)
    assert config.OLLAMA_HOST == "http://myhost:1234"


def test_env_override_adapter_timeout(monkeypatch):
    monkeypatch.setenv("JARVIS_ADAPTER_TIMEOUT", "99")
    import jarvis.config as config
    importlib.reload(config)
    assert config.ADAPTER_TIMEOUT_S == 99


def test_integration_paths_dict_has_grocery():
    import jarvis.config as config
    assert "grocery_agent" in config.INTEGRATION_PATHS


def test_integration_paths_dict_has_investor():
    import jarvis.config as config
    assert "investor" in config.INTEGRATION_PATHS


def test_data_dir_is_absolute_path():
    import jarvis.config as config
    assert os.path.isabs(config.DATA_DIR)


def test_get_returns_value():
    import jarvis.config as config
    assert config.get("MODEL") == config.MODEL


def test_get_returns_default():
    import jarvis.config as config
    assert config.get("NONEXISTENT_KEY", "fallback") == "fallback"
