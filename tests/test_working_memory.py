from __future__ import annotations
import threading
import pytest
from jarvis.memory_tiers.working import WorkingMemory


def test_add_returns_id():
    wm = WorkingMemory()
    mid = wm.add("user", "hello")
    assert isinstance(mid, str) and len(mid) == 36


def test_recent_returns_last_n():
    wm = WorkingMemory()
    for i in range(5):
        wm.add("user", f"msg {i}")
    msgs = wm.recent(3)
    assert len(msgs) == 3
    assert msgs[-1]["text"] == "msg 4"


def test_max_messages_enforced():
    wm = WorkingMemory()
    for i in range(25):
        wm.add("user", f"msg {i}")
    assert len(wm.recent(100)) == 20


def test_search_finds_matches():
    wm = WorkingMemory()
    wm.add("user", "what is the weather today")
    wm.add("user", "buy milk and eggs")
    results = wm.search("weather")
    assert len(results) == 1
    assert "weather" in results[0]["text"]


def test_search_no_match_returns_empty():
    wm = WorkingMemory()
    wm.add("user", "hello world")
    assert wm.search("zxqkjfh") == []


def test_clear_empties_messages():
    wm = WorkingMemory()
    wm.add("user", "test")
    wm.clear()
    assert wm.recent() == []


def test_thread_safe_add():
    wm = WorkingMemory()
    results = []
    def worker():
        for i in range(5):
            results.append(wm.add("user", f"t{i}"))
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert len(results) == 50
    assert len(wm.recent(100)) <= 20


def test_episode_id_default_none():
    wm = WorkingMemory()
    assert wm.current_episode_id is None


def test_episode_id_set_and_get():
    wm = WorkingMemory()
    wm.current_episode_id = "episode-abc"
    assert wm.current_episode_id == "episode-abc"
