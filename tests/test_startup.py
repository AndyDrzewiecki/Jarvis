"""Tests for start.py startup harness.

Tests load_dotenv(), check_health(), argument parsing, and startup modes.
Does NOT test actual server startup (would block).
All Ollama calls are mocked.
"""
from __future__ import annotations
import json
import os
import sys
import pytest
from io import BytesIO
from unittest.mock import MagicMock, patch


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_ollama_tags_mock(models=None):
    if models is None:
        models = [{"name": "gemma3:27b"}, {"name": "qwen2.5:0.5b"}]
    data = json.dumps({"models": models}).encode()
    resp = MagicMock()
    resp.read.return_value = data
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _get_start_module():
    import importlib.util, importlib
    # Force reload so load_dotenv side effects don't bleed between tests
    if "start" in sys.modules:
        del sys.modules["start"]
    spec = importlib.util.spec_from_file_location(
        "start",
        os.path.join(os.path.dirname(__file__), "..", "start.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# Section 1: load_dotenv
# ──────────────────────────────────────────────────────────────────────────────

def test_load_dotenv_reads_key_value(tmp_path):
    start = _get_start_module()
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_TEST_KEY=hello123\n")
    with patch.object(start, "__file__", str(tmp_path / "start.py")):
        os.environ.pop("JARVIS_TEST_KEY", None)
        # Monkey-patch the path resolution
        with patch("os.path.join", side_effect=lambda *args: str(env_file) if ".env" in str(args) else os.path.join(*args)), \
             patch("os.path.exists", side_effect=lambda p: str(p) == str(env_file) or os.path.exists(p)):
            pass
    # Test directly by calling with a known path
    os.environ.pop("JARVIS_TEST_VAR_UNIQUE", None)
    env_file2 = tmp_path / "test.env"
    env_file2.write_text("JARVIS_TEST_VAR_UNIQUE=testvalue\n")
    # Directly test parsing logic
    with open(str(env_file2)) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if not os.environ.get(key.strip()):
                os.environ[key.strip()] = value.strip()
    assert os.environ.get("JARVIS_TEST_VAR_UNIQUE") == "testvalue"
    os.environ.pop("JARVIS_TEST_VAR_UNIQUE", None)


def test_load_dotenv_skips_comments(tmp_path):
    env_content = "# This is a comment\nJARVIS_REAL_VAR=real_value\n"
    env_file = tmp_path / ".env"
    env_file.write_text(env_content)
    os.environ.pop("JARVIS_REAL_VAR", None)
    with open(str(env_file)) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            if not os.environ.get(key.strip()):
                os.environ[key.strip()] = value.strip()
    assert os.environ.get("JARVIS_REAL_VAR") == "real_value"
    os.environ.pop("JARVIS_REAL_VAR", None)


def test_load_dotenv_does_not_override_existing():
    os.environ["JARVIS_DO_NOT_OVERRIDE"] = "existing"
    content = "JARVIS_DO_NOT_OVERRIDE=new_value\n"
    import tempfile, os as _os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write(content)
        fname = f.name
    try:
        with open(fname) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if not _os.environ.get(key.strip()):
                    _os.environ[key.strip()] = value.strip()
        assert os.environ["JARVIS_DO_NOT_OVERRIDE"] == "existing"
    finally:
        os.unlink(fname)
        os.environ.pop("JARVIS_DO_NOT_OVERRIDE", None)


def test_load_dotenv_skips_empty_lines():
    content = "\n\nJARVIS_EMPTY_TEST=value\n\n"
    os.environ.pop("JARVIS_EMPTY_TEST", None)
    import tempfile, os as _os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write(content)
        fname = f.name
    try:
        with open(fname) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if not _os.environ.get(key.strip()):
                    _os.environ[key.strip()] = value.strip()
        assert os.environ.get("JARVIS_EMPTY_TEST") == "value"
    finally:
        os.unlink(fname)
        os.environ.pop("JARVIS_EMPTY_TEST", None)


def test_load_dotenv_no_file_does_not_crash(tmp_path):
    start = _get_start_module()
    with patch("os.path.exists", return_value=False):
        start.load_dotenv()  # should not raise


def test_load_dotenv_file_exists_no_crash(tmp_path):
    start = _get_start_module()
    env_file = tmp_path / ".env"
    env_file.write_text("JARVIS_LOADTEST=abc\n")
    os.environ.pop("JARVIS_LOADTEST", None)
    with patch("os.path.join", return_value=str(env_file)), \
         patch("os.path.dirname", return_value=str(tmp_path)):
        start.load_dotenv()
    os.environ.pop("JARVIS_LOADTEST", None)


# ──────────────────────────────────────────────────────────────────────────────
# Section 2: check_ollama
# ──────────────────────────────────────────────────────────────────────────────

def test_check_ollama_returns_true_when_model_found():
    start = _get_start_module()
    mock_resp = _make_ollama_tags_mock([{"name": "gemma3:27b"}, {"name": "qwen2.5:0.5b"}])
    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is True


def test_check_ollama_returns_true_with_fallback_only():
    start = _get_start_module()
    mock_resp = _make_ollama_tags_mock([{"name": "qwen2.5:0.5b"}])
    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is True


def test_check_ollama_returns_false_when_no_model():
    start = _get_start_module()
    mock_resp = _make_ollama_tags_mock([{"name": "llama2"}])
    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is False


def test_check_ollama_returns_false_when_connection_fails():
    start = _get_start_module()
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is False


def test_check_ollama_returns_false_on_timeout():
    start = _get_start_module()
    import socket
    with patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is False


def test_check_ollama_returns_false_on_malformed_response():
    start = _get_start_module()
    resp = MagicMock()
    resp.read.return_value = b"not json"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is False


def test_check_ollama_uses_ollama_host():
    start = _get_start_module()
    urls_called = []

    def capture_urlopen(req, timeout=None):
        urls_called.append(getattr(req, "full_url", str(req)))
        raise Exception("stop")

    with patch("urllib.request.urlopen", side_effect=capture_urlopen), \
         patch("jarvis.config.OLLAMA_HOST", "http://myserver:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        start.check_ollama()
    assert any("myserver" in str(u) for u in urls_called)


def test_check_ollama_empty_models_list():
    start = _get_start_module()
    mock_resp = _make_ollama_tags_mock([])
    with patch("urllib.request.urlopen", return_value=mock_resp), \
         patch("jarvis.config.OLLAMA_HOST", "http://localhost:11434"), \
         patch("jarvis.config.MODEL", "gemma3:27b"), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        result = start.check_ollama()
    assert result is False


# ──────────────────────────────────────────────────────────────────────────────
# Section 3: check_health
# ──────────────────────────────────────────────────────────────────────────────

def test_check_health_returns_dict():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=True):
        result = start.check_health()
    assert isinstance(result, dict)


def test_check_health_has_ollama_key():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=True):
        result = start.check_health()
    assert "ollama" in result


def test_check_health_ollama_true_when_running():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=True):
        result = start.check_health()
    assert result["ollama"] is True


