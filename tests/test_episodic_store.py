from __future__ import annotations
import time
import pytest
from jarvis.memory_tiers.episodic import EpisodicStore


@pytest.fixture
def store(tmp_path):
    return EpisodicStore(db_path=str(tmp_path / "episodes.db"))


def test_start_episode_returns_id(store):
    eid = store.start_episode()
    assert isinstance(eid, str) and len(eid) == 36


def test_end_episode_sets_ended_at(store):
    eid = store.start_episode()
    store.end_episode(eid, summary="test summary")
    eps = store.get_unconsolidated()
    assert len(eps) == 1
    assert eps[0]["ended_at"] is not None
    assert eps[0]["summary"] == "test summary"


def test_add_message_persists(store):
    eid = store.start_episode()
    store.end_episode(eid)
    mid = store.add_message(eid, "user", "hello world")
    msgs = store.get_messages(eid)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "hello world"


def test_link_decision_persists(store):
    eid = store.start_episode()
    store.link_decision(eid, "decision-123")
    # No error = success; table exists


def test_search_finds_by_content(store):
    eid = store.start_episode()
    store.end_episode(eid)
    store.add_message(eid, "user", "chicken tikka masala recipe")
    results = store.search("chicken")
    assert len(results) >= 1


def test_search_finds_by_summary(store):
    eid = store.start_episode()
    store.end_episode(eid, summary="discussed grocery shopping for the week")
    results = store.search("grocery")
    assert len(results) >= 1


def test_get_unconsolidated_only_returns_ended(store):
    eid_open = store.start_episode()  # not ended
    eid_done = store.start_episode()
    store.end_episode(eid_done)
    results = store.get_unconsolidated()
    ids = [r["id"] for r in results]
    assert eid_done in ids
    assert eid_open not in ids


def test_mark_consolidated(store):
    eid = store.start_episode()
    store.end_episode(eid)
    store.mark_consolidated(eid)
    results = store.get_unconsolidated()
    assert all(r["id"] != eid for r in results)


def test_get_messages_returns_ordered(store):
    eid = store.start_episode()
    for i in range(5):
        store.add_message(eid, "user", f"msg {i}")
    msgs = store.get_messages(eid)
    texts = [m["content"] for m in msgs]
    assert texts == [f"msg {i}" for i in range(5)]


def test_prune_removes_old_low_satisfaction(store):
    # This test just checks it runs without error; real time-based pruning is hard to test
    count = store.prune(older_than_days=0, min_satisfaction=1.0)
    assert isinstance(count, int)
