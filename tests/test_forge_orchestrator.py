"""Tests for jarvis.forge.orchestrator — ForgeOrchestrator."""
from __future__ import annotations
import pytest
from jarvis.forge.agent_base import BaseDevAgent, TaskResult


# ---------------------------------------------------------------------------
# Minimal test agents
# ---------------------------------------------------------------------------

class OkAgent(BaseDevAgent):
    name = "ok_agent"
    model = "test"

    def execute_task(self, task: dict) -> TaskResult:
        return TaskResult(
            task_id=task["id"], agent=self.name, status="success",
            output="done", confidence=0.9
        )


class FailAgent(BaseDevAgent):
    name = "fail_agent"
    model = "test"

    def execute_task(self, task: dict) -> TaskResult:
        return TaskResult(
            task_id=task["id"], agent=self.name, status="failure",
            output="", error="always fails"
        )


class CrashAgent(BaseDevAgent):
    name = "crash_agent"
    model = "test"

    def execute_task(self, task: dict) -> TaskResult:
        raise RuntimeError("agent crashed")


@pytest.fixture()
def store(tmp_path):
    from jarvis.forge.memory_store import ForgeMemoryStore, _inited
    db = str(tmp_path / "orch_test.db")
    _inited.discard(db)
    return ForgeMemoryStore(db_path=db)


@pytest.fixture()
def orch(store):
    from jarvis.forge.orchestrator import ForgeOrchestrator
    o = ForgeOrchestrator(memory_store=store)
    o.register(OkAgent(memory_store=store))
    o.register(FailAgent(memory_store=store))
    o.register(CrashAgent(memory_store=store))
    return o


# ---------------------------------------------------------------------------
# register / unregister
# ---------------------------------------------------------------------------

def test_register_agent(orch):
    assert "ok_agent" in orch.registered_agents()
    assert "fail_agent" in orch.registered_agents()


def test_unregister_agent(orch):
    orch.unregister("ok_agent")
    assert "ok_agent" not in orch.registered_agents()


# ---------------------------------------------------------------------------
# dispatch — success
# ---------------------------------------------------------------------------

def test_dispatch_success(orch):
    result = orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    assert result.status == "success"
    assert result.output == "done"


def test_dispatch_assigns_task_id_if_missing(orch):
    result = orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    assert isinstance(result.task_id, str) and len(result.task_id) > 0


def test_dispatch_uses_provided_task_id(orch):
    result = orch.dispatch({"id": "my-id", "type": "run", "target": "ok_agent", "payload": {}})
    assert result.task_id == "my-id"


# ---------------------------------------------------------------------------
# dispatch — failure cases
# ---------------------------------------------------------------------------

def test_dispatch_unregistered_agent_returns_failure(orch):
    result = orch.dispatch({"type": "run", "target": "ghost", "payload": {}})
    assert result.status == "failure"
    assert "ghost" in (result.error or "")


def test_dispatch_fail_agent(orch):
    result = orch.dispatch({"type": "run", "target": "fail_agent", "payload": {}})
    assert result.status == "failure"


def test_dispatch_crashing_agent_returns_failure_not_exception(orch):
    result = orch.dispatch({"type": "run", "target": "crash_agent", "payload": {}})
    assert result.status == "failure"
    assert result.error is not None


# ---------------------------------------------------------------------------
# Routing written to memory
# ---------------------------------------------------------------------------

def test_dispatch_writes_routing_to_store(orch, store):
    orch.dispatch({"type": "evaluate", "target": "ok_agent", "payload": {}})
    rows = store.query_routing(agent="orchestrator")
    assert len(rows) >= 1
    assert rows[0]["routed_to"] == "ok_agent"


def test_dispatch_updates_routing_outcome_on_success(orch, store):
    orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    rows = store.query_routing(routed_to="ok_agent")
    assert rows[0]["outcome"] == "success"


def test_dispatch_updates_routing_outcome_on_failure(orch, store):
    orch.dispatch({"type": "run", "target": "fail_agent", "payload": {}})
    rows = store.query_routing(routed_to="fail_agent")
    assert rows[0]["outcome"] == "failure"


# ---------------------------------------------------------------------------
# dispatch_many
# ---------------------------------------------------------------------------

def test_dispatch_many_returns_all_results(orch):
    tasks = [
        {"type": "run", "target": "ok_agent", "payload": {}},
        {"type": "run", "target": "ok_agent", "payload": {}},
    ]
    results = orch.dispatch_many(tasks)
    assert len(results) == 2
    assert all(r.status == "success" for r in results)


def test_dispatch_many_independent_tasks_all_complete(orch):
    tasks = [
        {"type": "run", "target": "ok_agent", "payload": {}},
        {"type": "run", "target": "fail_agent", "payload": {}},
    ]
    results = orch.dispatch_many(tasks)
    statuses = {r.agent: r.status for r in results}
    assert statuses["ok_agent"] == "success"
    assert statuses["fail_agent"] == "failure"


# ---------------------------------------------------------------------------
# track_progress
# ---------------------------------------------------------------------------

def test_track_progress_initial(orch):
    progress = orch.track_progress()
    assert progress["dispatched"] == 0
    assert progress["succeeded"] == 0
    assert progress["failed"] == 0
    assert progress["active"] == 0


def test_track_progress_after_dispatches(orch):
    orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    orch.dispatch({"type": "run", "target": "fail_agent", "payload": {}})
    p = orch.track_progress()
    assert p["dispatched"] == 2
    assert p["succeeded"] == 1
    assert p["failed"] == 1


# ---------------------------------------------------------------------------
# check_results
# ---------------------------------------------------------------------------

def test_check_results_empty_initially(orch):
    assert orch.check_results() == []


def test_check_results_after_dispatch(orch):
    orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    results = orch.check_results()
    assert len(results) == 1
    assert results[0].status == "success"


def test_check_results_filter_by_agent(orch):
    orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    orch.dispatch({"type": "run", "target": "fail_agent", "payload": {}})
    ok_results = orch.check_results(agent="ok_agent")
    assert all(r.agent == "ok_agent" for r in ok_results)


def test_check_results_filter_by_status(orch):
    orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    orch.dispatch({"type": "run", "target": "fail_agent", "payload": {}})
    successes = orch.check_results(status="success")
    assert all(r.status == "success" for r in successes)


# ---------------------------------------------------------------------------
# report_status
# ---------------------------------------------------------------------------

def test_report_status(orch):
    orch.dispatch({"type": "run", "target": "ok_agent", "payload": {}})
    s = orch.report_status()
    assert s.agents_registered == 3
    assert s.tasks_dispatched == 1
    assert s.tasks_succeeded == 1
    assert s.tasks_failed == 0
    assert s.active_task_ids == []