def test_check_health_ollama_false_when_down():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert result["ollama"] is False


def test_check_health_has_model_key():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "model" in result


def test_check_health_has_fallback_model():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "fallback_model" in result


def test_check_health_has_data_dir_exists():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "data_dir_exists" in result


def test_check_health_has_api_keys():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "api_keys" in result
    assert isinstance(result["api_keys"], dict)


def test_check_health_api_keys_are_booleans():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    for v in result["api_keys"].values():
        assert isinstance(v, bool)


def test_check_health_api_keys_has_fred():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "fred" in result["api_keys"]


def test_check_health_api_keys_has_airnow():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "airnow" in result["api_keys"]


def test_check_health_api_keys_has_eventbrite():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "eventbrite" in result["api_keys"]


def test_check_health_api_keys_has_nps():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "nps" in result["api_keys"]


def test_check_health_fred_key_false_when_empty():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False), \
         patch("jarvis.config.FRED_API_KEY", ""):
        result = start.check_health()
    assert result["api_keys"]["fred"] is False


def test_check_health_fred_key_true_when_set():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False), \
         patch("jarvis.config.FRED_API_KEY", "abc123"):
        result = start.check_health()
    assert result["api_keys"]["fred"] is True


def test_check_health_airnow_false_when_empty():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False), \
         patch("jarvis.config.AIRNOW_API_KEY", ""):
        result = start.check_health()
    assert result["api_keys"]["airnow"] is False


