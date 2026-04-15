"""Tests for jarvis.forge.trainer — AgentTrainer."""
from __future__ import annotations
import pytest
from unittest.mock import patch


@pytest.fixture()
def store(tmp_path):
    from jarvis.forge.memory_store import ForgeMemoryStore, _inited
    db = str(tmp_path / "trainer_test.db")
    _inited.discard(db)
    return ForgeMemoryStore(db_path=db)


@pytest.fixture()
def trainer(store):
    from jarvis.forge.trainer import AgentTrainer
    return AgentTrainer(memory_store=store)


def _populate(store, agent, n_good=5, n_poor=0):
    """Add n_good long outputs and n_poor short (or hallucinated) outputs."""
    interaction_ids = []
    for i in range(n_good):
        iid = store.log_interaction(
            agent=agent,
            input_text=f"task_{i}",
            output_text="This is a good, detailed, accurate output for the task." * 3,
        )
        interaction_ids.append(iid)
    for i in range(n_poor):
        iid = store.log_interaction(
            agent=agent,
            input_text=f"bad_task_{i}",
            output_text="bad",  # short = heuristic poor
        )
        interaction_ids.append(iid)
    return interaction_ids


# ---------------------------------------------------------------------------
# review — not enough interactions
# ---------------------------------------------------------------------------

def test_review_too_few_interactions_returns_early(trainer):
    report = trainer.review("phantom_agent", min_interactions=5)
    assert report.interactions_reviewed == 0
    assert report.new_prompt_version is None


def test_review_just_enough_interactions(trainer, store):
    _populate(store, "critic", n_good=5)
    report = trainer.review("critic", min_interactions=5)
    assert report.interactions_reviewed == 5


# ---------------------------------------------------------------------------
# review — quality bucketing
# ---------------------------------------------------------------------------

def test_review_counts_good_poor(trainer, store):
    _populate(store, "tester", n_good=7, n_poor=3)
    report = trainer.review("tester", min_interactions=5)
    # 7 good (long output), 3 poor (short output)
    assert report.good_count == 7
    assert report.poor_count == 3
    assert report.interactions_reviewed == 10


def test_review_all_good_no_prompt_update(trainer, store):
    """If < 30% poor, no prompt rewrite."""
    _populate(store, "clean_agent", n_good=10, n_poor=0)
    with patch.object(trainer, "_generate_improved_prompt") as mock_gen:
        report = trainer.review("clean_agent", min_interactions=5)
    mock_gen.assert_not_called()
    assert report.new_prompt_version is None


def test_review_many_poor_triggers_prompt_rewrite(trainer, store):
    """≥ 30% poor → rewrite prompt."""
    _populate(store, "bad_agent", n_good=3, n_poor=7)
    with patch.object(trainer, "_call_llm", return_value="You are an improved agent."):
        report = trainer.review("bad_agent", min_interactions=5)
    assert report.new_prompt_version is not None
    assert report.new_prompt_version == 1


def test_review_prompt_not_rewritten_if_unchanged(trainer, store):
    """Don't write a duplicate prompt if text is identical."""
    _populate(store, "dup_agent", n_good=2, n_poor=8)
    prompt_text = "Improved prompt text."
    with patch.object(trainer, "_call_llm", return_value=prompt_text):
        r1 = trainer.review("dup_agent", min_interactions=5)
        r2 = trainer.review("dup_agent", min_interactions=5)
    # Second review: same prompt text → no new version
    assert r1.new_prompt_version == 1
    assert r2.new_prompt_version is None


# ---------------------------------------------------------------------------
# review — skill updates
# ---------------------------------------------------------------------------

def test_review_updates_output_quality_skill(trainer, store):
    _populate(store, "skilled_agent", n_good=8, n_poor=2)
    report = trainer.review("skilled_agent", min_interactions=5)
    assert "output_quality" in report.skills_updated
    skills = store.get_skills("skilled_agent")
    quality_skill = next(s for s in skills if s["skill_name"] == "output_quality")
    assert quality_skill["score"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# review — hallucinations affect bucketing
# ---------------------------------------------------------------------------

def test_hallucinations_push_to_poor_bucket(trainer, store):
    ids = _populate(store, "halluc_agent", n_good=5)
    # Mark 3 of the good interactions as hallucinations
    for iid in ids[:3]:
        store.log_hallucination(agent="halluc_agent", claim="false claim", interaction_id=iid)
    report = trainer.review("halluc_agent", min_interactions=5)
    assert report.poor_count >= 3
    assert report.good_count <= 2


# ---------------------------------------------------------------------------
# review_all
# ---------------------------------------------------------------------------

def test_review_all_runs_for_all_agents(trainer, store):
    _populate(store, "agent_a", n_good=6)
    _populate(store, "agent_b", n_good=6)
    reports = trainer.review_all(min_interactions=5)
    agent_names = {r.agent for r in reports}
    assert "agent_a" in agent_names
    assert "agent_b" in agent_names


# ---------------------------------------------------------------------------
# Training pair export
# ---------------------------------------------------------------------------

def test_export_training_pairs_sharegpt(trainer, store):
    store.log_correction(agent="a", bad_output="bad", good_output="good")
    store.log_correction(agent="a", bad_output="wrong", good_output="right")
    pairs = trainer.export_training_pairs(agent="a", format="sharegpt")
    assert len(pairs) == 2
    assert "conversations" in pairs[0]
    assert pairs[0]["conversations"][0]["from"] == "human"
    assert pairs[0]["conversations"][1]["from"] == "gpt"


def test_export_training_pairs_dpo(trainer, store):
    store.log_correction(agent="b", bad_output="b", good_output="g")
    pairs = trainer.export_training_pairs(agent="b", format="dpo")
    assert len(pairs) == 1
    assert "prompt" in pairs[0]
    assert "chosen" in pairs[0]
    assert "rejected" in pairs[0]
    assert pairs[0]["chosen"] == "g"


def test_export_training_pairs_empty(trainer):
    pairs = trainer.export_training_pairs(agent="no_corrections")
    assert pairs == []


def test_mark_pairs_exported(trainer, store):
    store.log_correction(agent="x", bad_output="b", good_output="g")
    count = trainer.mark_pairs_exported(agent="x")
    assert count == 1
    assert trainer.export_training_pairs(agent="x") == []


# ---------------------------------------------------------------------------
# write_skill
# ---------------------------------------------------------------------------

def test_write_skill_directly(trainer, store):
    trainer.write_skill("critic", "hallucination_detection", 0.92, "50 evals, 4 misses")
    skills = store.get_skills("critic")
    assert any(s["skill_name"] == "hallucination_detection" for s in skills)


# ---------------------------------------------------------------------------
# _detect_pattern (LLM mocked)
# ---------------------------------------------------------------------------

def test_detect_pattern_extracts_pattern_line(trainer, store):
    interactions = [
        {"output_text": "short", "id": "x1"},
        {"output_text": "also short", "id": "x2"},
    ]
    with patch.object(trainer, "_call_llm", return_value=(
        "PATTERN: Agent outputs are too brief\nFIX: Add detail instructions"
    )):
        pattern = trainer._detect_pattern("agent", interactions)
    assert pattern == "Agent outputs are too brief"


def test_detect_pattern_none_on_empty_interactions(trainer):
    pattern = trainer._detect_pattern("agent", [])
    assert pattern is None


def test_detect_pattern_llm_error_returns_none(trainer):
    with patch.object(trainer, "_call_llm", side_effect=Exception("LLM down")):
        pattern = trainer._detect_pattern("a", [{"output_text": "x", "id": "1"}])
    assert pattern is None
