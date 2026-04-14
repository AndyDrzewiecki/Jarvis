"""TDD RED — tests/test_ingestion.py
Tests for IngestionBuffer and RawItem/IngestionReport dataclasses.
"""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


def _make_raw_item(**kwargs):
    from jarvis.ingestion import RawItem
    defaults = dict(
        content="This is a sample economic indicator content text",
        source="fred",
        fact_type="knowledge",
        domain="financial",
        quality_hint=0.5,
    )
    defaults.update(kwargs)
    return RawItem(**defaults)


# 1. ingest returns an IngestionReport with total == len(items)
def test_ingest_returns_report(tmp_path):
    from jarvis.ingestion import IngestionBuffer, RawItem, IngestionReport

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.return_value = "fact-id-1"
    buf._lake = mock_lake

    mock_store = MagicMock()
    buf._db_manager = mock_store

    items = [_make_raw_item() for _ in range(3)]
    report = buf.ingest("test_engine", items)

    assert isinstance(report, IngestionReport)
    assert report.total == 3
    assert report.engine == "test_engine"


# 2. no duplicates, quality > 0.2 → accepted == total
def test_ingest_accepted_count(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.return_value = "fact-id"
    buf._lake = mock_lake
    buf._db_manager = MagicMock()

    items = [_make_raw_item(quality_hint=0.5) for _ in range(3)]
    report = buf.ingest("engine", items)

    assert report.accepted == 3
    assert report.duplicates == 0
    assert report.rejected == 0


# 3. _is_duplicate returns True for 1 item → duplicates == 1
def test_ingest_skips_duplicates(tmp_path):
    from jarvis.ingestion import IngestionBuffer, RawItem

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    # First item: search returns match (duplicate)
    # Subsequent items: no match
    call_count = [0]
    def side_effect(query, n, domain):
        call_count[0] += 1
        if call_count[0] == 1:
            return [{"summary": query[:80]}]  # duplicate
        return []
    mock_lake.search.side_effect = side_effect
    mock_lake.store_fact.return_value = "fid"
    buf._lake = mock_lake
    buf._db_manager = MagicMock()

    items = [
        _make_raw_item(content="Duplicate content that already exists in the knowledge base"),
        _make_raw_item(content="Fresh unique content about something entirely different here"),
        _make_raw_item(content="Another fresh unique content about something else entirely"),
    ]
    report = buf.ingest("engine", items)

    assert report.duplicates == 1
    assert report.accepted == 2


# 4. item with quality_hint=0.1, no trusted source → rejected >= 1
def test_ingest_rejects_low_quality(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.return_value = "fid"
    buf._lake = mock_lake
    buf._db_manager = MagicMock()

    items = [
        _make_raw_item(quality_hint=0.1, source="unknown_unverified_source"),
    ]
    report = buf.ingest("engine", items)

    assert report.rejected >= 1


# 5. source="fred" → score >= item.quality_hint + 0.1
def test_score_quality_trusted_source(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    item = _make_raw_item(source="fred", quality_hint=0.5, content="A" * 50)
    score = buf._score_quality(item)
    assert score >= 0.5 + 0.1


# 6. content="hi" (< 20 chars) → score reduced
def test_score_quality_short_content(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    item = _make_raw_item(source="unknown", quality_hint=0.5, content="hi")
    score = buf._score_quality(item)
    assert score < 0.5


# 7. structured_data provided → score boosted
def test_score_quality_structured_data_boost(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    item_plain = _make_raw_item(quality_hint=0.5, content="A" * 50, structured_data=None)
    item_struct = _make_raw_item(quality_hint=0.5, content="A" * 50, structured_data={"key": "value"})

    score_plain = buf._score_quality(item_plain)
    score_struct = buf._score_quality(item_struct)
    assert score_struct > score_plain


# 8. item with structured_data → engine_store.store called
def test_ingest_structured_routes_to_engine_store(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.return_value = "fid"
    buf._lake = mock_lake

    mock_store = MagicMock()
    buf._db_manager = mock_store

    items = [
        _make_raw_item(
            content="A" * 50,
            quality_hint=0.5,
            structured_data={"series_id": "GDP", "value": 25000.0},
            fact_type="economic_indicator",
        )
    ]
    buf.ingest("engine", items)

    mock_store.store.assert_called_once()


# 9. lake.store_fact raises → errors == 1
def test_ingest_errors_counted(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.side_effect = RuntimeError("DB error")
    buf._lake = mock_lake
    buf._db_manager = MagicMock()

    items = [_make_raw_item(content="A" * 50, quality_hint=0.5)]
    report = buf.ingest("engine", items)

    assert report.errors == 1


# 10. report.started_at and ended_at set
def test_report_has_timestamps(tmp_path):
    from jarvis.ingestion import IngestionBuffer

    buf = IngestionBuffer()
    mock_lake = MagicMock()
    mock_lake.search.return_value = []
    mock_lake.store_fact.return_value = "fid"
    buf._lake = mock_lake
    buf._db_manager = MagicMock()

    report = buf.ingest("engine", [])
    assert report.started_at != ""
    assert report.ended_at != ""
