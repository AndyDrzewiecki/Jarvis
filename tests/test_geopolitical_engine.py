"""TDD RED — tests/test_geopolitical_engine.py
Tests for GeopoliticalEngine (Engine 2).
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch
from io import BytesIO


def _make_gdelt_response(articles=None):
    if articles is None:
        articles = [
            {
                "title": "Conflict erupts in Eastern Europe",
                "url": "https://example.com/article1",
                "seendate": "20240115T120000Z",
                "domain": "bbc.com",
                "tone": -8.5,
            }
        ]
    return json.dumps({"articles": articles}).encode()


def _make_congress_response(bills=None):
    if bills is None:
        bills = [
            {
                "title": "Infrastructure Investment and Jobs Act",
                "number": "1234",
                "congress": "118",
                "type": "HR",
                "originChamber": "House",
                "latestAction": {"text": "Passed House on Jan 10, 2024"},
                "updateDate": "2024-01-10",
            }
        ]
    return json.dumps({"bills": bills}).encode()


def _make_rss_response(items=None):
    """Build a minimal RSS 2.0 XML response."""
    if items is None:
        items = [
            ("World Tensions Rise", "https://news.com/1", "Tensions rising globally."),
            ("Trade War Update", "https://news.com/2", "New tariffs announced."),
        ]
    item_xml = ""
    for title, link, desc in items:
        item_xml += f"""
        <item>
            <title>{title}</title>
            <link>{link}</link>
            <description>{desc}</description>
        </item>"""
    xml = f"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>World News</title>{item_xml}
  </channel>
</rss>""".encode()
    return xml


def _make_urlopen_mock(response_bytes: bytes):
    resp = MagicMock()
    resp.read.return_value = response_bytes
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# 1. GeopoliticalEngine in ENGINE_REGISTRY
def test_geopolitical_engine_registered():
    import jarvis.engines.geopolitical  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    names = [cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")]
    assert "geopolitical_engine" in names


# 2. mock urlopen with GDELT JSON → gather returns article dicts
def test_gather_gdelt_mock():
    from jarvis.engines.geopolitical import GeopoliticalEngine

    eng = GeopoliticalEngine()
    resp_mock = _make_urlopen_mock(_make_gdelt_response())

    with patch("jarvis.config.CONGRESS_API_KEY", ""), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", []), \
         patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    gdelt_items = [r for r in result if r.get("type") == "gdelt"]
    assert len(gdelt_items) >= 1
    assert gdelt_items[0]["title"] == "Conflict erupts in Eastern Europe"


# 3. mock urlopen with Congress JSON → gather returns bill dicts
def test_gather_congress_mock():
    from jarvis.engines.geopolitical import GeopoliticalEngine

    eng = GeopoliticalEngine()
    resp_mock = _make_urlopen_mock(_make_congress_response())

    with patch("jarvis.config.CONGRESS_API_KEY", "test-key"), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", []), \
         patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    congress_items = [r for r in result if r.get("type") == "congress"]
    assert len(congress_items) >= 1
    assert "Infrastructure" in congress_items[0]["title"]


# 4. mock urlopen with RSS XML (2 items) → gather returns 2 rss dicts
def test_gather_rss_mock():
    from jarvis.engines.geopolitical import GeopoliticalEngine

    eng = GeopoliticalEngine()
    resp_mock = _make_urlopen_mock(_make_rss_response())

    with patch("jarvis.config.CONGRESS_API_KEY", ""), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", ["https://feeds.example.com/world"]), \
         patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    rss_items = [r for r in result if r.get("type") == "rss"]
    assert len(rss_items) == 2


# 5. CONGRESS_API_KEY="" → Congress fetch skipped, no crash
def test_gather_no_congress_key_skips():
    from jarvis.engines.geopolitical import GeopoliticalEngine

    eng = GeopoliticalEngine()
    gdelt_resp = _make_urlopen_mock(_make_gdelt_response())

    with patch("jarvis.config.CONGRESS_API_KEY", ""), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", []), \
         patch("urllib.request.urlopen", return_value=gdelt_resp):
        result = eng.gather()

    # Should not have any congress items
    congress_items = [r for r in result if r.get("type") == "congress"]
    assert congress_items == []


# 6. GEOPOLITICAL_FEEDS=[] → RSS fetch skipped, no crash
def test_gather_no_geo_feeds_skips():
    from jarvis.engines.geopolitical import GeopoliticalEngine

    eng = GeopoliticalEngine()
    gdelt_resp = _make_urlopen_mock(_make_gdelt_response())

    with patch("jarvis.config.CONGRESS_API_KEY", ""), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", []), \
         patch("urllib.request.urlopen", return_value=gdelt_resp):
        result = eng.gather()

    rss_items = [r for r in result if r.get("type") == "rss"]
    assert rss_items == []


# 7. urlopen raises URLError → gather returns [] (no crash)
def test_gather_http_error_graceful():
    from jarvis.engines.geopolitical import GeopoliticalEngine
    import urllib.error

    eng = GeopoliticalEngine()

    with patch("jarvis.config.CONGRESS_API_KEY", ""), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", []), \
         patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = eng.gather()

    assert isinstance(result, list)


# 8. gdelt raw dict → RawItem with fact_type="geopolitical_event"
def test_prepare_items_gdelt():
    from jarvis.engines.geopolitical import GeopoliticalEngine
    from jarvis.ingestion import RawItem

    eng = GeopoliticalEngine()
    raw = [
        {
            "type": "gdelt",
            "title": "Conflict in Region X",
            "url": "https://gdelt.org/article1",
            "seendate": "20240115",
            "tone": -8.5,
        }
    ]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RawItem)
    assert item.fact_type == "geopolitical_event"
    assert item.structured_data is not None
    assert "title" in item.structured_data
    assert "regions" in item.structured_data
    assert item.source == "gdelt"


