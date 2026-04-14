"""TDD RED — tests/test_engine_store.py
Tests for EngineStore domain-specific SQLite databases.
"""
from __future__ import annotations
import os
import pytest


def _make_economic_row(**kwargs):
    defaults = dict(
        id="row-001",
        series_id="UNRATE",
        value=3.7,
        period="2024-01",
        frequency="monthly",
        source="FRED",
        retrieved_at="2024-01-15T10:00:00+00:00",
    )
    defaults.update(kwargs)
    return defaults


def _make_market_row(**kwargs):
    defaults = dict(
        id="market-001",
        symbol="SPY",
        date="2024-01-15",
        close=470.0,
        source="yahoo_finance",
    )
    defaults.update(kwargs)
    return defaults


def _make_paper_row(**kwargs):
    defaults = dict(
        id="paper-001",
        title="Test Paper",
        authors="Author One",
        abstract="This is a test abstract about machine learning.",
        published_date="2024-01-15",
        categories="cs.AI",
    )
    defaults.update(kwargs)
    return defaults


def _make_repo_row(**kwargs):
    defaults = dict(
        id="repo-001",
        github_url="https://github.com/test/repo",
        name="test/repo",
        first_seen="2024-01-15T10:00:00+00:00",
        last_checked="2024-01-15T10:00:00+00:00",
    )
    defaults.update(kwargs)
    return defaults


# 1. store to financial table → DB file exists at engines_dir/financial.db
def test_store_creates_db_file(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("financial", "economic_indicators", _make_economic_row())
    store.close_all()

    assert os.path.exists(str(tmp_path / "financial.db"))


# 2. store economic_indicators row → query returns it
def test_store_economic_indicator(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("financial", "economic_indicators", _make_economic_row())
    rows = store.query("financial", "economic_indicators")
    store.close_all()

    assert len(rows) == 1
    assert rows[0]["series_id"] == "UNRATE"
    assert rows[0]["value"] == 3.7


# 3. store market_data row → query returns it
def test_store_market_data(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("financial", "market_data", _make_market_row())
    rows = store.query("financial", "market_data")
    store.close_all()

    assert len(rows) == 1
    assert rows[0]["symbol"] == "SPY"


# 4. store research_papers row → query returns it
def test_store_research_paper(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("research", "research_papers", _make_paper_row())
    rows = store.query("research", "research_papers")
    store.close_all()

    assert len(rows) == 1
    assert rows[0]["title"] == "Test Paper"


# 5. store tracked_repos row → query returns it
def test_store_tracked_repo(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("research", "tracked_repos", _make_repo_row())
    rows = store.query("research", "tracked_repos")
    store.close_all()

    assert len(rows) == 1
    assert rows[0]["name"] == "test/repo"


# 6. 3 rows, where="series_id='UNRATE'" → returns 1
def test_query_with_where(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("financial", "economic_indicators", _make_economic_row(id="r1", series_id="UNRATE"))
    store.store("financial", "economic_indicators", _make_economic_row(id="r2", series_id="GDP"))
    store.store("financial", "economic_indicators", _make_economic_row(id="r3", series_id="CPI"))

    rows = store.query("financial", "economic_indicators", where="series_id='UNRATE'")
    store.close_all()

    assert len(rows) == 1
    assert rows[0]["series_id"] == "UNRATE"


# 7. 3 rows inserted → count returns 3
def test_count_returns_row_count(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    for i in range(3):
        store.store("financial", "economic_indicators", _make_economic_row(id=f"row-{i}", series_id=f"SER{i}"))

    count = store.count("financial", "economic_indicators")
    store.close_all()

    assert count == 3


# 8. store to "research_papers" with engine="research" → stored in research.db
def test_table_engine_routing(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("research", "research_papers", _make_paper_row())
    store.close_all()

    assert os.path.exists(str(tmp_path / "research.db"))
    # financial.db should NOT be created
    assert not os.path.exists(str(tmp_path / "financial.db"))


# 9. store same id twice → count still 1 (upsert)
def test_insert_or_replace(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    row = _make_economic_row(id="upsert-1", value=3.7)
    store.store("financial", "economic_indicators", row)

    row_updated = _make_economic_row(id="upsert-1", value=4.0)
    store.store("financial", "economic_indicators", row_updated)

    count = store.count("financial", "economic_indicators")
    rows = store.query("financial", "economic_indicators")
    store.close_all()

    assert count == 1
    assert rows[0]["value"] == 4.0


# 10. close_all() on empty or populated store — no crash
def test_close_all_no_crash(tmp_path):
    from jarvis.engine_store import EngineStore

    # Empty store
    store1 = EngineStore(engines_dir=str(tmp_path))
    store1.close_all()  # Should not crash

    # Populated store
    store2 = EngineStore(engines_dir=str(tmp_path))
    store2.store("financial", "economic_indicators", _make_economic_row())
    store2.close_all()  # Should not crash
