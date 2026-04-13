from __future__ import annotations
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call
import pytest


def _make_episode_db(tmp_path) -> str:
    """Create an episodic store DB, return path."""
    db_path = str(tmp_path / "episodes.db")
    return db_path


def _seed_episode(episodic_store, messages: list[tuple[str, str]]) -> str:
    """Seed an episode with given (role, content) messages. Returns episode_id."""
    eid = episodic_store.start_episode()
    episodic_store.end_episode(eid, summary="test episode")
    for role, content in messages:
        episodic_store.add_message(eid, role, content)
    return eid


# ── test_run_processes_episodes ───────────────────────────────────────────────

def test_run_processes_episodes(tmp_path):
    """2 episodes with messages → run() returns report with episodes_processed=2, facts_created>0."""
    from jarvis.memory_tiers.episodic import EpisodicStore
    ep_db = str(tmp_path / "episodes.db")
    store = EpisodicStore(db_path=ep_db)
    eid1 = _seed_episode(store, [("user", "I prefer brief answers"), ("assistant", "Got it")])
    eid2 = _seed_episode(store, [("user", "What's the weather?"), ("assistant", "Sunny")])

    llm_response = "FACT: knowledge | User prefers brief answers | 0.8"

    mock_bus = MagicMock()
    mock_bus.episodic.get_unconsolidated.return_value = [
        {"id": eid1, "summary": "ep1", "domain": None},
        {"id": eid2, "summary": "ep2", "domain": None},
    ]
    mock_bus.episodic.get_messages.side_effect = [
        [{"role": "user", "content": "I prefer brief answers"}, {"role": "assistant", "content": "Got it"}],
        [{"role": "user", "content": "What's the weather?"}, {"role": "assistant", "content": "Sunny"}],
    ]

    mock_lake = MagicMock()
    mock_lake.search.return_value = []

    with patch("jarvis.core._ask_ollama", return_value=llm_response), \
         patch("jarvis.consolidation.ConsolidationEngine.bus", new_callable=lambda: property(lambda self: mock_bus)), \
         patch("jarvis.consolidation.ConsolidationEngine.lake", new_callable=lambda: property(lambda self: mock_lake)):
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine()
        report = engine.run()

    assert report.episodes_processed == 2
    assert report.facts_created > 0
    assert report.error is None


# ── test_run_empty_episode_skips_gracefully ───────────────────────────────────

def test_run_empty_episode_skips_gracefully(tmp_path):
    """Episode with no messages → mark_consolidated still called, facts_created=0."""
    mock_bus = MagicMock()
    mock_bus.episodic.get_unconsolidated.return_value = [
        {"id": "ep-empty", "summary": "", "domain": None},
    ]
    mock_bus.episodic.get_messages.return_value = []

    mock_lake = MagicMock()

    with patch("jarvis.core._ask_ollama", return_value="NONE"), \
         patch("jarvis.consolidation.ConsolidationEngine.bus", new_callable=lambda: property(lambda self: mock_bus)), \
         patch("jarvis.consolidation.ConsolidationEngine.lake", new_callable=lambda: property(lambda self: mock_lake)):
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine()
        report = engine.run()

    assert report.episodes_processed == 1
    assert report.facts_created == 0
    mock_bus.episodic.mark_consolidated.assert_called_once_with("ep-empty")


# ── test_run_llm_failure_doesnt_crash ─────────────────────────────────────────

def test_run_llm_failure_doesnt_crash(tmp_path):
    """LLM raises → run still completes, report.error is None."""
    mock_bus = MagicMock()
    mock_bus.episodic.get_unconsolidated.return_value = [
        {"id": "ep-fail", "summary": "ep", "domain": None},
    ]
    mock_bus.episodic.get_messages.return_value = [
        {"role": "user", "content": "hello"}
    ]

    mock_lake = MagicMock()

    with patch("jarvis.core._ask_ollama", side_effect=RuntimeError("LLM down")), \
         patch("jarvis.consolidation.ConsolidationEngine.bus", new_callable=lambda: property(lambda self: mock_bus)), \
         patch("jarvis.consolidation.ConsolidationEngine.lake", new_callable=lambda: property(lambda self: mock_lake)):
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine()
        report = engine.run()

    assert report.error is None
    assert report.episodes_processed == 1


# ── test_run_overall_error_sets_report_error ──────────────────────────────────

