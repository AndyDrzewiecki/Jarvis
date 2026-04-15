"""Tests for EngineStore DDL — Batch 3 engines: Health, Local, Family.

Verifies all new tables are created and store/query/count operations work.
"""
from __future__ import annotations
import os
import uuid
import pytest


def _make_store(tmp_path):
    from jarvis.engine_store import EngineStore
    return EngineStore(engines_dir=str(tmp_path / "engines"))


# ──────────────────────────────────────────────────────────────────────────────
# Health Engine tables
# ──────────────────────────────────────────────────────────────────────────────

def test_health_ddl_creates_health_knowledge(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("health", "health_knowledge")
    assert count == 0


def test_health_ddl_creates_environmental_data(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("health", "environmental_data")
    assert count == 0


def test_store_health_knowledge(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("health", "health_knowledge", {
        "id": str(uuid.uuid4()),
        "category": "respiratory",
        "title": "Flu Season Alert",
        "content": "Flu activity elevated in MN.",
        "source": "cdc",
        "source_url": "https://cdc.gov/flu",
        "evidence_level": "official",
        "relevance": 0.8,
        "last_verified": "2024-01-15",
        "seasonal": 1,
    })
    assert row_id


def test_query_health_knowledge(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("health", "health_knowledge", {
        "id": row_id,
        "category": "respiratory",
        "title": "Flu Season Alert",
        "content": "Flu activity elevated.",
        "source": "cdc",
        "source_url": "",
        "evidence_level": "official",
        "relevance": 0.8,
        "last_verified": "2024-01-15",
        "seasonal": 1,
    })
    rows = store.query("health", "health_knowledge")
    assert len(rows) == 1
    assert rows[0]["title"] == "Flu Season Alert"


def test_count_health_knowledge(tmp_path):
    store = _make_store(tmp_path)
    for i in range(3):
        store.store("health", "health_knowledge", {
            "id": str(uuid.uuid4()),
            "category": "general_health",
            "title": f"Article {i}",
            "content": "Content.",
            "source": "cdc",
            "source_url": "",
            "evidence_level": "official",
            "relevance": 0.5,
            "last_verified": "2024-01-15",
            "seasonal": 0,
        })
    assert store.count("health", "health_knowledge") == 3


def test_store_environmental_data(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("health", "environmental_data", {
        "id": str(uuid.uuid4()),
        "metric": "AQI_PM2.5",
        "value": 42.0,
        "location": "Minneapolis, MN",
        "measured_at": "2024-01-15T08:00:00+00:00",
        "source": "airnow",
        "forecast": "Good",
    })
    assert row_id


def test_query_environmental_data(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("health", "environmental_data", {
        "id": row_id,
        "metric": "AQI_PM2.5",
        "value": 42.0,
        "location": "Minneapolis, MN",
        "measured_at": "2024-01-15T08:00:00+00:00",
        "source": "airnow",
        "forecast": "Good",
    })
    rows = store.query("health", "environmental_data")
    assert len(rows) == 1
    assert rows[0]["metric"] == "AQI_PM2.5"


def test_count_environmental_data(tmp_path):
    store = _make_store(tmp_path)
    for i in range(5):
        store.store("health", "environmental_data", {
            "id": str(uuid.uuid4()),
            "metric": "AQI_PM2.5",
            "value": float(i * 10),
            "location": "Minneapolis, MN",
            "measured_at": "2024-01-15T08:00:00+00:00",
            "source": "airnow",
            "forecast": "Good",
        })
    assert store.count("health", "environmental_data") == 5


def test_health_knowledge_category_field(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("health", "health_knowledge", {
        "id": row_id, "category": "drug_interaction",
        "title": "Drug Alert", "content": "Be careful.",
        "source": "openfda", "source_url": "", "evidence_level": "case_report",
        "relevance": 0.6, "last_verified": "2024-01-15", "seasonal": 0,
    })
    rows = store.query("health", "health_knowledge", where="category = 'drug_interaction'")
    assert len(rows) == 1


def test_environmental_data_aqi_value(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("health", "environmental_data", {
        "id": row_id, "metric": "AQI_Ozone", "value": 87.5,
        "location": "St. Paul", "measured_at": "2024-01-15T14:00:00+00:00",
        "source": "airnow", "forecast": "Moderate",
    })
    rows = store.query("health", "environmental_data")
    assert rows[0]["value"] == 87.5


def test_environmental_data_update_on_conflict(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    base = {
        "id": row_id, "metric": "AQI_PM2.5", "value": 30.0,
        "location": "Minneapolis", "measured_at": "2024-01-15T08:00:00+00:00",
        "source": "airnow", "forecast": "Good",
    }
    store.store("health", "environmental_data", base)
    base["value"] = 55.0
    store.store("health", "environmental_data", base)
    rows = store.query("health", "environmental_data")
    assert len(rows) == 1
    assert rows[0]["value"] == 55.0


def test_health_knowledge_seasonal_field(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("health", "health_knowledge", {
        "id": row_id, "category": "seasonal_health",
        "title": "Pollen Alert", "content": "High pollen today.",
        "source": "cdc", "source_url": "", "evidence_level": "official",
        "relevance": 0.7, "last_verified": "2024-04-01", "seasonal": 1,
    })
    rows = store.query("health", "health_knowledge", where="seasonal = 1")
    assert len(rows) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Local Intelligence Engine table
# ──────────────────────────────────────────────────────────────────────────────

def test_local_ddl_creates_local_data(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("local", "local_data")
    assert count == 0


def test_store_local_data_weather(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("local", "local_data", {
        "id": str(uuid.uuid4()),
        "category": "weather",
        "title": "Weather: Saturday",
        "content": "Sunny, high near 72.",
        "location": "44.9778,-93.2650",
        "data_date": "2024-04-20",
        "source": "nws",
        "source_url": "https://api.weather.gov/forecast",
        "trend": "Sunny",
    })
    assert row_id


def test_query_local_data(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("local", "local_data", {
        "id": row_id,
        "category": "weather",
        "title": "Weather: Saturday",
        "content": "Sunny.",
        "location": "44.9778,-93.2650",
        "data_date": "2024-04-20",
        "source": "nws",
        "source_url": "",
        "trend": "Sunny",
    })
    rows = store.query("local", "local_data")
    assert len(rows) == 1
    assert rows[0]["category"] == "weather"


def test_count_local_data(tmp_path):
    store = _make_store(tmp_path)
    for i in range(7):
        store.store("local", "local_data", {
            "id": str(uuid.uuid4()),
            "category": "weather",
            "title": f"Period {i}",
            "content": "Forecast.",
            "location": "44,-93",
            "data_date": "2024-04-20",
            "source": "nws",
            "source_url": "",
            "trend": "Sunny",
        })
    assert store.count("local", "local_data") == 7


def test_local_data_category_filter(tmp_path):
    store = _make_store(tmp_path)
    store.store("local", "local_data", {
        "id": str(uuid.uuid4()), "category": "weather", "title": "Weather",
        "content": "Sunny", "location": "44,-93", "data_date": "2024-04-20",
        "source": "nws", "source_url": "", "trend": "Sunny",
    })
    store.store("local", "local_data", {
        "id": str(uuid.uuid4()), "category": "infrastructure", "title": "Road Closure",
        "content": "I-35W closed", "location": "mpls", "data_date": "2024-04-20",
        "source": "local_rss", "source_url": "", "trend": "",
    })
    weather_rows = store.query("local", "local_data", where="category = 'weather'")
    infra_rows = store.query("local", "local_data", where="category = 'infrastructure'")
    assert len(weather_rows) == 1
    assert len(infra_rows) == 1


def test_local_data_table_engine_mapping(tmp_path):
    """local_data table should resolve to 'local' engine."""
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("local_data") == "local"


# ──────────────────────────────────────────────────────────────────────────────
# Family Engine tables
# ──────────────────────────────────────────────────────────────────────────────

def test_family_ddl_creates_family_activities(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("family", "family_activities")
    assert count == 0


def test_family_ddl_creates_vacation_research(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("family", "vacation_research")
    assert count == 0


def test_family_ddl_creates_parenting_knowledge(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("family", "parenting_knowledge")
    assert count == 0


def test_family_ddl_creates_local_events(tmp_path):
    store = _make_store(tmp_path)
    count = store.count("family", "local_events")
    assert count == 0


def test_store_family_activity(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("family", "family_activities", {
        "id": str(uuid.uuid4()),
        "category": "outdoor",
        "title": "Fort Snelling State Park",
        "description": "Hiking along the Minnesota River.",
        "location": "MN",
        "distance_miles": 3.5,
        "cost_estimate": "Free",
        "age_appropriate": "all_ages",
        "duration": "half_day",
        "season": "spring,summer,fall",
        "weather_req": "clear_preferred",
        "source": "nps",
        "source_url": "https://nps.gov/fsnl",
        "rating": 0.9,
    })
    assert row_id


def test_query_family_activities(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("family", "family_activities", {
        "id": row_id, "category": "outdoor", "title": "Hiking Trail",
        "description": "Great trail.", "location": "MN", "distance_miles": 5.0,
        "cost_estimate": "Free", "age_appropriate": "all_ages", "duration": "half_day",
        "season": "all", "weather_req": "any", "source": "nps", "source_url": "",
        "rating": 0.8,
    })
    rows = store.query("family", "family_activities")
    assert len(rows) == 1
    assert rows[0]["title"] == "Hiking Trail"


def test_count_family_activities(tmp_path):
    store = _make_store(tmp_path)
    for i in range(4):
        store.store("family", "family_activities", {
            "id": str(uuid.uuid4()), "category": "outdoor", "title": f"Activity {i}",
            "description": "Fun.", "location": "MN", "distance_miles": float(i),
            "cost_estimate": "Free", "age_appropriate": "all_ages", "duration": "half_day",
            "season": "all", "weather_req": "any", "source": "nps", "source_url": "",
            "rating": 0.7,
        })
    assert store.count("family", "family_activities") == 4


def test_store_vacation_research(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("family", "vacation_research", {
        "id": str(uuid.uuid4()),
        "destination": "Boundary Waters, MN",
        "trip_type": "camping",
        "estimated_cost": 500.0,
        "duration_days": 5,
        "best_season": "summer",
        "kid_friendly": 1,
        "highlights": "Canoeing, fishing, stargazing",
        "logistics": "Permit required",
        "source": "manual",
        "source_url": "",
        "household_interest": 0.9,
        "saved_at": "2024-01-15T00:00:00+00:00",
        "planned_for": "2024-07-01",
    })
    assert row_id


def test_query_vacation_research(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("family", "vacation_research", {
        "id": row_id, "destination": "BWCA", "trip_type": "camping",
        "estimated_cost": 400.0, "duration_days": 4, "best_season": "summer",
        "kid_friendly": 1, "highlights": "Canoe", "logistics": "Permit",
        "source": "manual", "source_url": "", "household_interest": 0.8,
        "saved_at": "2024-01-15T00:00:00+00:00", "planned_for": "",
    })
    rows = store.query("family", "vacation_research")
    assert len(rows) == 1
    assert rows[0]["destination"] == "BWCA"


def test_store_parenting_knowledge(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("family", "parenting_knowledge", {
        "id": str(uuid.uuid4()),
        "category": "screen_time",
        "age_range": "3-5",
        "title": "Screen Time Guidelines for Preschoolers",
        "content": "AAP recommends limiting screen time to 1 hour per day.",
        "source": "aap",
        "evidence_level": "professional_guidance",
        "actionable": 1,
        "seasonal": 0,
    })
    assert row_id


def test_query_parenting_knowledge(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("family", "parenting_knowledge", {
        "id": row_id, "category": "sleep", "age_range": "1-3",
        "title": "Sleep Needs for Toddlers", "content": "12-14 hours.",
        "source": "aap", "evidence_level": "professional_guidance",
        "actionable": 1, "seasonal": 0,
    })
    rows = store.query("family", "parenting_knowledge")
    assert len(rows) == 1
    assert rows[0]["category"] == "sleep"


def test_count_parenting_knowledge(tmp_path):
    store = _make_store(tmp_path)
    for i in range(6):
        store.store("family", "parenting_knowledge", {
            "id": str(uuid.uuid4()), "category": "nutrition", "age_range": "all_ages",
            "title": f"Article {i}", "content": "Content.",
            "source": "aap", "evidence_level": "professional_guidance",
            "actionable": 0, "seasonal": 0,
        })
    assert store.count("family", "parenting_knowledge") == 6


def test_store_local_events(tmp_path):
    store = _make_store(tmp_path)
    row_id = store.store("family", "local_events", {
        "id": str(uuid.uuid4()),
        "title": "Minneapolis Farmers Market",
        "description": "Weekly market with local produce.",
        "venue": "Lyndale Farmstead Park",
        "address": "3900 Bryant Ave S, Minneapolis",
        "event_date": "2024-04-20",
        "event_time": "06:00",
        "end_date": "2024-04-20",
        "cost": "Free",
        "category": "market",
        "family_friendly": 1,
        "source": "eventbrite",
        "source_url": "https://eventbrite.com/e/123",
        "distance_miles": 2.1,
        "relevance": 0.8,
    })
    assert row_id


def test_query_local_events(tmp_path):
    store = _make_store(tmp_path)
    row_id = str(uuid.uuid4())
    store.store("family", "local_events", {
        "id": row_id, "title": "Summer Concert",
        "description": "Free outdoor concert.", "venue": "Loring Park",
        "address": "Minneapolis", "event_date": "2024-06-15",
        "event_time": "18:00", "end_date": "2024-06-15",
        "cost": "Free", "category": "music", "family_friendly": 1,
        "source": "eventbrite", "source_url": "", "distance_miles": 1.0, "relevance": 0.7,
    })
    rows = store.query("family", "local_events")
    assert len(rows) == 1
    assert rows[0]["title"] == "Summer Concert"


def test_local_events_family_friendly_filter(tmp_path):
    store = _make_store(tmp_path)
    store.store("family", "local_events", {
        "id": str(uuid.uuid4()), "title": "Kids Fair", "description": "For kids.",
        "venue": "Park", "address": "123 St", "event_date": "2024-04-20",
        "event_time": "", "end_date": "", "cost": "Free", "category": "kids",
        "family_friendly": 1, "source": "eventbrite", "source_url": "",
        "distance_miles": 1.0, "relevance": 0.9,
    })
    store.store("family", "local_events", {
        "id": str(uuid.uuid4()), "title": "Adult Bar Crawl", "description": "21+ only.",
        "venue": "Bar", "address": "456 Ave", "event_date": "2024-04-20",
        "event_time": "", "end_date": "", "cost": "$20", "category": "nightlife",
        "family_friendly": 0, "source": "eventbrite", "source_url": "",
        "distance_miles": 0.5, "relevance": 0.3,
    })
    family_rows = store.query("family", "local_events", where="family_friendly = 1")
    assert len(family_rows) == 1
    assert family_rows[0]["title"] == "Kids Fair"


def test_family_activities_table_engine_mapping(tmp_path):
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("family_activities") == "family"


def test_vacation_research_table_engine_mapping(tmp_path):
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("vacation_research") == "family"


def test_parenting_knowledge_table_engine_mapping(tmp_path):
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("parenting_knowledge") == "family"


def test_local_events_table_engine_mapping(tmp_path):
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("local_events") == "family"


def test_health_knowledge_table_engine_mapping(tmp_path):
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("health_knowledge") == "health"


def test_environmental_data_table_engine_mapping(tmp_path):
    from jarvis.engine_store import _TABLE_ENGINE
    assert _TABLE_ENGINE.get("environmental_data") == "health"


def test_engine_ddl_has_health_key():
    from jarvis.engine_store import _ENGINE_DDL
    assert "health" in _ENGINE_DDL


def test_engine_ddl_has_local_key():
    from jarvis.engine_store import _ENGINE_DDL
    assert "local" in _ENGINE_DDL


def test_engine_ddl_has_family_key():
    from jarvis.engine_store import _ENGINE_DDL
    assert "family" in _ENGINE_DDL


def test_health_ddl_contains_health_knowledge_table():
    from jarvis.engine_store import _ENGINE_DDL
    assert "health_knowledge" in _ENGINE_DDL["health"]


def test_health_ddl_contains_environmental_data_table():
    from jarvis.engine_store import _ENGINE_DDL
    assert "environmental_data" in _ENGINE_DDL["health"]


def test_local_ddl_contains_local_data_table():
    from jarvis.engine_store import _ENGINE_DDL
    assert "local_data" in _ENGINE_DDL["local"]


def test_family_ddl_contains_family_activities():
    from jarvis.engine_store import _ENGINE_DDL
    assert "family_activities" in _ENGINE_DDL["family"]


def test_family_ddl_contains_vacation_research():
    from jarvis.engine_store import _ENGINE_DDL
    assert "vacation_research" in _ENGINE_DDL["family"]


def test_family_ddl_contains_parenting_knowledge():
    from jarvis.engine_store import _ENGINE_DDL
    assert "parenting_knowledge" in _ENGINE_DDL["family"]


def test_family_ddl_contains_local_events():
    from jarvis.engine_store import _ENGINE_DDL
    assert "local_events" in _ENGINE_DDL["family"]


def test_store_close_all(tmp_path):
    store = _make_store(tmp_path)
    store.count("health", "health_knowledge")
    store.count("local", "local_data")
    store.count("family", "family_activities")
    store.close_all()  # should not raise
    assert len(store._connections) == 0


def test_store_reopen_after_close(tmp_path):
    store = _make_store(tmp_path)
    store.store("health", "health_knowledge", {
        "id": "abc123", "category": "general", "title": "Test",
        "content": "Content", "source": "test", "source_url": "",
        "evidence_level": "manual", "relevance": 0.5, "last_verified": "2024-01-01",
        "seasonal": 0,
    })
    store.close_all()
    count = store.count("health", "health_knowledge")
    assert count == 1


def test_family_activity_times_done_default(tmp_path):
    store = _make_store(tmp_path)
    store.store("family", "family_activities", {
        "id": str(uuid.uuid4()), "category": "outdoor", "title": "Trail Run",
        "description": "Great run.", "location": "MN",
        "cost_estimate": "Free", "age_appropriate": "adults",
        "duration": "2hr", "season": "all", "weather_req": "any",
        "source": "manual", "source_url": "",
    })
    rows = store.query("family", "family_activities")
    assert rows[0]["times_done"] == 0


def test_vacation_research_kid_friendly_default(tmp_path):
    store = _make_store(tmp_path)
    store.store("family", "vacation_research", {
        "id": str(uuid.uuid4()), "destination": "Yellowstone",
        "trip_type": "park", "estimated_cost": 1000.0, "duration_days": 7,
        "best_season": "summer", "highlights": "Geysers", "logistics": "Book early",
        "source": "manual", "source_url": "", "household_interest": 0.9,
        "saved_at": "2024-01-15T00:00:00+00:00",
    })
    rows = store.query("family", "vacation_research")
    assert rows[0]["kid_friendly"] == 1


def test_local_events_default_family_friendly(tmp_path):
    store = _make_store(tmp_path)
    store.store("family", "local_events", {
        "id": str(uuid.uuid4()), "title": "Community Event",
        "description": "For all.", "venue": "Park", "address": "123 St",
        "event_date": "2024-04-20", "event_time": "", "cost": "Free",
        "source": "manual", "source_url": "",
    })
    rows = store.query("family", "local_events")
    assert rows[0]["family_friendly"] == 1


def test_multiple_tables_in_same_engine(tmp_path):
    store = _make_store(tmp_path)
    # Store into two different tables in the family engine
    store.store("family", "family_activities", {
        "id": str(uuid.uuid4()), "category": "outdoor", "title": "Hike",
        "description": "Nice hike.", "location": "MN",
        "cost_estimate": "Free", "age_appropriate": "all_ages", "duration": "3hr",
        "season": "all", "weather_req": "any", "source": "nps", "source_url": "",
    })
    store.store("family", "parenting_knowledge", {
        "id": str(uuid.uuid4()), "category": "nutrition", "age_range": "6-12",
        "title": "Healthy Lunch Ideas", "content": "Pack fruit.",
        "source": "aap", "evidence_level": "professional", "actionable": 1, "seasonal": 0,
    })
    assert store.count("family", "family_activities") == 1
    assert store.count("family", "parenting_knowledge") == 1


def test_health_multiple_tables_independent(tmp_path):
    store = _make_store(tmp_path)
    store.store("health", "health_knowledge", {
        "id": str(uuid.uuid4()), "category": "respiratory", "title": "Flu Alert",
        "content": "High flu activity.", "source": "cdc", "source_url": "",
        "evidence_level": "official", "relevance": 0.8, "last_verified": "2024-01-15", "seasonal": 1,
    })
    store.store("health", "environmental_data", {
        "id": str(uuid.uuid4()), "metric": "AQI_PM2.5", "value": 50.0,
        "location": "Minneapolis", "measured_at": "2024-01-15T08:00:00+00:00",
        "source": "airnow", "forecast": "Moderate",
    })
    assert store.count("health", "health_knowledge") == 1
    assert store.count("health", "environmental_data") == 1
