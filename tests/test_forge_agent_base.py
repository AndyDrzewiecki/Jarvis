"""Tests for jarvis.forge.agent_base — BaseDevAgent contract."""
from __future__ import annotations
import pytest
from jarvis.forge.agent_base import BaseDevAgent, TaskResult


# ---------------------------------------------------------------------------
# Concrete test agent (minimal subclass)
# ---------------------------------------------------------------------------

class EchoAgent(BaseDevAgent):
    name = "echo"
    model = "test-model"

    def execute_task(self, task: dict) -> TaskResult:
        payload = task.get("payload", {})
        text = payload.get("text", "")
        if payload.get("fail"):
            raise ValueError("deliberate failure")
        return TaskResult(
            task_id=task["id"],
            agent=self.name,
            status="success",
            output=f"echo:{text}",
            confidence=0.9,
            metadata={"input": text},
        )


@pytest.fixture()
def store(tmp_path):
    from jarvis.forge.memory_store import ForgeMemoryStore, _inited
    db = str(tmp_path / "agent_test.db")
    _inited.discard(db)
    return ForgeMemoryStore(db_path=db)


@pytest.fixture()
def agent(store):
    return EchoAgent(memory_store=store)


# ---------------------------------------------------------------------------
# execute_task
# ---------------------------------------------------------------------------

def test_execute_task_returns_task_result(agent):
    task = {"id": "t1", "type": "echo", "payload": {"text": "hello"}}
    result = agent.execute_task(task)
    assert isinstance(result, TaskResult)
    assert result.output == "echo:hello"
    assert result.status == "success"


# ---------------------------------------------------------------------------
# run — full lifecycle
# ---------------------------------------------------------------------------

def test_run_assigns_task_id(agent):
    result = agent.run({"type": "echo", "payload": {"text": "hi"}})
    assert isinstance(result.task_id, str) and len(result.task_id) > 0


def test_run_records_duration(agent):
    result = agent.run({"type": "echo", "payload": {"text": "hi"}})
    assert result.duration_ms >= 0


def test_run_writes_to_memory(agent, store):
    agent.run({"type": "echo", "payload": {"text": "mem-test"}})
    rows = store.query_interactions(agent="echo")
    assert len(rows) == 1
    assert "echo:mem-test" in rows[0]["output_text"]


def test_run_catches_exceptions_and_returns_failure(agent):
    result = agent.run({"type": "echo", "payload": {"fail": True}})
    assert result.status == "failure"
    assert result.error is not None
    assert "deliberate failure" in result.error


def test_run_failure_still_writes_memory(agent, store):
    agent.run({"type": "echo", "payload": {"fail": True}})
    rows = store.query_interactions(agent="echo")
    # write_memory is called even on failure
    assert len(rows) == 1


def test_run_updates_stats(agent):
    agent.run({"type": "echo", "payload": {"text": "a"}})
    agent.run({"type": "echo", "payload": {"fail": True}})
    status = agent.report_status()
    assert status.tasks_completed == 1
    assert status.tasks_failed == 1


# ---------------------------------------------------------------------------
# read_memory
# ---------------------------------------------------------------------------

def test_read_memory_returns_dict_with_keys(agent):
    ctx = agent.read_memory()
    assert "recent_interactions" in ctx
    assert "skills" in ctx
    assert "routing_history" in ctx


def test_read_memory_returns_lists(agent):
    ctx = agent.read_memory()
    assert isinstance(ctx["recent_interactions"], list)
    assert isinstance(ctx["skills"], list)


# ---------------------------------------------------------------------------
# report_status
# ---------------------------------------------------------------------------

def test_report_status_initial(agent):
    status = agent.report_status()
    assert status.agent == "echo"
    assert status.model == "test-model"
    assert status.tasks_completed == 0
    assert status.tasks_failed == 0
    assert status.avg_confidence == pytest.approx(0.0)
    assert isinstance(status.top_skills, list)


def test_report_status_after_tasks(agent):
    agent.run({"type": "echo", "payload": {"text": "x"}})
    agent.run({"type": "echo", "payload": {"text": "y"}})
    status = agent.report_status()
    assert status.tasks_completed == 2
    assert status.avg_confidence > 0


# ---------------------------------------------------------------------------
# update_skill
# ---------------------------------------------------------------------------

def test_update_skill_persists(agent, store):
    agent.update_skill("accuracy", 0.75, "test evidence")
    skills = store.get_skills("echo")
    assert any(s["skill_name"] == "accuracy" for s in skills)
    assert next(s for s in skills if s["skill_name"] == "accuracy")["score"] == pytest.approx(0.75)
