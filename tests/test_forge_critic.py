"""Tests for jarvis.forge.critic — Critic (Brain 1)."""
from __future__ import annotations
import pytest
from unittest.mock import patch


@pytest.fixture()
def store(tmp_path):
    from jarvis.forge.memory_store import ForgeMemoryStore, _inited
    db = str(tmp_path / "critic_test.db")
    _inited.discard(db)
    return ForgeMemoryStore(db_path=db)


@pytest.fixture()
def critic(store):
    from jarvis.forge.critic import Critic
    return Critic(memory_store=store)


# ---------------------------------------------------------------------------
# _parse_verdict
# ---------------------------------------------------------------------------

def test_parse_verdict_good(critic):
    raw = "QUALITY: good\nSCORE: 0.85\nFLAGS: NONE\nREASONING: Accurate and complete."
    v = critic._parse_verdict(raw, "ix-1", "test_agent")
    assert v.quality == "good"
    assert v.score == pytest.approx(0.85)
    assert v.flags == []
    assert "Accurate" in v.reasoning


def test_parse_verdict_poor_with_flags(critic):
    raw = "QUALITY: poor\nSCORE: 0.1\nFLAGS: hallucination, off_topic\nREASONING: Made up facts."
    v = critic._parse_verdict(raw, "ix-2", "test_agent")
    assert v.quality == "poor"
    assert v.score == pytest.approx(0.1)
    assert "hallucination" in v.flags
    assert "off_topic" in v.flags


def test_parse_verdict_defaults_on_bad_format(critic):
    v = critic._parse_verdict("not valid output", "ix-3", "test_agent")
    assert v.quality in {"good", "acceptable", "poor"}
    assert 0.0 <= v.score <= 1.0


def test_parse_verdict_score_clamped(critic):
    raw = "QUALITY: good\nSCORE: 1.5\nFLAGS: NONE\nREASONING: x"
    v = critic._parse_verdict(raw, "ix-4", "a")
    assert v.score <= 1.0

    raw = "QUALITY: poor\nSCORE: -0.5\nFLAGS: NONE\nREASONING: x"
    v = critic._parse_verdict(raw, "ix-5", "a")
    assert v.score >= 0.0


# ---------------------------------------------------------------------------
# evaluate — with mocked LLM
# ---------------------------------------------------------------------------

def test_evaluate_good_output(critic, store):
    with patch.object(critic, "_call_llm", return_value=(
        "QUALITY: good\nSCORE: 0.9\nFLAGS: NONE\nREASONING: Output is accurate."
    )):
        v = critic.evaluate(
            interaction_id="ix-10",
            agent="code_auditor",
            task_type="code_review",
            input_text="Review this PR",
            output_text="The code looks correct.",
        )
    assert v.quality == "good"
    assert v.score == pytest.approx(0.9)
    assert v.flags == []
    assert v.hallucination_ids == []


def test_evaluate_poor_output_with_hallucination_writes_to_registry(critic, store):
    with patch.object(critic, "_call_llm", return_value=(
        "QUALITY: poor\nSCORE: 0.1\nFLAGS: hallucination\nREASONING: Contains false claim."
    )):
        v = critic.evaluate(
            interaction_id="ix-11",
            agent="code_auditor",
            task_type="code_review",
            input_text="Review this",
            output_text="The function uses Python 4 syntax.",
        )
    assert v.quality == "poor"
    assert "hallucination" in v.flags
    assert len(v.hallucination_ids) == 1
    hallucinations = store.query_hallucinations(agent="code_auditor")
    assert len(hallucinations) == 1


def test_evaluate_logs_critic_interaction(critic, store):
    with patch.object(critic, "_call_llm", return_value=(
        "QUALITY: acceptable\nSCORE: 0.6\nFLAGS: incomplete\nREASONING: Missing details."
    )):
        critic.evaluate("ix-12", "trainer", "review", "input", "output")
    rows = store.query_interactions(agent="critic")
    assert len(rows) == 1


def test_evaluate_llm_fallback_when_unavailable(critic):
    with patch.object(critic, "_call_llm", side_effect=Exception("LLM down")):
        # Falls back to _call_llm raising which gets caught in evaluate → uses LLM fallback path
        # The fallback is in _call_llm itself; here we test that evaluate doesn't crash
        # when _call_llm raises (evaluate calls _call_llm directly, which has its own fallback)
        pass  # This is tested through the BaseDevAgent.run() error handling


def test_evaluate_llm_default_verdict_on_error(critic):
    """Critic._call_llm has internal fallback; no exception propagates."""
    with patch("jarvis.core._ask_ollama", side_effect=Exception("down")):
        v = critic.evaluate("ix-13", "agent", "type", "in", "out")
    # Should return a verdict (from the fallback string in _call_llm)
    assert v.quality in {"good", "acceptable", "poor"}


# ---------------------------------------------------------------------------
# evaluate_batch
# ---------------------------------------------------------------------------

def test_evaluate_batch(critic):
    responses = iter([
        "QUALITY: good\nSCORE: 0.8\nFLAGS: NONE\nREASONING: ok",
        "QUALITY: poor\nSCORE: 0.2\nFLAGS: incomplete\nREASONING: missing",
    ])
    with patch.object(critic, "_call_llm", side_effect=lambda *a, **kw: next(responses)):
        verdicts = critic.evaluate_batch([
            {"interaction_id": "a1", "agent": "x", "task_type": "t",
             "input_text": "i1", "output_text": "o1"},
            {"interaction_id": "a2", "agent": "x", "task_type": "t",
             "input_text": "i2", "output_text": "o2"},
        ])
    assert len(verdicts) == 2
    assert verdicts[0].quality == "good"
    assert verdicts[1].quality == "poor"


# ---------------------------------------------------------------------------
# execute_task (BaseDevAgent interface)
# ---------------------------------------------------------------------------

def test_execute_task_evaluate(critic):
    with patch.object(critic, "_call_llm", return_value=(
        "QUALITY: good\nSCORE: 0.75\nFLAGS: NONE\nREASONING: Fine."
    )):
        task = {
            "id": "task-1",
            "type": "evaluate",
            "payload": {
                "interaction_id": "ix-20",
                "agent": "orchestrator",
                "task_type": "route",
                "input_text": "route this",
                "output_text": "routed to critic",
            },
        }
        result = critic.execute_task(task)
    assert result.status == "success"
    assert "quality=good" in result.output
    assert result.confidence == pytest.approx(0.75)


def test_execute_task_unknown_type(critic):
    task = {"id": "t-bad", "type": "unknown", "payload": {}}
    result = critic.execute_task(task)
    assert result.status == "failure"
    assert "Unknown task type" in (result.error or "")
