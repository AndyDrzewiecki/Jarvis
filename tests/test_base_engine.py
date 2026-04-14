"""TDD RED — tests/test_base_engine.py
Tests for BaseKnowledgeEngine.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


class _ConcreteEngine:
    """Minimal concrete engine for testing."""
    name = "test_engine"
    domain = "test"
    schedule = "0 */4 * * *"
    engine_type = "knowledge"

    def __init__(self):
        self._ingestion = None
        self._engine_store = None
        self._lake = None
        self._bus = None
        from jarvis import config
        self.model = config.FALLBACK_MODEL

    gather = None   # will be set per test
    prepare_items = None
    improve = None

    def run_cycle(self):
        from jarvis.engines.base_engine import BaseKnowledgeEngine
        return BaseKnowledgeEngine.run_cycle(self)

    @property
    def ingestion(self):
        if self._ingestion is None:
            from jarvis.ingestion import IngestionBuffer
            self._ingestion = IngestionBuffer()
        return self._ingestion

    @property
    def engine_store(self):
        if self._engine_store is None:
            from jarvis.engine_store import EngineStore
            self._engine_store = EngineStore()
        return self._engine_store

    @property
    def lake(self):
        if self._lake is None:
            from jarvis.knowledge_lake import KnowledgeLake
            self._lake = KnowledgeLake()
        return self._lake

    @property
    def bus(self):
        if self._bus is None:
            from jarvis.memory_bus import get_bus
            self._bus = get_bus()
        return self._bus


def _make_engine():
    from jarvis.engines.base_engine import BaseKnowledgeEngine

    class ConcreteEngine(BaseKnowledgeEngine):
        name = "test_engine"
        domain = "test"
        schedule = "0 */4 * * *"

        def gather(self):
            return []

        def prepare_items(self, raw_data):
            return []

        def improve(self):
            return []

    return ConcreteEngine()


# 1. run_cycle calls gather
def test_run_cycle_calls_gather(tmp_path):
    eng = _make_engine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        eng.run_cycle()

    eng.gather.assert_called_once()


# 2. run_cycle calls prepare_items with gather output
def test_run_cycle_calls_prepare_items(tmp_path):
    eng = _make_engine()
    raw = [{"type": "test", "data": "value"}]
    eng.gather = MagicMock(return_value=raw)
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        eng.run_cycle()

    eng.prepare_items.assert_called_once_with(raw)


# 3. run_cycle calls ingestion.ingest when prepare_items returns items
def test_run_cycle_calls_ingest(tmp_path):
    from jarvis.ingestion import RawItem
    eng = _make_engine()
    items = [RawItem(content="test content here", source="test")]
    eng.gather = MagicMock(return_value=[{"d": 1}])
    eng.prepare_items = MagicMock(return_value=items)
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=1)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        eng.run_cycle()

    mock_ingest.ingest.assert_called_once()


# 4. ingestion returns report with accepted=2 → CycleReport.insights==2
def test_run_cycle_report_counts(tmp_path):
    from jarvis.ingestion import RawItem
    eng = _make_engine()
    items = [RawItem(content="content", source="test")]
    eng.gather = MagicMock(return_value=[{"d": 1}])
    eng.prepare_items = MagicMock(return_value=items)
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=2)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    assert report.insights == 2


# 5. gather raises → report.error set, no crash
def test_run_cycle_error_sets_report_error(tmp_path):
    eng = _make_engine()
    eng.gather = MagicMock(side_effect=RuntimeError("gather blew up"))
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    assert report.error is not None
    assert "gather blew up" in report.error


# 6. ingestion property lazy-creates IngestionBuffer
def test_ingestion_property_lazy(tmp_path):
    eng = _make_engine()
    assert eng._ingestion is None
    buf = eng.ingestion
    from jarvis.ingestion import IngestionBuffer
    assert isinstance(buf, IngestionBuffer)
    # Second access returns same instance
    assert eng.ingestion is buf


# 7. engine_store property lazy-creates EngineStore
def test_engine_store_property_lazy(tmp_path):
    eng = _make_engine()
    assert eng._engine_store is None
    store = eng.engine_store
    from jarvis.engine_store import EngineStore
    assert isinstance(store, EngineStore)
    # Second access returns same instance
    assert eng.engine_store is store
