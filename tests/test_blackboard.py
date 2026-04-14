from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


@pytest.fixture
def bb(tmp_path):
    from jarvis.blackboard import SharedBlackboard
    return SharedBlackboard(db_path=str(tmp_path / "blackboard.db"))


def test_post_returns_id(bb):
    post_id = bb.post(agent="agent_a", topic="finance", content="test message")
    assert isinstance(post_id, str)
    assert len(post_id) == 36  # UUID format


def test_read_returns_post(bb):
    bb.post(agent="agent_a", topic="finance", content="hello world")
    results = bb.read()
    assert len(results) == 1
    assert results[0]["content"] == "hello world"
    assert results[0]["agent"] == "agent_a"
    assert results[0]["topic"] == "finance"


def test_read_topic_filter(bb):
    bb.post(agent="agent_a", topic="finance", content="finance post")
    bb.post(agent="agent_b", topic="weather", content="weather post")
    results = bb.read(topics=["finance"])
    assert len(results) == 1
    assert results[0]["topic"] == "finance"
    assert results[0]["content"] == "finance post"


def test_read_agent_filter(bb):
    bb.post(agent="agent_a", topic="finance", content="from agent_a")
    bb.post(agent="agent_b", topic="finance", content="from agent_b")
    results = bb.read(agents=["agent_a"])
    assert len(results) == 1
    assert results[0]["agent"] == "agent_a"


def test_read_since_filter(bb):
    bb.post(agent="agent_a", topic="finance", content="old post")
    midpoint = datetime.now(timezone.utc)
    bb.post(agent="agent_a", topic="finance", content="new post")
    results = bb.read(since=midpoint.isoformat())
    # Only the post after midpoint should be returned
    assert len(results) == 1
    assert results[0]["content"] == "new post"


def test_urgency_ordering(bb):
    bb.post(agent="agent_a", topic="finance", content="normal post", urgency="normal")
    bb.post(agent="agent_a", topic="finance", content="urgent post", urgency="urgent")
    results = bb.read()
    assert len(results) == 2
    assert results[0]["urgency"] == "urgent"
    assert results[1]["urgency"] == "normal"


def test_subscribe_and_get_subscriptions(bb):
    bb.subscribe("agent_a", ["topic1", "topic2"])
    subs = bb.get_subscriptions("agent_a")
    assert "topic1" in subs
    assert "topic2" in subs


def test_get_subscribers(bb):
    bb.subscribe("agent_a", ["shared_topic"])
    bb.subscribe("agent_b", ["shared_topic"])
    subscribers = bb.get_subscribers("shared_topic")
    assert "agent_a" in subscribers
    assert "agent_b" in subscribers


def test_expired_posts_not_returned(bb):
    # Post with ttl_days=-1 so it's already expired
    bb.post(agent="agent_a", topic="finance", content="expired post", ttl_days=-1)
    results = bb.read()
    assert len(results) == 0


def test_post_custom_ttl(bb):
    from datetime import datetime, timezone, timedelta
    post_id = bb.post(agent="agent_a", topic="finance", content="custom ttl", ttl_days=1)
    results = bb.read()
    assert len(results) == 1
    expires_at = results[0]["expires_at"]
    expires_dt = datetime.fromisoformat(expires_at)
    now = datetime.now(timezone.utc)
    # Should expire approximately 1 day from now (within 5 minutes tolerance)
    expected = now + timedelta(days=1)
    diff = abs((expires_dt - expected).total_seconds())
    assert diff < 300  # within 5 minutes
