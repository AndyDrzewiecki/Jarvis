"""Tests for jarvis.guideline_evolver — TDD Wave 4.1."""
from __future__ import annotations
import os
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evolver(tmp_path):
    from jarvis.guideline_evolver import GuidelineEvolver
    return GuidelineEvolver(library_root=str(tmp_path / "library"))


# ---------------------------------------------------------------------------
# 1. test_load_guidelines_missing_returns_empty
# ---------------------------------------------------------------------------

def test_load_guidelines_missing_returns_empty(tmp_path):
    evolver = _make_evolver(tmp_path)
    text, version = evolver._load_guidelines("grocery")
    assert text == ""
    assert version == 0


# ---------------------------------------------------------------------------
# 2. test_load_guidelines_parses_version
# ---------------------------------------------------------------------------

def test_load_guidelines_parses_version(tmp_path):
    lib = tmp_path / "library" / "grocery"
    lib.mkdir(parents=True)
    (lib / "guidelines.md").write_text(
        "# Grocery Specialist Guidelines v3\n\nSome content here."
    )
    evolver = _make_evolver(tmp_path)
    text, version = evolver._load_guidelines("grocery")
    assert version == 3
    assert "Some content here." in text


# ---------------------------------------------------------------------------
# 3. test_save_guidelines_creates_file
# ---------------------------------------------------------------------------

def test_save_guidelines_creates_file(tmp_path):
    evolver = _make_evolver(tmp_path)
    evolver._save_guidelines("grocery", "My guideline text.", 2)
    path = tmp_path / "library" / "grocery" / "guidelines.md"
    assert path.exists()
    content = path.read_text()
    assert "v2" in content
    assert "My guideline text." in content


# ---------------------------------------------------------------------------
# 4. test_evolve_no_grades_returns_noop
# ---------------------------------------------------------------------------

def test_evolve_no_grades_returns_noop(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "query", lambda **kwargs: [{"id": "d1", "decision": "foo", "reasoning": "bar"}])
    monkeypatch.setattr(am, "get_grade", lambda decision_id: None)
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    evolver = _make_evolver(tmp_path)
    result = evolver.evolve("grocery")

    assert result.old_version == result.new_version
    assert result.patterns_analyzed == 0
    assert "No graded decisions" in result.changes_summary


# ---------------------------------------------------------------------------
# 5. test_evolve_with_grades_calls_llm
# ---------------------------------------------------------------------------