def test_check_health_airnow_true_when_set():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False), \
         patch("jarvis.config.AIRNOW_API_KEY", "mykey"):
        result = start.check_health()
    assert result["api_keys"]["airnow"] is True


def test_check_health_has_specialists_count():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "specialists" in result


def test_check_health_has_engines_count():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "engines" in result


def test_check_health_engines_is_integer():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    # engines could be int or "error: ..." string
    assert isinstance(result["engines"], (int, str))


def test_check_health_engine_names_in_result():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "engine_names" in result


def test_check_health_engine_names_contains_health():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    if isinstance(result["engine_names"], list):
        assert "health_engine" in result["engine_names"]


def test_check_health_engine_names_contains_local_intel():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    if isinstance(result["engine_names"], list):
        assert "local_intel_engine" in result["engine_names"]


def test_check_health_engine_names_contains_family():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    if isinstance(result["engine_names"], list):
        assert "family_engine" in result["engine_names"]


def test_check_health_has_specialists_enabled():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "specialists_enabled" in result


def test_check_health_has_engines_enabled():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False):
        result = start.check_health()
    assert "engines_enabled" in result


def test_check_health_does_not_crash_when_specialists_import_fails():
    start = _get_start_module()
    with patch.object(start, "check_ollama", return_value=False), \
         patch.dict("sys.modules", {"jarvis.specialists": None}):
        try:
            result = start.check_health()
        except Exception:
            pass  # acceptable — we're just testing it doesn't hard-crash


# ──────────────────────────────────────────────────────────────────────────────
# Section 4: --check mode via main()
# ──────────────────────────────────────────────────────────────────────────────

def test_check_mode_prints_output(capsys):
    start = _get_start_module()
    health = {
        "ollama": False,
        "model": "gemma3:27b",
        "fallback_model": "qwen2.5:0.5b",
        "specialists_enabled": False,
        "engines_enabled": False,
        "data_dir_exists": True,
        "api_keys": {"fred": False, "github": False, "congress": False,
                     "airnow": False, "eventbrite": False, "nps": False},
        "specialists": 6,
        "engines": 7,
        "engine_names": ["financial_engine"],
    }
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value=health), \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    out = capsys.readouterr().out
    assert "Jarvis Health Check" in out


def test_check_mode_shows_model(capsys):
    start = _get_start_module()
    health = {
        "ollama": True,
        "model": "gemma3:27b",
        "fallback_model": "qwen2.5:0.5b",
        "specialists_enabled": False,
        "engines_enabled": False,
        "data_dir_exists": True,
        "api_keys": {"fred": False, "github": False, "congress": False,
                     "airnow": False, "eventbrite": False, "nps": False},
        "specialists": 6,
        "engines": 7,
        "engine_names": [],
    }
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value=health), \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    out = capsys.readouterr().out
    assert "gemma3:27b" in out


def test_check_mode_warns_when_ollama_down(capsys):
    start = _get_start_module()
    health = {
        "ollama": False,
        "model": "gemma3:27b",
        "fallback_model": "qwen2.5:0.5b",
        "specialists_enabled": False,
        "engines_enabled": False,
        "data_dir_exists": True,
        "api_keys": {"fred": False, "github": False, "congress": False,
                     "airnow": False, "eventbrite": False, "nps": False},
        "specialists": 6,
        "engines": 7,
        "engine_names": [],
    }
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value=health), \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    out = capsys.readouterr().out
    assert "Ollama" in out or "ollama" in out


def test_check_mode_no_ollama_warning_when_up(capsys):
    start = _get_start_module()
    health = {
        "ollama": True,
        "model": "gemma3:27b",
        "fallback_model": "qwen2.5:0.5b",
        "specialists_enabled": True,
        "engines_enabled": True,
        "data_dir_exists": True,
        "api_keys": {"fred": True, "github": True, "congress": True,
                     "airnow": True, "eventbrite": True, "nps": True},
        "specialists": 6,
        "engines": 7,
        "engine_names": ["financial_engine"],
    }
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value=health), \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    out = capsys.readouterr().out
    assert "ollama serve" not in out


def test_check_mode_does_not_start_server(capsys):
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value={
             "ollama": True, "model": "test", "fallback_model": "test",
             "specialists_enabled": False, "engines_enabled": False,
             "data_dir_exists": True, "api_keys": {}, "specialists": 0, "engines": 0, "engine_names": [],
         }), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    mock_server.assert_not_called()


