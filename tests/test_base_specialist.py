from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from jarvis.specialists.base import BaseSpecialist, Insight, CycleReport


class _GoodSpec(BaseSpecialist):
    name = "test_good"
    domain = "test"
    schedule = "0 * * * *"
    def gather(self): return [{"item": "milk"}, {"item": "eggs"}]
    def analyze(self, raw, ctx): return [Insight("note", "milk is low", 0.9)]
    def improve(self): return ["check prices more often"]


class _FailGatherSpec(BaseSpecialist):
    name = "test_fail_gather"
    domain = "test"
    schedule = "0 * * * *"
    def gather(self): raise RuntimeError("network error")
    def analyze(self, raw, ctx): return []
    def improve(self): return []


class _FailAnalyzeSpec(BaseSpecialist):
    name = "test_fail_analyze"
    domain = "test"
    schedule = "0 * * * *"
    def gather(self): return [{"x": 1}]
    def analyze(self, raw, ctx): raise ValueError("bad data")
    def improve(self): return []


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))


@pytest.fixture
def mock_lake():
    lake = MagicMock()
    lake.recent_by_domain.return_value = {}
    lake.store_fact.return_value = "fact-id-123"
    lake.query_facts.return_value = []
    return lake


def test_run_cycle_success(mock_lake):
    spec = _GoodSpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    report = spec.run_cycle()
    assert report.gathered == 2
    assert report.insights == 1
    assert report.gaps_identified == 1
    assert report.error is None
    assert report.ended_at != ""


def test_run_cycle_stores_insights_to_lake(mock_lake):
    spec = _GoodSpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    spec.run_cycle()
    mock_lake.store_fact.assert_called_once()
    call_kwargs = mock_lake.store_fact.call_args.kwargs
    assert call_kwargs["domain"] == "test"
    assert call_kwargs["fact_type"] == "note"
    assert call_kwargs["source_agent"] == "test_good"


def test_run_cycle_gather_error_captured(mock_lake):
    spec = _FailGatherSpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    report = spec.run_cycle()
    assert report.error is not None
    assert "network error" in report.error
    assert report.gathered == 0


def test_run_cycle_analyze_error_captured(mock_lake):
    spec = _FailAnalyzeSpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    report = spec.run_cycle()
    assert report.error is not None
    assert report.insights == 0


def test_run_cycle_logs_to_agent_memory(mock_lake, tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "d2.db"))
    am._inited.discard(str(tmp_path / "d2.db"))
    spec = _GoodSpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    spec.run_cycle()
    decisions = am.query(agent="test_good")
    assert len(decisions) == 1
    assert decisions[0]["capability"] == "run_cycle"


def test_bus_is_lazy():
    spec = _GoodSpec()
    assert spec._bus is None
    with patch("jarvis.memory_bus.get_bus") as mock_get:
        mock_get.return_value = MagicMock()
        _ = spec.bus
        mock_get.assert_called_once()


def test_lake_is_lazy():
    spec = _GoodSpec()
    assert spec._lake is None
    with patch("jarvis.knowledge_lake.KnowledgeLake") as mock_cls:
        mock_cls.return_value = MagicMock()
        _ = spec.lake
        mock_cls.assert_called_once()


def test_model_defaults_to_fallback_model():
    spec = _GoodSpec()
    from jarvis import config
    assert spec.model == config.FALLBACK_MODEL


def test_cycle_report_has_timestamps(mock_lake):
    spec = _GoodSpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    report = spec.run_cycle()
    assert report.started_at != ""
    assert report.ended_at != ""
    assert report.ended_at >= report.started_at