def test_evolve_with_grades_calls_llm(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    decisions = [
        {"id": "d1", "decision": "buy apples", "reasoning": "cheap"},
        {"id": "d2", "decision": "skip bananas", "reasoning": "expensive"},
        {"id": "d3", "decision": "try mango", "reasoning": "seasonal"},
        {"id": "d4", "decision": "bulk rice", "reasoning": "budget"},
    ]
    grades = {
        "d1": {"short_term_grade": "poor", "short_term_reason": "bad choice"},
        "d2": {"short_term_grade": "poor", "short_term_reason": "missed sale"},
        "d3": {"short_term_grade": "good", "short_term_reason": "tasty"},
        "d4": {"short_term_grade": "good", "short_term_reason": "saved money"},
    }
    monkeypatch.setattr(am, "query", lambda **kwargs: decisions)
    monkeypatch.setattr(am, "get_grade", lambda decision_id: grades.get(decision_id))
    monkeypatch.setattr(am, "log_decision", lambda **kwargs: "x")

    llm_calls = []

    def fake_ask(prompt, model=None):
        llm_calls.append(prompt)
        if "corrective" in prompt.lower() or "AVOID" in prompt or "WHEN" in prompt or "POOR" in prompt:
            return "AVOID: making impulsive purchases without checking prices."
        if "reinforcement" in prompt.lower() or "PREFER" in prompt or "GOOD" in prompt:
            return "PREFER: buying seasonal produce for better value."
        # merge call
        return "## Merged Guidelines\nKeep doing good things."

    import jarvis.core as core
    monkeypatch.setattr(core, "_ask_ollama", fake_ask)

    evolver = _make_evolver(tmp_path)
    result = evolver.evolve("grocery")

    assert result.new_version == result.old_version + 1
    assert result.patterns_analyzed == 4
    assert result.corrective_count > 0
    assert result.reinforcement_count > 0
    assert len(llm_calls) > 0


# ---------------------------------------------------------------------------
# 6. test_draft_corrective_guideline
# ---------------------------------------------------------------------------

def test_draft_corrective_guideline(tmp_path, monkeypatch):
    import jarvis.core as core
    monkeypatch.setattr(core, "_ask_ollama", lambda prompt, model=None: "AVOID: something bad.\nExtra line")

    evolver = _make_evolver(tmp_path)
    pattern = {
        "decision": {"decision": "bad decision", "reasoning": "poor logic"},
        "grade": {"short_term_grade": "poor", "short_term_reason": "it failed"},
    }
    result = evolver._draft_corrective_guideline(pattern, "grocery")
    assert result == "AVOID: something bad."


# ---------------------------------------------------------------------------
# 7. test_draft_corrective_guideline_llm_failure
# ---------------------------------------------------------------------------

def test_draft_corrective_guideline_llm_failure(tmp_path, monkeypatch):
    import jarvis.core as core
    monkeypatch.setattr(core, "_ask_ollama", lambda prompt, model=None: (_ for _ in ()).throw(RuntimeError("LLM down")))

    evolver = _make_evolver(tmp_path)
    pattern = {
        "decision": {"decision": "bad decision", "reasoning": "poor logic"},
        "grade": {"short_term_grade": "poor", "short_term_reason": "it failed"},
    }
    result = evolver._draft_corrective_guideline(pattern, "grocery")
    assert result is None


# ---------------------------------------------------------------------------
# 8. test_draft_reinforcement_guideline
# ---------------------------------------------------------------------------

def test_draft_reinforcement_guideline(tmp_path, monkeypatch):
    import jarvis.core as core
    monkeypatch.setattr(core, "_ask_ollama", lambda prompt, model=None: "PREFER: buying local produce.\nMore text")

    evolver = _make_evolver(tmp_path)
    pattern = {
        "decision": {"decision": "good decision", "reasoning": "smart choice"},
        "grade": {"short_term_grade": "good", "short_term_reason": "worked well"},
    }
    result = evolver._draft_reinforcement_guideline(pattern, "grocery")
    assert result == "PREFER: buying local produce."


# ---------------------------------------------------------------------------
# 9. test_merge_guidelines_uses_llm
# ---------------------------------------------------------------------------

def test_merge_guidelines_uses_llm(tmp_path, monkeypatch):
    import jarvis.core as core
    merged_text = "## Merged\nNew combined guidelines."
    monkeypatch.setattr(core, "_ask_ollama", lambda prompt, model=None: merged_text)

    evolver = _make_evolver(tmp_path)
    result = evolver._merge_guidelines(
        "Old guidelines text.",
        ["AVOID: bad thing"],
        ["PREFER: good thing"],
        "grocery",
    )
    assert result == merged_text


# ---------------------------------------------------------------------------
# 10. test_merge_guidelines_fallback_on_error
# ---------------------------------------------------------------------------

def test_merge_guidelines_fallback_on_error(tmp_path, monkeypatch):
    import jarvis.core as core
    monkeypatch.setattr(core, "_ask_ollama", lambda prompt, model=None: (_ for _ in ()).throw(RuntimeError("LLM down")))

    evolver = _make_evolver(tmp_path)
    current = "Existing guidelines."
    result = evolver._merge_guidelines(
        current,
        ["AVOID: bad thing"],
        ["PREFER: good thing"],
        "grocery",
    )
    assert current in result
    assert "AVOID: bad thing" in result
    assert "PREFER: good thing" in result