# 9. congress raw dict → RawItem with fact_type="policy_tracker", structured_data has jurisdiction
def test_prepare_items_congress():
    from jarvis.engines.geopolitical import GeopoliticalEngine
    from jarvis.ingestion import RawItem

    eng = GeopoliticalEngine()
    raw = [
        {
            "type": "congress",
            "title": "Infrastructure Act",
            "number": "1234",
            "congress": "118",
            "type": "congress",
            "origin": "House",
            "latest_action": "Passed House",
            "update_date": "2024-01-10",
            "url": "https://congress.gov/bill/118/hr-bill/1234",
        }
    ]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RawItem)
    assert item.fact_type == "policy_tracker"
    assert item.structured_data is not None
    assert item.structured_data.get("jurisdiction") == "US Federal"
    assert item.source == "congress_gov"


# 10. rss raw dict → RawItem with fact_type="geopolitical_event"
def test_prepare_items_rss():
    from jarvis.engines.geopolitical import GeopoliticalEngine
    from jarvis.ingestion import RawItem

    eng = GeopoliticalEngine()
    raw = [
        {
            "type": "rss",
            "title": "World News Headline",
            "url": "https://news.com/1",
            "description": "Breaking: major world event.",
            "feed": "https://feeds.example.com/world",
        }
    ]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RawItem)
    assert item.fact_type == "geopolitical_event"
    assert item.source == "rss"


# 11. improve() returns list
def test_improve_returns_list():
    from jarvis.engines.geopolitical import GeopoliticalEngine

    eng = GeopoliticalEngine()
    with patch("jarvis.config.CONGRESS_API_KEY", ""), \
         patch("jarvis.config.GEOPOLITICAL_FEEDS", []):
        result = eng.improve()

    assert isinstance(result, list)


# 12. mock ingestion.ingest → called during run_cycle when items exist
def test_run_cycle_uses_ingestion_buffer():
    from jarvis.engines.geopolitical import GeopoliticalEngine
    from jarvis.ingestion import RawItem

    eng = GeopoliticalEngine()

    dummy_item = RawItem(
        content="Test geopolitical event",
        source="gdelt",
        fact_type="geopolitical_event",
        domain="geopolitical",
    )
    eng.gather = MagicMock(return_value=[{"type": "gdelt", "title": "Test", "tone": 0}])
    eng.prepare_items = MagicMock(return_value=[dummy_item])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=1)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    mock_ingest.ingest.assert_called_once()
    assert report is not None
    assert report.error is None
