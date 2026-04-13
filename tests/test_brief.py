"""Tests for jarvis.brief.BriefEngine — all adapters + LLM are mocked."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

import jarvis.agent_memory as am
from jarvis.adapters.base import AdapterResult


@pytest.fixture(autouse=True)
def tmp_files(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))
    import jarvis.brief as brief_mod
    monkeypatch.setattr(brief_mod, "BRIEFS_PATH", str(tmp_path / "briefs.jsonl"))


def _ok(text="ok"):
    return AdapterResult(success=True, text=text, adapter="test")


def _fail():
    return AdapterResult(success=False, text="error", adapter="test")


# ── BriefEngine.generate ──────────────────────────────────────────────────────

@patch("jarvis.brief.notifier.notify")
@patch("jarvis.core._ask_ollama", return_value="Good morning. Synthesised brief.")
def test_generate_returns_dict(mock_llm, mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch.object(engine, "_adapter_map", {
        "investor": MagicMock(safe_run=MagicMock(return_value=_ok("market ok"))),
        "summerpuppy": MagicMock(safe_run=MagicMock(return_value=_ok("security ok"))),
        "homeops_grocery": MagicMock(safe_run=MagicMock(return_value=_ok("groceries ok"))),
        "grocery": MagicMock(safe_run=MagicMock(return_value=_ok("shopping ok"))),
    }):
        result = engine.generate()

    assert "text" in result
    assert "sections" in result
    assert "unavailable" in result
    assert "timestamp" in result


@patch("jarvis.brief.notifier.notify")
@patch("jarvis.core._ask_ollama", return_value="Synthesised brief text.")
def test_generate_calls_all_adapters(mock_llm, mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    mock_adapters = {
        name: MagicMock(safe_run=MagicMock(return_value=_ok(f"{name} data")))
        for name in ["investor", "weather", "summerpuppy", "homeops_grocery", "grocery"]
    }
    with patch.object(engine, "_adapter_map", mock_adapters):
        result = engine.generate()

    assert "investor" in result["sections"]
    assert "summerpuppy" in result["sections"]
    assert "homeops_grocery" in result["sections"]
    assert "grocery" in result["sections"]
    assert result["unavailable"] == []


@patch("jarvis.brief.notifier.notify")
@patch("jarvis.core._ask_ollama", return_value="Brief with some down.")
def test_generate_skips_failed_adapters(mock_llm, mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch.object(engine, "_adapter_map", {
        "investor": MagicMock(safe_run=MagicMock(return_value=_ok("market"))),
        "summerpuppy": MagicMock(safe_run=MagicMock(return_value=_fail())),
        "homeops_grocery": MagicMock(safe_run=MagicMock(return_value=_ok("groceries"))),
        "grocery": MagicMock(safe_run=MagicMock(return_value=_fail())),
    }):
        result = engine.generate()

    assert "investor" in result["sections"]
    assert "homeops_grocery" in result["sections"]
    assert "summerpuppy" in result["unavailable"]
    assert "grocery" in result["unavailable"]


@patch("jarvis.brief.notifier.notify")
def test_generate_all_down_returns_graceful_message(mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch.object(engine, "_adapter_map", {
        name: MagicMock(safe_run=MagicMock(return_value=_fail()))
        for name in ["investor", "summerpuppy", "homeops_grocery", "grocery"]
    }):
        result = engine.generate()

    assert "unavailable" in result["text"].lower() or "All" in result["text"]
    assert result["sections"] == []


@patch("jarvis.brief.notifier.notify")
@patch("jarvis.core._ask_ollama", return_value="Morning brief text.")
def test_generate_logs_to_agent_memory(mock_llm, mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch.object(engine, "_adapter_map", {
        "investor": MagicMock(safe_run=MagicMock(return_value=_ok("market"))),
        "summerpuppy": MagicMock(safe_run=MagicMock(return_value=_ok("security"))),
        "homeops_grocery": MagicMock(safe_run=MagicMock(return_value=_ok("home"))),
        "grocery": MagicMock(safe_run=MagicMock(return_value=_ok("shop"))),
    }):
        engine.generate()

    decisions = am.query(agent="brief_engine")
    assert len(decisions) == 1
    assert decisions[0]["capability"] == "generate"


@patch("jarvis.brief.notifier.notify")
@patch("jarvis.core._ask_ollama", return_value="Brief pushed to Discord.")
def test_generate_calls_notifier(mock_llm, mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch.object(engine, "_adapter_map", {
        "investor": MagicMock(safe_run=MagicMock(return_value=_ok("market"))),
        "summerpuppy": MagicMock(safe_run=MagicMock(return_value=_ok("sec"))),
        "homeops_grocery": MagicMock(safe_run=MagicMock(return_value=_ok("home"))),
        "grocery": MagicMock(safe_run=MagicMock(return_value=_ok("shop"))),
    }):
        engine.generate()

    mock_notify.assert_called_once()


@patch("jarvis.brief.notifier.notify")
@patch("jarvis.core._ask_ollama", return_value="Stored brief.")
def test_generate_stores_to_briefs_jsonl(mock_llm, mock_notify, tmp_path, monkeypatch):
    import json
    import jarvis.brief as brief_mod
    briefs_path = str(tmp_path / "briefs.jsonl")
    monkeypatch.setattr(brief_mod, "BRIEFS_PATH", briefs_path)

    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch.object(engine, "_adapter_map", {
        "investor": MagicMock(safe_run=MagicMock(return_value=_ok("market"))),
        "summerpuppy": MagicMock(safe_run=MagicMock(return_value=_ok("sec"))),
        "homeops_grocery": MagicMock(safe_run=MagicMock(return_value=_ok("home"))),
        "grocery": MagicMock(safe_run=MagicMock(return_value=_ok("shop"))),
    }):
        engine.generate()

    lines = open(briefs_path).read().strip().split("\n")
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert "text" in entry
    assert "timestamp" in entry


# ── _synthesize fallback ──────────────────────────────────────────────────────

def test_synthesize_fallback_when_llm_down():
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    with patch("jarvis.core._ask_ollama", side_effect=Exception("LLM down")):
        text = engine._synthesize(
            {"investor": "market data", "grocery": "shopping data"},
            ["summerpuppy"],
        )
    assert "INVESTOR" in text or "investor" in text.lower()
    assert "GROCERY" in text or "grocery" in text.lower()


def test_synthesize_empty_sections_returns_all_unavailable():
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    text = engine._synthesize({}, ["investor", "summerpuppy"])
    assert "unavailable" in text.lower() or "All" in text


# ── missing adapter ───────────────────────────────────────────────────────────

@patch("jarvis.brief.notifier.notify")
def test_generate_handles_missing_adapter_name(mock_notify):
    from jarvis.brief import BriefEngine
    engine = BriefEngine()
    # Only provide some adapters in the map
    with patch.object(engine, "_adapter_map", {
        "investor": MagicMock(safe_run=MagicMock(return_value=_ok("market"))),
    }):
        result = engine.generate()

    assert "investor" in result["sections"]
    assert len(result["unavailable"]) == 4  # weather, summerpuppy, homeops_grocery, grocery
