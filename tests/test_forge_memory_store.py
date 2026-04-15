"""Tests for jarvis.forge.memory_store — ForgeMemoryStore (7-layer introspection)."""
from __future__ import annotations
import pytest


@pytest.fixture()
def store(tmp_path):
    from jarvis.forge.memory_store import ForgeMemoryStore, _inited
    db = str(tmp_path / "forge_test.db")
    _inited.discard(db)
    return ForgeMemoryStore(db_path=db)


# ---------------------------------------------------------------------------
# Layer 1 — Interactions
# ---------------------------------------------------------------------------

def test_log_and_query_interaction(store):
    iid = store.log_interaction(
        agent="critic", input_text="evaluate this", output_text="quality=good"
    )
    assert isinstance(iid, str) and len(iid) > 0
    rows = store.query_interactions(agent="critic")
    assert len(rows) == 1
    assert rows[0]["input_text"] == "evaluate this"
    assert rows[0]["output_text"] == "quality=good"


def test_query_interactions_filter_by_task(store):
    store.log_interaction(agent="a", input_text="x", output_text="y", task_id="t1")
    store.log_interaction(agent="a", input_text="x2", output_text="y2", task_id="t2")
    rows = store.query_interactions(agent="a", task_id="t1")
    assert len(rows) == 1
    assert rows[0]["task_id"] == "t1"


def test_query_interactions_limit(store):
    for i in range(10):
        store.log_interaction(agent="a", input_text=str(i), output_text=str(i))
    rows = store.query_interactions(agent="a", limit=3)
    assert len(rows) == 3


def test_log_interaction_stores_model_and_duration(store):
    store.log_interaction(agent="a", input_text="i", output_text="o", model="gemma3:27b", duration_ms=123)
    rows = store.query_interactions(agent="a")
    assert rows[0]["model"] == "gemma3:27b"
    assert rows[0]["duration_ms"] == 123


# ---------------------------------------------------------------------------
# Layer 2 — Routing decisions
# ---------------------------------------------------------------------------

def test_log_and_query_routing(store):
    rid = store.log_routing(agent="orchestrator", routed_to="critic", reason="evaluate task")
    assert isinstance(rid, str)
    rows = store.query_routing(agent="orchestrator")
    assert len(rows) == 1
    assert rows[0]["routed_to"] == "critic"
    assert rows[0]["outcome"] == "unknown"


def test_update_routing_outcome(store):
    rid = store.log_routing(agent="orch", routed_to="trainer")
    store.update_routing_outcome(rid, "success")
    rows = store.query_routing(agent="orch")
    assert rows[0]["outcome"] == "success"


def test_query_routing_filter_by_routed_to(store):
    store.log_routing(agent="orch", routed_to="critic")
    store.log_routing(agent="orch", routed_to="trainer")
    rows = store.query_routing(routed_to="critic")
    assert all(r["routed_to"] == "critic" for r in rows)


# ---------------------------------------------------------------------------
# Layer 3 — Corrections
# ---------------------------------------------------------------------------

def test_log_correction_and_get_training_pairs(store):
    cid = store.log_correction(agent="critic", bad_output="wrong", good_output="right")
    assert isinstance(cid, str)
    pairs = store.get_training_pairs(agent="critic")
    assert len(pairs) == 1
    assert pairs[0]["bad_output"] == "wrong"
    assert pairs[0]["good_output"] == "right"
    assert pairs[0]["used_for_training"] == 0


def test_mark_training_used(store):
    cid = store.log_correction(agent="a", bad_output="b", good_output="g")
    store.mark_training_used([cid])
    pairs = store.get_training_pairs(agent="a")
    assert len(pairs) == 0  # marked as used, excluded


def test_correction_source_default(store):
    store.log_correction(agent="a", bad_output="b", good_output="g")
    pairs = store.get_training_pairs()
    assert pairs[0]["correction_source"] == "user"


# ---------------------------------------------------------------------------
# Layer 4 — Hallucinations
# ---------------------------------------------------------------------------

def test_log_and_query_hallucination(store):
    hid = store.log_hallucination(
        agent="critic", claim="The sky is green", evidence_against="Observable fact"
    )
    assert isinstance(hid, str)
    rows = store.query_hallucinations(agent="critic")
    assert len(rows) == 1
    assert rows[0]["claim"] == "The sky is green"
    assert rows[0]["severity"] == "medium"