def test_run_overall_error_sets_report_error(tmp_path):
    """bus.episodic.get_unconsolidated raises → report.error is set, doesn't raise."""
    mock_bus = MagicMock()
    mock_bus.episodic.get_unconsolidated.side_effect = RuntimeError("DB blown up")
    mock_lake = MagicMock()

    with patch("jarvis.consolidation.ConsolidationEngine.bus", new_callable=lambda: property(lambda self: mock_bus)), \
         patch("jarvis.consolidation.ConsolidationEngine.lake", new_callable=lambda: property(lambda self: mock_lake)):
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine()
        report = engine.run()

    assert report.error is not None
    assert "DB blown up" in report.error


# ── test_extract_knowledge_parses_fact_lines ──────────────────────────────────

def test_extract_knowledge_parses_fact_lines():
    """Feed raw with 2 FACT lines → returns 2 Insights."""
    raw = "FACT: preference | User likes tea | 0.9\nFACT: knowledge | Kitchen has herbs | 0.7"
    with patch("jarvis.core._ask_ollama", return_value=raw):
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine.__new__(ConsolidationEngine)
        insights = engine._parse_extraction(raw)

    assert len(insights) == 2
    assert insights[0].fact_type == "preference"
    assert insights[0].content == "User likes tea"
    assert insights[0].confidence == pytest.approx(0.9)
    assert insights[1].fact_type == "knowledge"
    assert insights[1].content == "Kitchen has herbs"
    assert insights[1].confidence == pytest.approx(0.7)


# ── test_extract_knowledge_handles_none ──────────────────────────────────────

def test_extract_knowledge_handles_none():
    """raw='NONE' → returns []."""
    from jarvis.consolidation import ConsolidationEngine
    engine = ConsolidationEngine.__new__(ConsolidationEngine)
    insights = engine._parse_extraction("NONE")
    assert insights == []


# ── test_extract_knowledge_handles_malformed ─────────────────────────────────

def test_extract_knowledge_handles_malformed():
    """raw='not a fact line' → returns []."""
    from jarvis.consolidation import ConsolidationEngine
    engine = ConsolidationEngine.__new__(ConsolidationEngine)
    insights = engine._parse_extraction("not a fact line")
    assert insights == []


# ── test_merge_creates_new_when_no_match ─────────────────────────────────────

def test_merge_creates_new_when_no_match():
    """lake.search returns [] → action is 'created', store_fact called."""
    from jarvis.consolidation import ConsolidationEngine
    from jarvis.specialists.base import Insight

    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.return_value = "fact-id-1"

    engine = ConsolidationEngine.__new__(ConsolidationEngine)
    insight = Insight(fact_type="preference", content="User likes tea", confidence=0.9)
    action = engine._merge_into_semantic(insight, mock_lake)

    assert action == "created"
    mock_lake.store_fact.assert_called_once()


# ── test_merge_reinforces_when_match_found ────────────────────────────────────

def test_merge_reinforces_when_match_found():
    """lake.search returns a match → action is 'reinforced'."""
    from jarvis.consolidation import ConsolidationEngine
    from jarvis.specialists.base import Insight

    mock_lake = MagicMock()
    mock_lake.search.return_value = [{"summary": "User likes tea briefly", "id": "existing-1"}]

    engine = ConsolidationEngine.__new__(ConsolidationEngine)
    insight = Insight(fact_type="preference", content="User likes tea", confidence=0.9)
    action = engine._merge_into_semantic(insight, mock_lake)

    assert action == "reinforced"


# ── test_episodes_marked_consolidated ────────────────────────────────────────

def test_episodes_marked_consolidated():
    """mark_consolidated called for each episode."""
    mock_bus = MagicMock()
    ep_ids = ["ep-1", "ep-2", "ep-3"]
    mock_bus.episodic.get_unconsolidated.return_value = [
        {"id": eid, "summary": "s", "domain": None} for eid in ep_ids
    ]
    mock_bus.episodic.get_messages.return_value = []
    mock_lake = MagicMock()

    with patch("jarvis.core._ask_ollama", return_value="NONE"), \
         patch("jarvis.consolidation.ConsolidationEngine.bus", new_callable=lambda: property(lambda self: mock_bus)), \
         patch("jarvis.consolidation.ConsolidationEngine.lake", new_callable=lambda: property(lambda self: mock_lake)):
        from jarvis.consolidation import ConsolidationEngine
        engine = ConsolidationEngine()
        engine.run()

    called_ids = [c.args[0] for c in mock_bus.episodic.mark_consolidated.call_args_list]
    for eid in ep_ids:
        assert eid in called_ids