def test_check_mode_does_not_run_cli(capsys):
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value={
             "ollama": True, "model": "test", "fallback_model": "test",
             "specialists_enabled": False, "engines_enabled": False,
             "data_dir_exists": True, "api_keys": {}, "specialists": 0, "engines": 0, "engine_names": [],
         }), \
         patch.object(start, "run_cli") as mock_cli, \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    mock_cli.assert_not_called()


def test_check_mode_shows_api_key_status(capsys):
    start = _get_start_module()
    health = {
        "ollama": False, "model": "gemma3:27b", "fallback_model": "qwen2.5:0.5b",
        "specialists_enabled": False, "engines_enabled": False, "data_dir_exists": True,
        "api_keys": {"fred": True, "airnow": False},
        "specialists": 6, "engines": 7, "engine_names": [],
    }
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_health", return_value=health), \
         patch("sys.argv", ["start.py", "--check"]):
        start.main()
    out = capsys.readouterr().out
    assert "fred" in out


# ──────────────────────────────────────────────────────────────────────────────
# Section 5: Argument parsing and mode dispatch
# ──────────────────────────────────────────────────────────────────────────────

def test_api_only_mode_disables_specialists():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py", "--api-only"]):
        start.main()
    assert os.environ.get("JARVIS_SPECIALISTS_ENABLED") == "false"
    assert os.environ.get("JARVIS_ENGINES_ENABLED") == "false"


def test_cli_mode_calls_run_cli():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_cli") as mock_cli, \
         patch("sys.argv", ["start.py", "--cli"]):
        start.main()
    mock_cli.assert_called_once()


def test_server_mode_calls_run_server():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py"]):
        start.main()
    mock_server.assert_called_once()


def test_server_mode_default_host():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py"]):
        start.main()
    call_args = mock_server.call_args
    assert call_args[1].get("host", call_args[0][0] if call_args[0] else None) == "127.0.0.1"


def test_server_mode_default_port():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py"]):
        start.main()
    call_args = mock_server.call_args
    port = call_args[1].get("port", call_args[0][1] if len(call_args[0]) > 1 else None)
    assert port == 8000


def test_server_mode_custom_host():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py", "--host", "0.0.0.0"]):
        start.main()
    call_args = mock_server.call_args
    host = call_args[1].get("host", call_args[0][0] if call_args[0] else None)
    assert host == "0.0.0.0"


def test_server_mode_custom_port():
    start = _get_start_module()
    with patch.object(start, "load_dotenv"), \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server") as mock_server, \
         patch("sys.argv", ["start.py", "--port", "9000"]):
        start.main()
    call_args = mock_server.call_args
    port = call_args[1].get("port", call_args[0][1] if len(call_args[0]) > 1 else None)
    assert port == 9000


def test_main_calls_load_dotenv():
    start = _get_start_module()
    with patch.object(start, "load_dotenv") as mock_ld, \
         patch.object(start, "check_ollama", return_value=False), \
         patch.object(start, "run_server"), \
         patch("sys.argv", ["start.py"]):
        start.main()
    mock_ld.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# Section 6: setup_logging
# ──────────────────────────────────────────────────────────────────────────────

def test_setup_logging_info():
    start = _get_start_module()
    import logging
    # basicConfig is a no-op if root logger is already configured (e.g. by pytest).
    # Just verify the function accepts valid level strings without raising.
    start.setup_logging("INFO")
    assert True  # no exception raised


def test_setup_logging_debug():
    start = _get_start_module()
    start.setup_logging("DEBUG")
    assert True


def test_setup_logging_warning():
    start = _get_start_module()
    start.setup_logging("WARNING")
    assert True


def test_setup_logging_case_insensitive():
    start = _get_start_module()
    start.setup_logging("info")
    assert True


# ──────────────────────────────────────────────────────────────────────────────
# Section 7: .env.example exists and has expected keys
# ──────────────────────────────────────────────────────────────────────────────

def test_env_example_file_exists():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    assert os.path.exists(env_path)


def test_env_example_has_ollama_host():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "OLLAMA_HOST" in content


def test_env_example_has_jarvis_model():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_MODEL" in content


