from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
import jarvis.agent_memory as am


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    db = str(tmp_path / "decisions.db")
    monkeypatch.setattr(am, "DB_PATH", db)
    am._inited.discard(db)


@pytest.fixture
def mock_blackboard():
    bb = MagicMock()
    bb.read.return_value = []
    bb.post.return_value = None
    return bb


def test_specialist_registered():
    """MetacognitiveSpec is in SPECIALIST_REGISTRY."""
    # Import triggers registration via @register
    import jarvis.specialists.metacognitive  # noqa: F401
    from jarvis.specialists import SPECIALIST_REGISTRY
    names = [cls.name for cls in SPECIALIST_REGISTRY]
    assert "metacognitive_supervisor" in names


def test_gather_reads_decisions(tmp_path, monkeypatch, mock_blackboard):
    """gather() pulls recent decisions from agent_memory."""
    # Seed a decision
    am.log_decision(
        agent="grocery_specialist",
        capability="run_cycle",
        decision="Did grocery run",
        reasoning="all good",
        outcome="success",
    )

    from jarvis.specialists.metacognitive import MetacognitiveSpec
    spec = MetacognitiveSpec()
    spec._blackboard = mock_blackboard

    items = spec.gather()
    # Should include at least one decision item
    decision_items = [i for i in items if "decision" in i]
    assert len(decision_items) >= 1


def test_analyze_computes_score(tmp_path, monkeypatch, mock_blackboard):
    """analyze() with mixed outcomes returns insights with performance info."""
    from jarvis.specialists.metacognitive import MetacognitiveSpec

    gathered = [
        {"decision": {"id": "d1", "agent": "grocery_specialist", "outcome": "success"}, "grade": {"short_term_grade": "good"}},
        {"decision": {"id": "d2", "agent": "grocery_specialist", "outcome": "success"}, "grade": {"short_term_grade": "good"}},
        {"decision": {"id": "d3", "agent": "grocery_specialist", "outcome": "failure"}, "grade": {"short_term_grade": "poor"}},
    ]

    spec = MetacognitiveSpec()
    spec._blackboard = mock_blackboard

    with patch("jarvis.core._ask_ollama", return_value="REC: review grocery thresholds"):
        insights = spec.analyze(gathered)

    # Should return some insights (recommendation + possibly underperformer)
    assert isinstance(insights, list)


def test_analyze_identifies_underperformer(tmp_path, monkeypatch, mock_blackboard):
    """All failures → underperformer insight created for that agent."""
    from jarvis.specialists.metacognitive import MetacognitiveSpec
    from jarvis.memory_tiers.types import Insight

    gathered = [
        {"decision": {"id": f"d{i}", "agent": "broken_agent", "outcome": "failure"}, "grade": {"short_term_grade": "poor"}}
        for i in range(5)
    ]

    spec = MetacognitiveSpec()
    spec._blackboard = mock_blackboard

    with patch("jarvis.core._ask_ollama", return_value="NONE"):
        insights = spec.analyze(gathered)

    underperformer_insights = [ins for ins in insights if "broken_agent" in ins.content and "underperform" in ins.content]
    assert len(underperformer_insights) >= 1


def test_analyze_posts_to_blackboard(tmp_path, monkeypatch, mock_blackboard):
    """analyze() calls blackboard.post with topic 'system_health' when LLM returns REC."""
    from jarvis.specialists.metacognitive import MetacognitiveSpec

    gathered = [
        {"decision": {"id": "d1", "agent": "some_agent", "outcome": "success"}, "grade": {"short_term_grade": "good"}},
    ]

    spec = MetacognitiveSpec()
    spec._blackboard = mock_blackboard

    with patch("jarvis.core._ask_ollama", return_value="REC: optimize routing logic"):
        spec.analyze(gathered)

    # blackboard.post should have been called with topic=system_health
    calls = mock_blackboard.post.call_args_list
    topics = [c.kwargs.get("topic") or (c.args[1] if len(c.args) > 1 else None) for c in calls]
    assert "system_health" in topics


def test_analyze_mocked_llm(tmp_path, monkeypatch, mock_blackboard):
    """analyze() with mocked LLM returns insights without crash."""
    from jarvis.specialists.metacognitive import MetacognitiveSpec

    gathered = [
        {"decision": {"id": "d1", "agent": "test_agent", "outcome": "success"}, "grade": None},
    ]

    spec = MetacognitiveSpec()
    spec._blackboard = mock_blackboard

    with patch("jarvis.core._ask_ollama", return_value="REC: no changes needed"):
        insights = spec.analyze(gathered)

    assert isinstance(insights, list)


def test_improve_no_crash(tmp_path, monkeypatch, mock_blackboard):
    """improve() runs without errors and returns a list."""
    from jarvis.specialists.metacognitive import MetacognitiveSpec

    spec = MetacognitiveSpec()
    spec._blackboard = mock_blackboard

    result = spec.improve()
    assert isinstance(result, list)
