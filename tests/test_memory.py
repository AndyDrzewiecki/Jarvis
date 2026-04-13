"""Tests for jarvis/memory.py — SQLite-backed conversation memory."""
from __future__ import annotations
import threading
import pytest


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """Redirect MEMORY_PATH to a temp dir for each test."""
    import jarvis.memory as mem
    monkeypatch.setattr(mem, "MEMORY_PATH", str(tmp_path / "test_memory.db"))
    mem.clear()


def test_add_returns_uuid():
    import jarvis.memory as mem
    entry_id = mem.add("user", "hello")
    assert isinstance(entry_id, str)
    assert len(entry_id) == 36  # UUID format
    assert "-" in entry_id


def test_recent_returns_last_n_chronological():
    import jarvis.memory as mem
    mem.add("user", "first")
    mem.add("assistant", "second")
    mem.add("user", "third")
    results = mem.recent(2)
    assert len(results) == 2
    assert results[0]["text"] == "second"
    assert results[1]["text"] == "third"


def test_recent_empty_returns_empty_list():
    import jarvis.memory as mem
    assert mem.recent(10) == []


def test_all_messages_returns_all_chronological():
    import jarvis.memory as mem
    mem.add("user", "a")
    mem.add("assistant", "b")
    mem.add("user", "c")
    all_msgs = mem.all_messages()
    assert len(all_msgs) == 3
    texts = [m["text"] for m in all_msgs]
    assert texts == ["a", "b", "c"]


def test_clear_removes_all():
    import jarvis.memory as mem
    mem.add("user", "hello")
    mem.add("assistant", "hi")
    mem.clear()
    assert mem.all_messages() == []


def test_max_messages_enforced(monkeypatch):
    import jarvis.memory as mem
    monkeypatch.setattr(mem, "MAX_MESSAGES", 100)
    for i in range(110):
        mem.add("user", f"msg {i}")
    all_msgs = mem.all_messages()
    assert len(all_msgs) == 100
    # Should keep the newest 100 (msg 10 through msg 109)
    assert all_msgs[-1]["text"] == "msg 109"


def test_add_with_adapter_field():
    import jarvis.memory as mem
    entry_id = mem.add("assistant", "meal plan ready", adapter="grocery")
    msgs = mem.all_messages()
    assert len(msgs) == 1
    assert msgs[0]["adapter"] == "grocery"
    assert msgs[0]["id"] == entry_id


def test_concurrent_writes_safe(tmp_path, monkeypatch):
    import jarvis.memory as mem
    monkeypatch.setattr(mem, "MEMORY_PATH", str(tmp_path / "concurrent.db"))
    errors = []

    def writer(n):
        try:
            for i in range(10):
                mem.add("user", f"thread {n} msg {i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"Concurrent write errors: {errors}"
    all_msgs = mem.all_messages()
    assert len(all_msgs) == 50


def test_tmp_path_isolation(tmp_path, monkeypatch):
    import jarvis.memory as mem
    db1 = str(tmp_path / "db1.db")
    db2 = str(tmp_path / "db2.db")

    monkeypatch.setattr(mem, "MEMORY_PATH", db1)
    mem.add("user", "from db1")

    monkeypatch.setattr(mem, "MEMORY_PATH", db2)
    mem.add("user", "from db2")

    # db2 should only have its own message
    assert len(mem.all_messages()) == 1
    assert mem.all_messages()[0]["text"] == "from db2"

    # Switch back to db1
    monkeypatch.setattr(mem, "MEMORY_PATH", db1)
    assert len(mem.all_messages()) == 1
    assert mem.all_messages()[0]["text"] == "from db1"
