from __future__ import annotations
import pytest
from unittest.mock import patch


@pytest.fixture
def proc_store(tmp_path):
    from jarvis.memory_tiers.procedural import ProceduralStore
    return ProceduralStore(db_path=str(tmp_path / "procedures.db"))


@pytest.fixture
def episodic_store(tmp_path):
    from jarvis.memory_tiers.episodic import EpisodicStore
    return EpisodicStore(db_path=str(tmp_path / "episodes.db"))


def test_compile_from_episodes_no_pattern(proc_store):
    """LLM returns 'NONE' → compile_from_episodes returns None."""
    episodes = [
        {"id": f"ep{i}", "domain": "grocery", "summary": "grocery chat"}
        for i in range(3)
    ]
    messages_by_episode = {ep["id"]: [{"role": "user", "content": "buy milk"}] for ep in episodes}

    with patch("jarvis.core._ask_ollama", return_value="NONE"):
        result = proc_store.compile_from_episodes(episodes, messages_by_episode)

    assert result is None


def test_compile_from_episodes_creates_procedure(proc_store):
    """Valid LLM response → compile_from_episodes returns a procedure ID."""
    episodes = [
        {"id": f"ep{i}", "domain": "grocery", "summary": "grocery chat"}
        for i in range(5)
    ]
    messages_by_episode = {
        ep["id"]: [{"role": "user", "content": "show me the shopping list"}]
        for ep in episodes
    }

    llm_response = (
        "TRIGGER: show me the shopping list\n"
        "ACTION: grocery:shopping_list\n"
        "CONFIDENCE: 0.85\n"
    )
    with patch("jarvis.core._ask_ollama", return_value=llm_response):
        result = proc_store.compile_from_episodes(episodes, messages_by_episode)

    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0

    # Verify it's in the store
    all_procs = proc_store.all()
    assert any(p["id"] == result for p in all_procs)


def test_parse_compilation_valid(proc_store):
    """Valid TRIGGER/ACTION/CONFIDENCE lines → procedure created and ID returned."""
    raw = (
        "TRIGGER: what's for dinner\n"
        "ACTION: grocery:meal_plan\n"
        "CONFIDENCE: 0.9\n"
    )
    result = proc_store._parse_compilation(raw, ["ep1", "ep2"])
    assert result is not None

    all_procs = proc_store.all()
    created = next((p for p in all_procs if p["id"] == result), None)
    assert created is not None
    assert "dinner" in created["trigger_pattern"]
    assert created["confidence"] >= 0.9


def test_parse_compilation_low_confidence(proc_store):
    """CONFIDENCE: 0.3 is below 0.5 threshold → returns None."""
    raw = (
        "TRIGGER: some trigger\n"
        "ACTION: grocery:shopping_list\n"
        "CONFIDENCE: 0.3\n"
    )
    result = proc_store._parse_compilation(raw, ["ep1"])
    assert result is None


def test_parse_compilation_missing_action(proc_store):
    """TRIGGER but no ACTION → returns None."""
    raw = (
        "TRIGGER: some trigger\n"
        "CONFIDENCE: 0.9\n"
    )
    result = proc_store._parse_compilation(raw, ["ep1"])
    assert result is None
