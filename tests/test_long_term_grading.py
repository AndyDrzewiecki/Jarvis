from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
import pytest


def _make_db(tmp_path):
    """Helper: create a fresh decisions DB and return its path."""
    db_path = str(tmp_path / "decisions.db")
    return db_path


def _seed_decision(db_path: str, age_days: float = 10, decision_id: str | None = None) -> str:
    """Insert a decision row and return its id."""
    import uuid
    did = decision_id or str(uuid.uuid4())
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat()
    import jarvis.agent_memory as am
    conn = am._open(db_path)
    conn.execute(
        """INSERT INTO decisions (id, timestamp, agent, capability, decision, reasoning)
           VALUES (?,?,?,?,?,?)""",
        (did, ts, "test_agent", "test_cap", "test decision", "test reasoning"),
    )
    conn.commit()
    conn.close()
    return did


def _seed_grade(db_path: str, decision_id: str, long_term_grade: str | None = None) -> None:
    """Insert a grade row with optional long_term_grade."""
    import uuid
    import jarvis.agent_memory as am
    conn = am._open(db_path)
    grade_id = str(uuid.uuid4())
    conn.execute(
        """INSERT OR REPLACE INTO decision_grades
           (id, decision_id, short_term_grade, short_term_score, short_term_reason,
            short_term_graded_at, long_term_grade)
           VALUES (?,?,?,?,?,?,?)""",
        (grade_id, decision_id, "good", 0.8, "Looks good",
         datetime.now(timezone.utc).isoformat(), long_term_grade),
    )
    conn.commit()
    conn.close()


# ── test_grade_long_term_returns_dict ─────────────────────────────────────────

def test_grade_long_term_returns_dict(tmp_path):
    """LLM returns structured response → grade_long_term returns parsed dict."""
    db_path = _make_db(tmp_path)
    did = _seed_decision(db_path)

    decision = {"id": did, "decision": "buy apples", "capability": "grocery",
                "reasoning": "cheap this week", "outcome": "success"}
    grade = {"short_term_grade": "good", "short_term_score": 0.8,
             "short_term_reason": "Worked well"}

    llm_response = "GRADE: good\nSCORE: 0.8\nREASON: Held up well"

    with patch("jarvis.core._ask_ollama", return_value=llm_response):
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        result = grader.grade_long_term(decision, grade)

    assert result["grade"] == "good"
    assert result["score"] == pytest.approx(0.8)
    assert result["reason"] == "Held up well"


# ── test_grade_long_term_llm_failure_falls_back ───────────────────────────────

def test_grade_long_term_llm_failure_falls_back(tmp_path):
    """LLM raises exception → fallback dict returned."""
    decision = {"id": "x", "decision": "d", "capability": "c",
                "reasoning": "r", "outcome": "unknown"}
    grade = {"short_term_grade": "neutral", "short_term_score": 0.5, "short_term_reason": "ok"}

    with patch("jarvis.core._ask_ollama", side_effect=RuntimeError("LLM down")):
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        result = grader.grade_long_term(decision, grade)

    assert result["grade"] == "neutral"
    assert result["score"] == pytest.approx(0.5)
    assert "unavailable" in result["reason"].lower()


# ── test_run_long_term_batch_grades_eligible ──────────────────────────────────

def test_run_long_term_batch_grades_eligible(tmp_path, monkeypatch):
    """2 eligible decisions → run_long_term_batch returns 2."""
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setattr("jarvis.agent_memory.DB_PATH", db_path)
    import jarvis.agent_memory as am
    am._inited.discard(db_path)

    did1 = _seed_decision(db_path, age_days=10)
    did2 = _seed_decision(db_path, age_days=15)
    _seed_grade(db_path, did1)
    _seed_grade(db_path, did2)

    llm_response = "GRADE: good\nSCORE: 0.8\nREASON: Still solid"
    with patch("jarvis.core._ask_ollama", return_value=llm_response):
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        count = grader.run_long_term_batch()

    assert count == 2


# ── test_run_long_term_batch_skips_recent ─────────────────────────────────────

def test_run_long_term_batch_skips_recent(tmp_path, monkeypatch):
    """Decision only 3 days old → not eligible → returns 0."""
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setattr("jarvis.agent_memory.DB_PATH", db_path)
    import jarvis.agent_memory as am
    am._inited.discard(db_path)

    did = _seed_decision(db_path, age_days=3)
    _seed_grade(db_path, did)

    with patch("jarvis.core._ask_ollama", return_value="GRADE: good\nSCORE: 0.8\nREASON: ok"):
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        count = grader.run_long_term_batch()

    assert count == 0


# ── test_run_long_term_batch_skips_already_graded ─────────────────────────────

def test_run_long_term_batch_skips_already_graded(tmp_path, monkeypatch):
    """Decision 10 days old but long_term_grade already set → skipped."""
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setattr("jarvis.agent_memory.DB_PATH", db_path)
    import jarvis.agent_memory as am
    am._inited.discard(db_path)

    did = _seed_decision(db_path, age_days=10)
    _seed_grade(db_path, did, long_term_grade="good")

    with patch("jarvis.core._ask_ollama", return_value="GRADE: good\nSCORE: 0.8\nREASON: ok"):
        from jarvis.grading import DecisionGrader
        grader = DecisionGrader()
        count = grader.run_long_term_batch()

    assert count == 0


# ── test_get_decisions_for_long_term_grading_filters_by_age ───────────────────

def test_get_decisions_for_long_term_grading_filters_by_age(tmp_path, monkeypatch):
    """Seed decisions at 3d, 10d, 35d → only the 10d one is returned."""
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setattr("jarvis.agent_memory.DB_PATH", db_path)
    import jarvis.agent_memory as am
    am._inited.discard(db_path)

    did_3 = _seed_decision(db_path, age_days=3)
    did_10 = _seed_decision(db_path, age_days=10)
    did_35 = _seed_decision(db_path, age_days=35)

    _seed_grade(db_path, did_3)
    _seed_grade(db_path, did_10)
    _seed_grade(db_path, did_35)

    pairs = am.get_decisions_for_long_term_grading(min_age_days=7, max_age_days=30)
    ids = [p[0]["id"] for p in pairs]
    assert did_10 in ids
    assert did_3 not in ids
    assert did_35 not in ids


# ── test_update_long_term_grade_writes_columns ────────────────────────────────

def test_update_long_term_grade_writes_columns(tmp_path, monkeypatch):
    """update_long_term_grade writes all long_term_* columns."""
    db_path = str(tmp_path / "decisions.db")
    monkeypatch.setattr("jarvis.agent_memory.DB_PATH", db_path)
    import jarvis.agent_memory as am
    am._inited.discard(db_path)

    did = _seed_decision(db_path, age_days=10)
    _seed_grade(db_path, did)

    am.update_long_term_grade(
        decision_id=did,
        long_term_grade="poor",
        long_term_score=0.2,
        long_term_reason="Did not age well",
        model="test-model",
    )

    grade = am.get_grade(did)
    assert grade is not None
    assert grade["long_term_grade"] == "poor"
    assert grade["long_term_score"] == pytest.approx(0.2)
    assert grade["long_term_reason"] == "Did not age well"
    assert grade["long_term_graded_at"] is not None