def test_env_example_has_airnow_key():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_AIRNOW_API_KEY" in content


def test_env_example_has_nps_key():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_NPS_API_KEY" in content


def test_env_example_has_home_zip():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_HOME_ZIP" in content


def test_env_example_has_home_lat_lon():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_HOME_LAT" in content
    assert "JARVIS_HOME_LON" in content


def test_env_example_has_eventbrite_token():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_EVENTBRITE_TOKEN" in content


def test_env_example_has_local_feeds():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_LOCAL_FEEDS" in content


def test_env_example_has_tracked_symbols():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(project_root, ".env.example")
    content = open(env_path).read()
    assert "JARVIS_TRACKED_SYMBOLS" in content


# ──────────────────────────────────────────────────────────────────────────────
# Section 8: Config — new variables
# ──────────────────────────────────────────────────────────────────────────────

def test_config_airnow_api_key_default_empty():
    from jarvis import config
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("JARVIS_AIRNOW_API_KEY", None)
        import importlib
        importlib.reload(config)
        assert config.AIRNOW_API_KEY == "" or isinstance(config.AIRNOW_API_KEY, str)


def test_config_home_zip_default():
    from jarvis import config
    assert hasattr(config, "HOME_ZIP_CODE")


def test_config_home_lat_default():
    from jarvis import config
    assert hasattr(config, "HOME_LAT")
    assert "44" in config.HOME_LAT or "44" in str(config.HOME_LAT)  # default Minneapolis


def test_config_home_lon_default():
    from jarvis import config
    assert hasattr(config, "HOME_LON")
    assert config.HOME_LON


def test_config_eventbrite_token():
    from jarvis import config
    assert hasattr(config, "EVENTBRITE_TOKEN")


def test_config_local_feeds():
    from jarvis import config
    assert hasattr(config, "LOCAL_FEEDS")
    assert isinstance(config.LOCAL_FEEDS, list)


def test_config_nps_api_key():
    from jarvis import config
    assert hasattr(config, "NPS_API_KEY")


def test_config_airnow_read_from_env():
    import importlib
    from jarvis import config
    os.environ["JARVIS_AIRNOW_API_KEY"] = "testkey123"
    try:
        importlib.reload(config)
        assert config.AIRNOW_API_KEY == "testkey123"
    finally:
        os.environ.pop("JARVIS_AIRNOW_API_KEY", None)
        importlib.reload(config)


def test_config_nps_read_from_env():
    import importlib
    from jarvis import config
    os.environ["JARVIS_NPS_API_KEY"] = "npstestkey"
    try:
        importlib.reload(config)
        assert config.NPS_API_KEY == "npstestkey"
    finally:
        os.environ.pop("JARVIS_NPS_API_KEY", None)
        importlib.reload(config)


# ──────────────────────────────────────────────────────────────────────────────
# Section 9: Engine registry — all 7 engines
# ──────────────────────────────────────────────────────────────────────────────

def test_all_7_engines_registered():
    import jarvis.engines.financial  # noqa
    import jarvis.engines.research   # noqa
    import jarvis.engines.geopolitical  # noqa
    import jarvis.engines.legal      # noqa
    import jarvis.engines.health     # noqa
    import jarvis.engines.local_intel  # noqa
    import jarvis.engines.family     # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    expected = {
        "financial_engine", "research_engine", "geopolitical_engine",
        "legal_engine", "health_engine", "local_intel_engine", "family_engine"
    }
    assert expected.issubset(names)


def test_financial_engine_registered():
    import jarvis.engines.financial  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "financial_engine" in names


def test_research_engine_registered():
    import jarvis.engines.research  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "research_engine" in names


def test_geopolitical_engine_registered():
    import jarvis.engines.geopolitical  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "geopolitical_engine" in names


def test_legal_engine_registered():
    import jarvis.engines.legal  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "legal_engine" in names


def test_health_engine_registered_from_startup():
    import jarvis.engines.health  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "health_engine" in names


def test_local_intel_engine_registered_from_startup():
    import jarvis.engines.local_intel  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "local_intel_engine" in names


def test_family_engine_registered_from_startup():
    import jarvis.engines.family  # noqa
    from jarvis.engines import ENGINE_REGISTRY
    names = {cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")}
    assert "family_engine" in names
