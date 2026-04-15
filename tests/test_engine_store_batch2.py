"""TDD RED — tests/test_engine_store_batch2.py
Tests for EngineStore Batch 2: Geopolitical and Legal DDL extensions.
"""
from __future__ import annotations
import os
import pytest


def _make_geo_event_row(**kwargs):
    defaults = dict(
        id="geo-001",
        event_type="conflict",
        title="Conflict in Region X",
        description="Armed conflict breaks out in Region X",
        regions='["Europe"]',
        started_at="2024-01-15",
        severity=0.7,
        source="gdelt",
        source_url="https://gdelt.org/article/123",
    )
    defaults.update(kwargs)
    return defaults


def _make_policy_row(**kwargs):
    defaults = dict(
        id="policy-001",
        jurisdiction="US Federal",
        policy_type="legislation",
        title="Infrastructure Investment Act",
        status="introduced",
        introduced_date="2024-01-10",
    )
    defaults.update(kwargs)
    return defaults


def _make_regulatory_row(**kwargs):
    defaults = dict(
        id="reg-001",
        jurisdiction="federal",
        domain="tax",
        title="New Tax Filing Rule",
        description="IRS announces new filing deadline rules",
        source="federal_register",
    )
    defaults.update(kwargs)
    return defaults


# 1. store geopolitical_event → geopolitical.db has the row
def test_geopolitical_events_table_created(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("geopolitical", "geopolitical_events", _make_geo_event_row())
    rows = store.query("geopolitical", "geopolitical_events")
    store.close_all()

    assert os.path.exists(str(tmp_path / "geopolitical.db"))
    assert len(rows) == 1
    assert rows[0]["title"] == "Conflict in Region X"


# 2. store policy_tracker row → retrievable
def test_policy_tracker_table_created(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("geopolitical", "policy_tracker", _make_policy_row())
    rows = store.query("geopolitical", "policy_tracker")
    store.close_all()

    assert len(rows) == 1
    assert rows[0]["jurisdiction"] == "US Federal"
    assert rows[0]["title"] == "Infrastructure Investment Act"


# 3. store regulatory_changes row → retrievable
def test_regulatory_changes_table_created(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("legal", "regulatory_changes", _make_regulatory_row())
    rows = store.query("legal", "regulatory_changes")
    store.close_all()

    assert os.path.exists(str(tmp_path / "legal.db"))
    assert len(rows) == 1
    assert rows[0]["title"] == "New Tax Filing Rule"


# 4. store with engine="geopolitical", table="geopolitical_events" → stored in geopolitical.db
def test_geopolitical_table_routing(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("geopolitical", "geopolitical_events", _make_geo_event_row())
    store.close_all()

    assert os.path.exists(str(tmp_path / "geopolitical.db"))
    # legal.db should NOT be created
    assert not os.path.exists(str(tmp_path / "legal.db"))


# 5. store with engine="legal", table="regulatory_changes" → stored in legal.db
def test_legal_table_routing(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("legal", "regulatory_changes", _make_regulatory_row())
    store.close_all()

    assert os.path.exists(str(tmp_path / "legal.db"))
    # geopolitical.db should NOT be created
    assert not os.path.exists(str(tmp_path / "geopolitical.db"))


# 6. store 2 events, query all → returns 2
def test_query_geopolitical_events(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    store.store("geopolitical", "geopolitical_events", _make_geo_event_row(id="geo-001", title="Event A"))
    store.store("geopolitical", "geopolitical_events", _make_geo_event_row(id="geo-002", title="Event B"))
    rows = store.query("geopolitical", "geopolitical_events")
    store.close_all()

    assert len(rows) == 2
    titles = {r["title"] for r in rows}
    assert "Event A" in titles
    assert "Event B" in titles


# 7. store 3 regulatory changes, count → 3
def test_count_regulatory_changes(tmp_path):
    from jarvis.engine_store import EngineStore

    store = EngineStore(engines_dir=str(tmp_path))
    for i in range(3):
        store.store("legal", "regulatory_changes", _make_regulatory_row(id=f"reg-{i:03d}", title=f"Rule {i}"))

    count = store.count("legal", "regulatory_changes")
    store.close_all()

    assert count == 3
