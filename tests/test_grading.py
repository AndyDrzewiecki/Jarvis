from __future__ import annotations
import pytest
from unittest.mock import patch
import jarvis.agent_memory as am


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))


def test_grade_short_term_good_outcome():
    from jarvis.grading import DecisionGrader
    decision = {"id": "d1", "outcome": "success", "capability": "meal_plan",
                "decision": "Generated meal plan", "reasoning": "User asked for meals"}
    with patch("jarvis.core._ask_ollama", return_value="GRADE: good\nSCORE: 0.9\nREASON: Successful meal plan."):
        grader = DecisionGrader()
        result = grader.grade_short_term(decision)
    assert result["grade"] == "good"
    assert result["score"] == pytest.approx(0.9)
    assert "meal" in result["reason"].lower() or len(result["reason"]) > 0


def test_grade_short_term_poor_outcome():
    from jarvis.grading import DecisionGrader
    decision = {"id": "d2", "outcome": "failure", "capability": "route_message",
                "decision": "Failed to route", "reasoning": "Error"}
    with patch("jarvis.core._ask_ollama", return_value="GRADE: poor\nSCORE: 0.1\nREASON: Routing failed."):
        grader = DecisionGrader()
        result = grader.grade_short_term(decision)
    assert result["grade"] == "poor"
    assert result["score"] < 0.5


def test_grade_short_term_llm_fallback():
    """When LLM fails, uses outcome field as fallback."""
    from jarvis.grading import DecisionGrader
    decision = {"id": "d3", "outcome": "success", "capability": "test",
                "decision": "ok", "reasoning": "ok"}
    with patch("jarvis.core._ask_ollama", side_effect=Exception("LLM down")):
        grader = DecisionGrader()
        result = grader.grade_short_term(decision)
    assert result["grade"] == "good"
    assert result["score"] >= 0.5


def test_save_and_get_grade():
    gid = am.save_grade("dec-1", "good", 0.9, "Well done", "test-model")
    assert isinstance(gid, str)
    grade = am.get_grade("dec-1")
    assert grade is not None
    assert grade["short_term_grade"] == "good"
    assert grade["short_term_score"] == pytest.approx(0.9)
    assert grade["grading_model"] == "test-model"


def test_save_grade_updates_existing():
    am.save_grade("dec-2", "poor", 0.2, "bad", "model-a")
    am.save_grade("dec-2", "good", 0.8, "actually good", "model-b")
    grade = am.get_grade("dec-2")
    assert grade["short_term_grade"] == "good"
    assert grade["short_term_score"] == pytest.approx(0.8)


def test_get_grade_returns_none_for_ungraded():
    result = am.get_grade("nonexistent-decision-id")
    assert result is None


def test_get_ungraded_decisions_returns_recent():
    am.log_decision("router", "route_message", "d1", "r1", outcome="success")
    am.log_decision("grocery", "meal_plan", "d2", "r2", outcome="success")
    ungraded = am.get_ungraded_decisions(since_hours=1)
    assert len(ungraded) == 2


def test_get_ungraded_excludes_already_graded():
    did = am.log_decision("router", "route", "d1", "r1", outcome="success")
    am.save_grade(did, "good", 0.9, "fine", "model")
    ungraded = am.get_ungraded_decisions(since_hours=1)
    assert all(d["id"] != did for d in ungraded)


def test_run_short_term_batch_grades_all(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "batch.db"))
    am._inited.discard(str(tmp_path / "batch.db"))
    am.log_decision("a", "b", "d1", "r1", outcome="success")
    am.log_decision("a", "b", "d2", "r2", outcome="failure")
    from jarvis.grading import DecisionGrader
    with patch("jarvis.core._ask_ollama", return_value="GRADE: good\nSCORE: 0.8\nREASON: ok"):
        grader = DecisionGrader()
        count = grader.run_short_term_batch()
    assert count == 2
    ungraded = am.get_ungraded_decisions(since_hours=1)
    assert len(ungraded) == 0


def test_run_short_term_batch_empty():
    from jarvis.grading import DecisionGrader
    grader = DecisionGrader()
    count = grader.run_short_term_batch()
    assert count == 0