def test_hallucination_severity_filter(store):
    store.log_hallucination(agent="a", claim="c1", severity="high")
    store.log_hallucination(agent="a", claim="c2", severity="low")
    high = store.query_hallucinations(agent="a", severity="high")
    assert len(high) == 1
    assert high[0]["severity"] == "high"


# ---------------------------------------------------------------------------
# Layer 6 — Prompt versions
# ---------------------------------------------------------------------------

def test_save_and_get_prompt_versions(store):
    v1 = store.save_prompt_version(agent="critic", prompt_text="You are a critic.")
    v2 = store.save_prompt_version(
        agent="critic", prompt_text="You are a strict critic.", change_reason="be stricter"
    )
    assert v1 == 1
    assert v2 == 2
    history = store.get_prompt_history("critic")
    assert len(history) == 2
    assert history[0]["version"] == 2  # DESC order


def test_get_current_prompt_returns_latest(store):
    store.save_prompt_version(agent="a", prompt_text="v1")
    store.save_prompt_version(agent="a", prompt_text="v2")
    current = store.get_current_prompt("a")
    assert current["prompt_text"] == "v2"
    assert current["version"] == 2


def test_get_current_prompt_none_when_no_versions(store):
    assert store.get_current_prompt("nonexistent") is None


def test_prompt_versions_are_per_agent(store):
    store.save_prompt_version(agent="critic", prompt_text="c1")
    store.save_prompt_version(agent="trainer", prompt_text="t1")
    assert store.get_current_prompt("critic")["version"] == 1
    assert store.get_current_prompt("trainer")["version"] == 1


# ---------------------------------------------------------------------------
# Agent skills
# ---------------------------------------------------------------------------

def test_update_and_get_skills(store):
    store.update_skill("critic", "accuracy_assessment", 0.8, "Based on 10 reviews")
    skills = store.get_skills("critic")
    assert len(skills) == 1
    assert skills[0]["skill_name"] == "accuracy_assessment"
    assert skills[0]["score"] == pytest.approx(0.8)


def test_update_skill_overwrites(store):
    store.update_skill("a", "coding", 0.4)
    store.update_skill("a", "coding", 0.9, "improved")
    skills = store.get_skills("a")
    assert len(skills) == 1
    assert skills[0]["score"] == pytest.approx(0.9)


def test_get_all_skills_groups_by_agent(store):
    store.update_skill("critic", "accuracy", 0.8)
    store.update_skill("trainer", "pattern_detection", 0.6)
    all_skills = store.get_all_skills()
    assert "critic" in all_skills
    assert "trainer" in all_skills


# ---------------------------------------------------------------------------
# Layer 7 — Meta-patterns
# ---------------------------------------------------------------------------

def test_log_meta_pattern(store):
    pid = store.log_meta_pattern("Agent tends to be verbose", source_layers=[1, 2], impact="medium")
    assert isinstance(pid, str)
    patterns = store.query_meta_patterns()
    assert len(patterns) == 1
    assert patterns[0]["pattern"] == "Agent tends to be verbose"
    assert patterns[0]["frequency"] == 1


def test_duplicate_meta_pattern_increments_frequency(store):
    p = "Repeated hallucination pattern"
    store.log_meta_pattern(p)
    store.log_meta_pattern(p)
    store.log_meta_pattern(p)
    patterns = store.query_meta_patterns()
    assert len(patterns) == 1
    assert patterns[0]["frequency"] == 3


def test_meta_pattern_impact_filter(store):
    store.log_meta_pattern("high impact thing", impact="high")
    store.log_meta_pattern("low impact thing", impact="low")
    high = store.query_meta_patterns(impact="high")
    assert len(high) == 1 and high[0]["impact"] == "high"


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_counts(store):
    store.log_interaction(agent="a", input_text="i", output_text="o")
    store.log_routing(agent="orch", routed_to="a")
    store.log_correction(agent="a", bad_output="b", good_output="g")
    store.log_hallucination(agent="a", claim="c")
    store.save_prompt_version(agent="a", prompt_text="p")
    store.update_skill("a", "s", 0.5)
    store.log_meta_pattern("pattern x")
    s = store.summary()
    assert s["interactions"] == 1
    assert s["routing_decisions"] == 1
    assert s["corrections"] == 1
    assert s["hallucinations"] == 1
    assert s["prompt_versions"] == 1
    assert s["agent_skills"] == 1
    assert s["meta_patterns"] == 1


def test_summary_zero_when_empty(store):
    s = store.summary()
    assert all(v == 0 for v in s.values())
