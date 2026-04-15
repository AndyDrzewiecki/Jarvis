"""Comprehensive tests for HealthEngine (Engine 5).

Tests cover:
- ENGINE_REGISTRY registration
- gather() with/without AIRNOW_API_KEY
- _fetch_airnow_aqi: success, empty, HTTP error, malformed JSON
- _fetch_cdc_rss: RSS 2.0, Atom, multiple feeds, errors, malformed XML
- _fetch_openfda_events: success, multiple, errors, missing fields
- prepare_items: airnow, cdc_rss, openfda types, mixed, empty
- improve(): no API key, stale data
- _classify_cdc_title: all branches
- Edge cases: unicode, long content, empty strings
- run_cycle integration
- AQI category formatting
- Seasonal flag detection
- Serious vs non-serious OpenFDA events
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch, call

import pytest

from jarvis.engines.health import HealthEngine, _classify_cdc_title
from jarvis.ingestion import RawItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_urlopen_mock(response_bytes: bytes):
    resp = MagicMock()
    resp.read.return_value = response_bytes
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _make_airnow_response(obs=None):
    if obs is None:
        obs = [
            {
                "AQI": 42,
                "Category": {"Name": "Good"},
                "ParameterName": "PM2.5",
                "ReportingArea": "Minneapolis",
                "DateObserved": "2024-01-15",
                "HourObserved": 8,
            }
        ]
    return json.dumps(obs).encode()


def _make_rss2_response(items=None):
    if items is None:
        items = [
            ("CDC Health Alert: Flu Season Update", "https://cdc.gov/news/1", "Flu activity rising.", "Mon, 15 Jan 2024 12:00:00 GMT"),
        ]
    item_xml = ""
    for title, link, desc, pub in items:
        item_xml += f"""
    <item>
      <title>{title}</title>
      <link>{link}</link>
      <description>{desc}</description>
      <pubDate>{pub}</pubDate>
    </item>"""
    xml = f"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>CDC News</title>{item_xml}
  </channel>
</rss>""".encode()
    return xml


def _make_atom_response(entries=None):
    if entries is None:
        entries = [
            ("Vaccination Campaign Launched", "https://cdc.gov/vaccine/1", "New vaccination drive underway."),
        ]
    entry_xml = ""
    for title, href, summary in entries:
        entry_xml += f"""
  <atom:entry>
    <atom:title>{title}</atom:title>
    <atom:link href="{href}"/>
    <atom:summary>{summary}</atom:summary>
  </atom:entry>"""
    xml = f"""<?xml version="1.0"?>
<atom:feed xmlns:atom="http://www.w3.org/2005/Atom">
  <atom:title>CDC Feed</atom:title>{entry_xml}
</atom:feed>""".encode()
    return xml


def _make_openfda_response(events=None):
    if events is None:
        events = [
            {
                "serious": 1,
                "receivedate": "20240115",
                "patient": {
                    "drug": [{"medicinalproduct": "ASPIRIN"}],
                    "reaction": [{"reactionmeddrapt": "Nausea"}],
                },
            }
        ]
    return json.dumps({"results": events}).encode()


def _new_engine():
    return HealthEngine()


# ===========================================================================
# 1. ENGINE_REGISTRY registration
# ===========================================================================

def test_health_engine_registered():
    import jarvis.engines.health  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    names = [cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")]
    assert "health_engine" in names


def test_health_engine_registered_class_is_health_engine():
    import jarvis.engines.health  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    classes = [cls for cls in ENGINE_REGISTRY if hasattr(cls, "name") and cls.name == "health_engine"]
    assert len(classes) >= 1
    assert classes[0] is HealthEngine


# ===========================================================================
# 2. gather() — with and without AIRNOW_API_KEY
# ===========================================================================

def test_gather_no_api_key_skips_airnow():
    eng = _new_engine()
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "airnowapi" in url:
            raise AssertionError("Should not call AirNow without API key")
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", ""), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    airnow_items = [r for r in result if r.get("type") == "airnow"]
    assert airnow_items == []


def test_gather_with_api_key_calls_airnow():
    eng = _new_engine()
    airnow_resp = _make_urlopen_mock(_make_airnow_response())
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())
    call_order = []

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "airnowapi" in url:
            call_order.append("airnow")
            return airnow_resp
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            call_order.append("cdc")
            return cdc_resp
        if "fda.gov" in url:
            call_order.append("fda")
            return openfda_resp
        return _make_urlopen_mock(b"[]")

    with patch("jarvis.config.AIRNOW_API_KEY", "test-key-123"), \
         patch("jarvis.config.HOME_ZIP_CODE", "55401"), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    airnow_items = [r for r in result if r.get("type") == "airnow"]
    assert len(airnow_items) >= 1
    assert "airnow" in call_order


def test_gather_always_calls_cdc_rss():
    eng = _new_engine()
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())
    urls_called = []

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        urls_called.append(url)
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", ""), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        eng.gather()

    assert any("cdc" in u.lower() for u in urls_called)


def test_gather_always_calls_openfda():
    eng = _new_engine()
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())
    urls_called = []

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        urls_called.append(url)
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", ""), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        eng.gather()

    assert any("fda.gov" in u.lower() for u in urls_called)


def test_gather_returns_list():
    eng = _new_engine()
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", ""), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    assert isinstance(result, list)


def test_gather_all_sources_combined():
    eng = _new_engine()
    airnow_resp = _make_urlopen_mock(_make_airnow_response())
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "airnowapi" in url:
            return airnow_resp
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        if "fda.gov" in url:
            return openfda_resp
        return _make_urlopen_mock(b"[]")

    with patch("jarvis.config.AIRNOW_API_KEY", "test-key"), \
         patch("jarvis.config.HOME_ZIP_CODE", "55401"), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    types = {r.get("type") for r in result}
    assert "airnow" in types
    assert "openfda" in types


# ===========================================================================
# 3. _fetch_airnow_aqi
# ===========================================================================

def test_fetch_airnow_aqi_success_single_obs():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert len(result) == 1
    assert result[0]["type"] == "airnow"


def test_fetch_airnow_aqi_aqi_value():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["aqi"] == 42


def test_fetch_airnow_aqi_category():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["category"] == "Good"


def test_fetch_airnow_aqi_pollutant():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["pollutant"] == "PM2.5"


def test_fetch_airnow_aqi_location():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["location"] == "Minneapolis"


def test_fetch_airnow_aqi_date_observed():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["date_observed"] == "2024-01-15"


def test_fetch_airnow_aqi_hour_observed():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["hour_observed"] == 8


def test_fetch_airnow_aqi_source_url_contains_zip():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_airnow_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert "55401" in result[0]["source_url"]


def test_fetch_airnow_aqi_empty_response():
    eng = _new_engine()
    resp = _make_urlopen_mock(b"[]")
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result == []


def test_fetch_airnow_aqi_http_error_returns_empty():
    eng = _new_engine()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result == []


def test_fetch_airnow_aqi_malformed_json_returns_empty():
    eng = _new_engine()
    resp = _make_urlopen_mock(b"not valid json{{")
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result == []


def test_fetch_airnow_aqi_multiple_obs():
    eng = _new_engine()
    obs = [
        {"AQI": 42, "Category": {"Name": "Good"}, "ParameterName": "PM2.5", "ReportingArea": "Minneapolis", "DateObserved": "2024-01-15", "HourObserved": 8},
        {"AQI": 55, "Category": {"Name": "Moderate"}, "ParameterName": "Ozone", "ReportingArea": "Minneapolis", "DateObserved": "2024-01-15", "HourObserved": 8},
    ]
    resp = _make_urlopen_mock(json.dumps(obs).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert len(result) == 2
    assert result[0]["pollutant"] == "PM2.5"
    assert result[1]["pollutant"] == "Ozone"


def test_fetch_airnow_aqi_missing_category_name():
    eng = _new_engine()
    obs = [{"AQI": 10, "Category": {}, "ParameterName": "PM2.5", "ReportingArea": "City", "DateObserved": "2024-01-15", "HourObserved": 0}]
    resp = _make_urlopen_mock(json.dumps(obs).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result[0]["category"] == ""


def test_fetch_airnow_aqi_fallback_location_to_zip():
    eng = _new_engine()
    obs = [{"AQI": 10, "Category": {"Name": "Good"}, "ParameterName": "PM2.5", "DateObserved": "2024-01-15", "HourObserved": 0}]
    resp = _make_urlopen_mock(json.dumps(obs).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("test-key", "99999")
    assert result[0]["location"] == "99999"


def test_fetch_airnow_aqi_generic_exception_returns_empty():
    eng = _new_engine()
    with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
        result = eng._fetch_airnow_aqi("test-key", "55401")
    assert result == []


def test_fetch_airnow_aqi_ozone_pollutant():
    eng = _new_engine()
    obs = [{"AQI": 70, "Category": {"Name": "Moderate"}, "ParameterName": "Ozone", "ReportingArea": "Metro", "DateObserved": "2024-06-01", "HourObserved": 14}]
    resp = _make_urlopen_mock(json.dumps(obs).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("key", "10001")
    assert result[0]["pollutant"] == "Ozone"
    assert result[0]["aqi"] == 70


def test_fetch_airnow_aqi_unhealthy_category():
    eng = _new_engine()
    obs = [{"AQI": 165, "Category": {"Name": "Unhealthy"}, "ParameterName": "PM2.5", "ReportingArea": "City", "DateObserved": "2024-01-15", "HourObserved": 12}]
    resp = _make_urlopen_mock(json.dumps(obs).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("key", "55401")
    assert result[0]["category"] == "Unhealthy"
    assert result[0]["aqi"] == 165


# ===========================================================================
# 4. _fetch_cdc_rss
# ===========================================================================

def test_fetch_cdc_rss_success_rss2():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    assert len(cdc_items) >= 1


def test_fetch_cdc_rss_title_present():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert result[0]["title"] == "CDC Health Alert: Flu Season Update"


def test_fetch_cdc_rss_url_present():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert result[0]["url"] == "https://cdc.gov/news/1"


def test_fetch_cdc_rss_description_present():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert "Flu activity" in result[0]["description"]


def test_fetch_cdc_rss_pub_date_present():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert result[0]["pub_date"] == "Mon, 15 Jan 2024 12:00:00 GMT"


def test_fetch_cdc_rss_feed_url_recorded():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert "cdc" in result[0]["feed"].lower()


def test_fetch_cdc_rss_atom_success():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_atom_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    assert len(cdc_items) >= 1
    assert any("Vaccination" in r["title"] for r in cdc_items)


def test_fetch_cdc_rss_atom_title():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_atom_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    titles = [r["title"] for r in result]
    assert "Vaccination Campaign Launched" in titles


def test_fetch_cdc_rss_atom_url():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_atom_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    urls = [r["url"] for r in result]
    assert "https://cdc.gov/vaccine/1" in urls


def test_fetch_cdc_rss_atom_summary():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_atom_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    descs = [r["description"] for r in result]
    assert any("vaccination" in d.lower() for d in descs)


def test_fetch_cdc_rss_multiple_rss2_items():
    eng = _new_engine()
    items = [
        ("Flu Update", "https://cdc.gov/1", "Flu rising.", "Mon, 15 Jan 2024 12:00:00 GMT"),
        ("Vaccine Drive", "https://cdc.gov/2", "New vaccines.", "Tue, 16 Jan 2024 12:00:00 GMT"),
        ("Food Safety", "https://cdc.gov/3", "Salmonella outbreak.", "Wed, 17 Jan 2024 12:00:00 GMT"),
    ]
    resp = _make_urlopen_mock(_make_rss2_response(items))
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    # Two feeds are called, so items may be doubled
    titles = [r["title"] for r in cdc_items]
    assert "Flu Update" in titles
    assert "Vaccine Drive" in titles
    assert "Food Safety" in titles


def test_fetch_cdc_rss_http_error_continues():
    eng = _new_engine()
    call_count = [0]

    def side_effect(req, timeout=15):
        call_count[0] += 1
        if call_count[0] == 1:
            raise urllib.error.URLError("timeout")
        return _make_urlopen_mock(_make_rss2_response())

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng._fetch_cdc_rss()
    # Should still return results from second feed
    assert isinstance(result, list)


def test_fetch_cdc_rss_both_feeds_error_returns_empty():
    eng = _new_engine()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        result = eng._fetch_cdc_rss()
    assert result == []


def test_fetch_cdc_rss_malformed_xml_returns_empty():
    eng = _new_engine()
    resp = _make_urlopen_mock(b"<not valid xml <<>>")
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert isinstance(result, list)


def test_fetch_cdc_rss_empty_feed_no_items():
    eng = _new_engine()
    xml = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>CDC News</title>
  </channel>
</rss>"""
    resp = _make_urlopen_mock(xml)
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    assert cdc_items == []


def test_fetch_cdc_rss_skips_items_without_title():
    eng = _new_engine()
    xml = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>CDC</title>
    <item>
      <title></title>
      <link>https://cdc.gov/1</link>
    </item>
  </channel>
</rss>"""
    resp = _make_urlopen_mock(xml)
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    assert cdc_items == []


def test_fetch_cdc_rss_description_truncated_at_500():
    eng = _new_engine()
    long_desc = "X" * 600
    items = [("Long Article", "https://cdc.gov/1", long_desc, "")]
    resp = _make_urlopen_mock(_make_rss2_response(items))
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    for item in cdc_items:
        assert len(item["description"]) <= 500


def test_fetch_cdc_rss_multiple_atom_entries():
    eng = _new_engine()
    entries = [
        ("Flu Alert", "https://cdc.gov/flu", "Flu spreading."),
        ("COVID Update", "https://cdc.gov/covid", "COVID cases."),
    ]
    resp = _make_urlopen_mock(_make_atom_response(entries))
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    titles = [r["title"] for r in result]
    assert "Flu Alert" in titles
    assert "COVID Update" in titles


def test_fetch_cdc_rss_atom_pub_date_empty():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_atom_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    atom_items = [r for r in result if r.get("type") == "cdc_rss" and r.get("url") == "https://cdc.gov/vaccine/1"]
    assert atom_items[0]["pub_date"] == ""


def test_fetch_cdc_rss_type_field():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_rss2_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    for item in result:
        assert item["type"] == "cdc_rss"


# ===========================================================================
# 5. _fetch_openfda_events
# ===========================================================================

def test_fetch_openfda_success():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert len(result) >= 1
    assert result[0]["type"] == "openfda"


def test_fetch_openfda_drug_names():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert "ASPIRIN" in result[0]["drug_names"]


def test_fetch_openfda_reactions():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert "Nausea" in result[0]["reactions"]


def test_fetch_openfda_serious_flag():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result[0]["serious"] == 1


def test_fetch_openfda_receive_date():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result[0]["receive_date"] == "20240115"


def test_fetch_openfda_source_url():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert "fda.gov" in result[0]["source_url"]


def test_fetch_openfda_http_error_returns_empty():
    eng = _new_engine()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
        result = eng._fetch_openfda_events()
    assert result == []


def test_fetch_openfda_malformed_json_returns_empty():
    eng = _new_engine()
    resp = _make_urlopen_mock(b"{{invalid json")
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result == []


def test_fetch_openfda_empty_results():
    eng = _new_engine()
    resp = _make_urlopen_mock(json.dumps({"results": []}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result == []


def test_fetch_openfda_missing_drug_names_skips():
    eng = _new_engine()
    events = [
        {
            "serious": 1,
            "receivedate": "20240115",
            "patient": {
                "drug": [],
                "reaction": [{"reactionmeddrapt": "Headache"}],
            },
        }
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result == []


def test_fetch_openfda_multiple_drugs_joined():
    eng = _new_engine()
    events = [
        {
            "serious": 0,
            "receivedate": "20240115",
            "patient": {
                "drug": [
                    {"medicinalproduct": "ASPIRIN"},
                    {"medicinalproduct": "IBUPROFEN"},
                    {"medicinalproduct": "ACETAMINOPHEN"},
                ],
                "reaction": [{"reactionmeddrapt": "Rash"}],
            },
        }
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert "ASPIRIN" in result[0]["drug_names"]
    assert "IBUPROFEN" in result[0]["drug_names"]


def test_fetch_openfda_caps_drugs_at_3():
    eng = _new_engine()
    events = [
        {
            "serious": 0,
            "receivedate": "20240115",
            "patient": {
                "drug": [
                    {"medicinalproduct": "DRUG1"},
                    {"medicinalproduct": "DRUG2"},
                    {"medicinalproduct": "DRUG3"},
                    {"medicinalproduct": "DRUG4"},
                    {"medicinalproduct": "DRUG5"},
                ],
                "reaction": [],
            },
        }
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert "DRUG4" not in result[0]["drug_names"]
    assert "DRUG5" not in result[0]["drug_names"]


def test_fetch_openfda_non_serious():
    eng = _new_engine()
    events = [
        {
            "serious": 0,
            "receivedate": "20240115",
            "patient": {
                "drug": [{"medicinalproduct": "TYLENOL"}],
                "reaction": [{"reactionmeddrapt": "Dizziness"}],
            },
        }
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result[0]["serious"] == 0


def test_fetch_openfda_missing_patient_field():
    eng = _new_engine()
    events = [{"serious": 1, "receivedate": "20240115"}]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result == []


# ===========================================================================
# 6. prepare_items — airnow type
# ===========================================================================

def _airnow_raw(**kwargs):
    base = {
        "type": "airnow",
        "aqi": 42,
        "category": "Good",
        "pollutant": "PM2.5",
        "location": "Minneapolis",
        "date_observed": "2024-01-15",
        "hour_observed": 8,
        "source_url": "https://airnowapi.org/test",
    }
    base.update(kwargs)
    return base


def test_prepare_airnow_returns_raw_item():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert len(items) == 1
    assert isinstance(items[0], RawItem)


def test_prepare_airnow_content_contains_location():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(location="Minneapolis")])
    assert "Minneapolis" in items[0].content


def test_prepare_airnow_content_contains_aqi():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=42)])
    assert "42" in items[0].content


def test_prepare_airnow_content_contains_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(category="Good")])
    assert "Good" in items[0].content


def test_prepare_airnow_content_contains_pollutant():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="PM2.5")])
    assert "PM2.5" in items[0].content


def test_prepare_airnow_content_contains_date():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(date_observed="2024-01-15")])
    assert "2024-01-15" in items[0].content


def test_prepare_airnow_source_is_airnow():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert items[0].source == "airnow"


def test_prepare_airnow_fact_type():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert items[0].fact_type == "environmental_data"


def test_prepare_airnow_domain_is_health():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert items[0].domain == "health"


def test_prepare_airnow_quality_hint():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert items[0].quality_hint == pytest.approx(0.8)


def test_prepare_airnow_source_url():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(source_url="https://airnow.gov/test")])
    assert items[0].source_url == "https://airnow.gov/test"


def test_prepare_airnow_structured_data_metric():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="PM2.5")])
    assert items[0].structured_data["metric"] == "AQI_PM2.5"


def test_prepare_airnow_structured_data_value():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=42)])
    assert items[0].structured_data["value"] == pytest.approx(42.0)


def test_prepare_airnow_structured_data_location():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(location="Minneapolis")])
    assert items[0].structured_data["location"] == "Minneapolis"


def test_prepare_airnow_structured_data_source():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert items[0].structured_data["source"] == "airnow"


def test_prepare_airnow_structured_data_forecast():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(category="Good")])
    assert items[0].structured_data["forecast"] == "Good"


def test_prepare_airnow_structured_data_measured_at_format():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(date_observed="2024-01-15", hour_observed=8)])
    measured = items[0].structured_data["measured_at"]
    assert measured == "2024-01-15T08:00:00+00:00"


def test_prepare_airnow_structured_data_measured_at_midnight():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(date_observed="2024-06-01", hour_observed=0)])
    assert items[0].structured_data["measured_at"] == "2024-06-01T00:00:00+00:00"


def test_prepare_airnow_tags_contain_health():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert "health" in items[0].tags


def test_prepare_airnow_tags_contain_air_quality():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert "air_quality" in items[0].tags


def test_prepare_airnow_tags_contain_aqi():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert "aqi" in items[0].tags


def test_prepare_airnow_tags_contain_pollutant_lowercase():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="PM2.5")])
    assert "pm2.5" in items[0].tags


def test_prepare_airnow_ozone_metric():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="Ozone")])
    assert items[0].structured_data["metric"] == "AQI_Ozone"


def test_prepare_airnow_ozone_tags():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="Ozone")])
    assert "ozone" in items[0].tags


def test_prepare_airnow_high_aqi_unhealthy():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=165, category="Unhealthy")])
    assert "Unhealthy" in items[0].content
    assert items[0].structured_data["value"] == pytest.approx(165.0)


def test_prepare_airnow_pollutant_with_space_in_metric():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="PM 2.5")])
    assert " " not in items[0].structured_data["metric"]


def test_prepare_airnow_pollutant_space_replaced_with_underscore():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="Fine Particles")])
    assert items[0].structured_data["metric"] == "AQI_Fine_Particles"


# ===========================================================================
# 7. prepare_items — cdc_rss type
# ===========================================================================

def _cdc_raw(**kwargs):
    base = {
        "type": "cdc_rss",
        "title": "CDC Health Alert: Flu Season Update",
        "description": "Flu activity is rising across multiple states.",
        "url": "https://cdc.gov/news/1",
        "pub_date": "Mon, 15 Jan 2024 12:00:00 GMT",
        "feed": "https://tools.cdc.gov/api/v2/resources/media/rss",
    }
    base.update(kwargs)
    return base


def test_prepare_cdc_returns_raw_item():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert len(items) == 1
    assert isinstance(items[0], RawItem)


def test_prepare_cdc_source_is_cdc():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].source == "cdc"


def test_prepare_cdc_fact_type():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].fact_type == "health_knowledge"


def test_prepare_cdc_domain_is_health():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].domain == "health"


def test_prepare_cdc_quality_hint():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].quality_hint == pytest.approx(0.7)


def test_prepare_cdc_content_starts_with_prefix():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Flu Alert")])
    assert items[0].content.startswith("CDC health alert: Flu Alert")


def test_prepare_cdc_content_includes_description():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(description="Details about the flu.")])
    assert "Details about the flu." in items[0].content


def test_prepare_cdc_source_url():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(url="https://cdc.gov/news/42")])
    assert items[0].source_url == "https://cdc.gov/news/42"


def test_prepare_cdc_source_url_empty_string_becomes_none():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(url="")])
    assert items[0].source_url is None


def test_prepare_cdc_structured_data_category_respiratory():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Flu Season: Rising Cases")])
    assert items[0].structured_data["category"] == "respiratory"


def test_prepare_cdc_structured_data_category_vaccination():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="New Vaccine Approved by CDC")])
    assert items[0].structured_data["category"] == "vaccination"


def test_prepare_cdc_structured_data_category_food_safety():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Salmonella Outbreak Detected")])
    assert items[0].structured_data["category"] == "food_safety"


def test_prepare_cdc_structured_data_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="My CDC Title")])
    assert items[0].structured_data["title"] == "My CDC Title"


def test_prepare_cdc_structured_data_content_from_desc():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(description="Full description here.")])
    assert "Full description here." in items[0].structured_data["content"]


def test_prepare_cdc_structured_data_content_falls_back_to_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(description="", title="Fallback Title")])
    assert items[0].structured_data["content"] == "Fallback Title"


def test_prepare_cdc_structured_data_source():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].structured_data["source"] == "cdc"


def test_prepare_cdc_structured_data_source_url():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(url="https://cdc.gov/99")])
    assert items[0].structured_data["source_url"] == "https://cdc.gov/99"


def test_prepare_cdc_structured_data_evidence_level():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].structured_data["evidence_level"] == "official"


def test_prepare_cdc_structured_data_relevance():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert items[0].structured_data["relevance"] == pytest.approx(0.7)


def test_prepare_cdc_structured_data_last_verified_is_date():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    lv = items[0].structured_data["last_verified"]
    assert len(lv) == 10
    assert "-" in lv


def test_prepare_cdc_tags_contain_health():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert "health" in items[0].tags


def test_prepare_cdc_tags_contain_cdc():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert "cdc" in items[0].tags


def test_prepare_cdc_tags_contain_category():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Flu Season")])
    assert "respiratory" in items[0].tags


def test_prepare_cdc_seasonal_flu_title_is_1():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Flu Season 2024 Update")])
    assert items[0].structured_data["seasonal"] == 1


def test_prepare_cdc_seasonal_influenza_title_is_1():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Influenza Surveillance Report")])
    assert items[0].structured_data["seasonal"] == 1


def test_prepare_cdc_seasonal_pollen_is_1():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="High Pollen Count Expected")])
    assert items[0].structured_data["seasonal"] == 1


def test_prepare_cdc_seasonal_allerg_is_1():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Allergy Season Forecast")])
    assert items[0].structured_data["seasonal"] == 1


def test_prepare_cdc_seasonal_winter_is_1():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Winter Health Tips")])
    assert items[0].structured_data["seasonal"] == 1


def test_prepare_cdc_seasonal_summer_is_1():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Summer Heat Safety")])
    assert items[0].structured_data["seasonal"] == 1


def test_prepare_cdc_seasonal_non_seasonal_is_0():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Cancer Prevention Guidelines")])
    assert items[0].structured_data["seasonal"] == 0


def test_prepare_cdc_seasonal_vaccine_title_is_0():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Vaccine Efficacy Study")])
    assert items[0].structured_data["seasonal"] == 0


def test_prepare_cdc_content_truncates_description_at_300():
    eng = _new_engine()
    long_desc = "A" * 400
    items = eng.prepare_items([_cdc_raw(description=long_desc, title="Test")])
    # content = "CDC health alert: Test. " + desc[:300]
    assert len(items[0].content) <= len("CDC health alert: Test. ") + 300


def test_prepare_cdc_structured_content_truncates_at_1000():
    eng = _new_engine()
    long_desc = "B" * 1200
    items = eng.prepare_items([_cdc_raw(description=long_desc)])
    assert len(items[0].structured_data["content"]) <= 1000


# ===========================================================================
# 8. prepare_items — openfda type
# ===========================================================================

def _openfda_raw(**kwargs):
    base = {
        "type": "openfda",
        "drug_names": "ASPIRIN",
        "reactions": "Nausea",
        "serious": 1,
        "receive_date": "20240115",
        "source_url": "https://api.fda.gov/drug/event.json?limit=10",
    }
    base.update(kwargs)
    return base


def test_prepare_openfda_returns_raw_item():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert len(items) == 1
    assert isinstance(items[0], RawItem)


def test_prepare_openfda_source_is_openfda():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].source == "openfda"


def test_prepare_openfda_fact_type():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].fact_type == "health_knowledge"


def test_prepare_openfda_domain_is_health():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].domain == "health"


def test_prepare_openfda_quality_hint_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert items[0].quality_hint == pytest.approx(0.7)


def test_prepare_openfda_quality_hint_non_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert items[0].quality_hint == pytest.approx(0.5)


def test_prepare_openfda_content_serious_label():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert "serious" in items[0].content
    assert "non-serious" not in items[0].content


def test_prepare_openfda_content_non_serious_label():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert "non-serious" in items[0].content


def test_prepare_openfda_content_contains_drug_names():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(drug_names="IBUPROFEN")])
    assert "IBUPROFEN" in items[0].content


def test_prepare_openfda_content_contains_reactions():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(reactions="Dizziness")])
    assert "Dizziness" in items[0].content


def test_prepare_openfda_content_contains_receive_date():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(receive_date="20240115")])
    assert "20240115" in items[0].content


def test_prepare_openfda_source_url():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(source_url="https://api.fda.gov/test")])
    assert items[0].source_url == "https://api.fda.gov/test"


def test_prepare_openfda_structured_data_category():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].structured_data["category"] == "drug_interaction"


def test_prepare_openfda_structured_data_title():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(drug_names="WARFARIN")])
    assert items[0].structured_data["title"] == "Drug safety event: WARFARIN"


def test_prepare_openfda_structured_data_source():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].structured_data["source"] == "openfda"


def test_prepare_openfda_structured_data_evidence_level():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].structured_data["evidence_level"] == "case_report"


def test_prepare_openfda_structured_data_relevance_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert items[0].structured_data["relevance"] == pytest.approx(0.8)


def test_prepare_openfda_structured_data_relevance_non_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert items[0].structured_data["relevance"] == pytest.approx(0.5)


def test_prepare_openfda_structured_data_seasonal_is_0():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].structured_data["seasonal"] == 0


def test_prepare_openfda_structured_data_last_verified():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    lv = items[0].structured_data["last_verified"]
    assert len(lv) == 10


def test_prepare_openfda_tags_contain_health():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert "health" in items[0].tags


def test_prepare_openfda_tags_contain_fda():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert "fda" in items[0].tags


def test_prepare_openfda_tags_contain_drug_safety():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert "drug_safety" in items[0].tags


def test_prepare_openfda_tags_serious_label():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert "serious" in items[0].tags


def test_prepare_openfda_tags_non_serious_label():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert "non-serious" in items[0].tags


def test_prepare_openfda_structured_content_equals_item_content():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert items[0].structured_data["content"] == items[0].content


# ===========================================================================
# 9. prepare_items — mixed types
# ===========================================================================

def test_prepare_mixed_types_all_returned():
    eng = _new_engine()
    raw = [_airnow_raw(), _cdc_raw(), _openfda_raw()]
    items = eng.prepare_items(raw)
    assert len(items) == 3


def test_prepare_mixed_types_correct_sources():
    eng = _new_engine()
    raw = [_airnow_raw(), _cdc_raw(), _openfda_raw()]
    items = eng.prepare_items(raw)
    sources = {i.source for i in items}
    assert sources == {"airnow", "cdc", "openfda"}


def test_prepare_mixed_types_correct_fact_types():
    eng = _new_engine()
    raw = [_airnow_raw(), _cdc_raw(), _openfda_raw()]
    items = eng.prepare_items(raw)
    fact_types = {i.fact_type for i in items}
    assert "environmental_data" in fact_types
    assert "health_knowledge" in fact_types


def test_prepare_mixed_types_unknown_type_skipped():
    eng = _new_engine()
    raw = [
        {"type": "unknown_source", "data": "something"},
        _airnow_raw(),
    ]
    items = eng.prepare_items(raw)
    assert len(items) == 1
    assert items[0].source == "airnow"


def test_prepare_mixed_types_multiple_airnow():
    eng = _new_engine()
    raw = [
        _airnow_raw(pollutant="PM2.5", aqi=42),
        _airnow_raw(pollutant="Ozone", aqi=55),
    ]
    items = eng.prepare_items(raw)
    assert len(items) == 2
    metrics = {i.structured_data["metric"] for i in items}
    assert "AQI_PM2.5" in metrics
    assert "AQI_Ozone" in metrics


def test_prepare_mixed_types_multiple_cdc():
    eng = _new_engine()
    raw = [
        _cdc_raw(title="Flu Alert"),
        _cdc_raw(title="Vaccine Update"),
    ]
    items = eng.prepare_items(raw)
    assert len(items) == 2


def test_prepare_mixed_types_multiple_openfda():
    eng = _new_engine()
    raw = [
        _openfda_raw(drug_names="ASPIRIN", serious=1),
        _openfda_raw(drug_names="IBUPROFEN", serious=0),
    ]
    items = eng.prepare_items(raw)
    assert len(items) == 2


# ===========================================================================
# 10. prepare_items — empty list
# ===========================================================================

def test_prepare_empty_list_returns_empty():
    eng = _new_engine()
    items = eng.prepare_items([])
    assert items == []


def test_prepare_empty_list_type_is_list():
    eng = _new_engine()
    result = eng.prepare_items([])
    assert isinstance(result, list)


# ===========================================================================
# 11. improve() — no API key
# ===========================================================================

def test_improve_no_api_key_returns_gap():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", ""):
        gaps = eng.improve()

    assert isinstance(gaps, list)
    assert len(gaps) >= 1
    assert any("AirNow" in g or "airnow" in g.lower() or "API key" in g for g in gaps)


def test_improve_no_api_key_message_content():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", ""):
        gaps = eng.improve()

    assert any("AQI" in g or "key" in g.lower() for g in gaps)


def test_improve_with_api_key_no_aqi_gap():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "valid-key"):
        gaps = eng.improve()

    aqi_gaps = [g for g in gaps if "AirNow" in g or "API key" in g]
    assert aqi_gaps == []


# ===========================================================================
# 12. improve() — stale data
# ===========================================================================

def test_improve_stale_data_returns_gap():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = [
        {"id": 1, "fact_type": "environmental_data"},
        {"id": 2, "fact_type": "environmental_data"},
    ]
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "valid-key"):
        gaps = eng.improve()

    stale_gaps = [g for g in gaps if "tale" in g or "AQI" in g]
    assert len(stale_gaps) >= 1


def test_improve_stale_data_gap_mentions_count():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = [{"id": i} for i in range(3)]
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "valid-key"):
        gaps = eng.improve()

    stale_gaps = [g for g in gaps if "3" in g or "tale" in g.lower()]
    assert len(stale_gaps) >= 1


def test_improve_no_stale_data_no_stale_gap():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "valid-key"):
        gaps = eng.improve()

    stale_gaps = [g for g in gaps if "tale" in g.lower()]
    assert stale_gaps == []


def test_improve_engine_store_exception_does_not_crash():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.side_effect = Exception("DB error")
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "valid-key"):
        gaps = eng.improve()

    assert isinstance(gaps, list)


def test_improve_returns_list_type():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "key"):
        result = eng.improve()

    assert isinstance(result, list)


def test_improve_queries_engine_store_for_stale():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "key"):
        eng.improve()

    mock_store.query.assert_called_once()


def test_improve_query_uses_health_domain():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "key"):
        eng.improve()

    call_args = mock_store.query.call_args
    assert call_args[0][0] == "health"


def test_improve_query_uses_environmental_data():
    eng = _new_engine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    with patch("jarvis.config.AIRNOW_API_KEY", "key"):
        eng.improve()

    call_args = mock_store.query.call_args
    assert call_args[0][1] == "environmental_data"


# ===========================================================================
# 13. _classify_cdc_title — every branch
# ===========================================================================

# respiratory
def test_classify_flu_is_respiratory():
    assert _classify_cdc_title("Flu Season Update 2024") == "respiratory"


def test_classify_influenza_is_respiratory():
    assert _classify_cdc_title("Influenza Surveillance Weekly Report") == "respiratory"


def test_classify_cold_is_respiratory():
    assert _classify_cdc_title("Common Cold Prevention Tips") == "respiratory"


def test_classify_respiratory_keyword_is_respiratory():
    assert _classify_cdc_title("Respiratory Syncytial Virus Cases Rise") == "respiratory"


def test_classify_covid_is_respiratory():
    assert _classify_cdc_title("COVID-19 Variant Detected in US") == "respiratory"


def test_classify_flu_case_insensitive():
    assert _classify_cdc_title("FLU SEASON ALERT") == "respiratory"


def test_classify_influenza_mixed_case():
    assert _classify_cdc_title("Influenza A Subtype Spreading") == "respiratory"


# vaccination
def test_classify_vaccine_is_vaccination():
    assert _classify_cdc_title("New Vaccine Approved for Children") == "vaccination"


def test_classify_vaccination_keyword():
    assert _classify_cdc_title("Vaccination Rates Improve in 2024") == "vaccination"


def test_classify_immuniz_is_vaccination():
    assert _classify_cdc_title("Immunization Schedule Updated") == "vaccination"


def test_classify_immunization_full_word():
    assert _classify_cdc_title("Immunization Campaign Reaches Millions") == "vaccination"


# food_safety
def test_classify_food_is_food_safety():
    assert _classify_cdc_title("Food Safety Alert: Contaminated Products") == "food_safety"


def test_classify_outbreak_is_food_safety():
    assert _classify_cdc_title("Outbreak Investigation Under Way") == "food_safety"


def test_classify_salmonella_is_food_safety():
    assert _classify_cdc_title("Salmonella Linked to Chicken Products") == "food_safety"


def test_classify_e_coli_is_food_safety():
    assert _classify_cdc_title("E. coli Cases Reported in Three States") == "food_safety"


def test_classify_listeria_is_food_safety():
    assert _classify_cdc_title("Listeria Contamination Recall Issued") == "food_safety"


def test_classify_food_case_insensitive():
    assert _classify_cdc_title("FOOD SAFETY RECALL NOTICE") == "food_safety"


# chronic_disease
def test_classify_cancer_is_chronic_disease():
    assert _classify_cdc_title("Cancer Screening Recommendations Updated") == "chronic_disease"


def test_classify_tumor_is_chronic_disease():
    assert _classify_cdc_title("Tumor Registry Data Released") == "chronic_disease"


def test_classify_oncol_is_chronic_disease():
    assert _classify_cdc_title("Oncology Trial Results Published") == "chronic_disease"


def test_classify_cancer_case_insensitive():
    assert _classify_cdc_title("CANCER PREVENTION GUIDELINES") == "chronic_disease"


# mental_health
def test_classify_mental_is_mental_health():
    assert _classify_cdc_title("Mental Health Awareness Month Activities") == "mental_health"


def test_classify_depression_is_mental_health():
    assert _classify_cdc_title("Depression Screening Tools for Clinicians") == "mental_health"


def test_classify_anxiety_is_mental_health():
    assert _classify_cdc_title("Anxiety Disorders on the Rise") == "mental_health"


def test_classify_suicide_is_mental_health():
    assert _classify_cdc_title("Suicide Prevention Hotline Resources") == "mental_health"


def test_classify_mental_case_insensitive():
    assert _classify_cdc_title("MENTAL WELLNESS RESOURCES") == "mental_health"


# seasonal_health
def test_classify_allerg_is_seasonal_health():
    assert _classify_cdc_title("Allergy Season Starts Early This Year") == "seasonal_health"


def test_classify_allergies_full_word():
    assert _classify_cdc_title("Spring Allergies: Tips for Relief") == "seasonal_health"


def test_classify_pollen_is_seasonal_health():
    assert _classify_cdc_title("Pollen Levels Reach Record High") == "seasonal_health"


def test_classify_asthma_is_seasonal_health():
    assert _classify_cdc_title("Asthma Triggers During Wildfire Season") == "seasonal_health"


def test_classify_allerg_case_insensitive():
    assert _classify_cdc_title("ALLERGIC RHINITIS PREVENTION") == "seasonal_health"


# general_health
def test_classify_unknown_is_general_health():
    assert _classify_cdc_title("New Health Guidelines Released") == "general_health"


def test_classify_empty_string_is_general_health():
    assert _classify_cdc_title("") == "general_health"


def test_classify_unrelated_is_general_health():
    assert _classify_cdc_title("Annual Report Published by CDC") == "general_health"


def test_classify_diabetes_is_general_health():
    assert _classify_cdc_title("Diabetes Management Strategies") == "general_health"


def test_classify_opioid_is_general_health():
    assert _classify_cdc_title("Opioid Crisis Update 2024") == "general_health"


# priority ordering (first match wins)
def test_classify_flu_beats_vaccine_in_title():
    # "flu vaccine" — flu appears first in check order
    assert _classify_cdc_title("Flu Vaccine Campaign Launched") == "respiratory"


def test_classify_food_not_confused_with_general():
    assert _classify_cdc_title("Food Poisoning Outbreak Cases") == "food_safety"


# ===========================================================================
# 14. Edge cases
# ===========================================================================

def test_prepare_unicode_cdc_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Épidémie de grippe au Québec")])
    assert "Épidémie" in items[0].content


def test_prepare_unicode_airnow_location():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(location="São Paulo")])
    assert "São Paulo" in items[0].content


def test_prepare_airnow_zero_aqi():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=0)])
    assert items[0].structured_data["value"] == pytest.approx(0.0)


def test_prepare_airnow_very_high_aqi():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=500, category="Hazardous")])
    assert items[0].structured_data["value"] == pytest.approx(500.0)
    assert "Hazardous" in items[0].content


def test_prepare_cdc_empty_description():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(description="")])
    assert isinstance(items[0].content, str)
    assert len(items[0].content) > 0


def test_prepare_openfda_empty_reactions():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(reactions="")])
    assert isinstance(items[0].content, str)


def test_prepare_items_no_type_key_skipped():
    eng = _new_engine()
    items = eng.prepare_items([{"data": "something without type"}])
    assert items == []


def test_prepare_airnow_hour_23():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(hour_observed=23)])
    assert items[0].structured_data["measured_at"] == "2024-01-15T23:00:00+00:00"


def test_prepare_cdc_very_long_title():
    eng = _new_engine()
    long_title = "Flu " + "Update " * 50
    items = eng.prepare_items([_cdc_raw(title=long_title)])
    assert isinstance(items[0].content, str)


def test_prepare_openfda_very_long_drug_names():
    eng = _new_engine()
    long_drugs = ", ".join([f"DRUG{i}" for i in range(20)])
    items = eng.prepare_items([_openfda_raw(drug_names=long_drugs)])
    assert isinstance(items[0].content, str)


def test_prepare_cdc_special_chars_in_description():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(description="Alert: <b>danger</b> & 'quotes'")])
    assert isinstance(items[0].content, str)


def test_prepare_all_items_have_domain():
    eng = _new_engine()
    raw = [_airnow_raw(), _cdc_raw(), _openfda_raw()]
    items = eng.prepare_items(raw)
    for item in items:
        assert item.domain == "health"


def test_prepare_all_items_have_structured_data():
    eng = _new_engine()
    raw = [_airnow_raw(), _cdc_raw(), _openfda_raw()]
    items = eng.prepare_items(raw)
    for item in items:
        assert item.structured_data is not None
        assert isinstance(item.structured_data, dict)


# ===========================================================================
# 15. run_cycle integration
# ===========================================================================

def test_run_cycle_returns_cycle_report():
    from jarvis.memory_tiers.types import CycleReport
    eng = _new_engine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    assert isinstance(report, CycleReport)


def test_run_cycle_no_error_on_success():
    eng = _new_engine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    assert report.error is None


def test_run_cycle_calls_gather():
    eng = _new_engine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        eng.run_cycle()

    eng.gather.assert_called_once()


def test_run_cycle_calls_improve():
    eng = _new_engine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        eng.run_cycle()

    eng.improve.assert_called_once()


def test_run_cycle_ingest_called_when_items_exist():
    eng = _new_engine()
    dummy_item = RawItem(content="test", source="airnow", fact_type="environmental_data", domain="health")
    eng.gather = MagicMock(return_value=[_airnow_raw()])
    eng.prepare_items = MagicMock(return_value=[dummy_item])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=1)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    mock_ingest.ingest.assert_called_once()
    assert report.error is None


def test_run_cycle_ingest_not_called_when_no_items():
    eng = _new_engine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        eng.run_cycle()

    mock_ingest.ingest.assert_not_called()


def test_run_cycle_gathered_count():
    eng = _new_engine()
    eng.gather = MagicMock(return_value=[_airnow_raw(), _cdc_raw()])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])
    mock_ingest = MagicMock()
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    assert report.gathered == 2


# ===========================================================================
# 16. AQI category content string formatting
# ===========================================================================

def test_aqi_content_good_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=35, category="Good", location="City", pollutant="PM2.5", date_observed="2024-01-15")])
    assert "AQI 35 (Good)" in items[0].content


def test_aqi_content_moderate_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=75, category="Moderate", location="Metro", pollutant="PM2.5")])
    assert "AQI 75 (Moderate)" in items[0].content


def test_aqi_content_unhealthy_sensitive_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=115, category="Unhealthy for Sensitive Groups", location="City", pollutant="PM2.5")])
    assert "Unhealthy for Sensitive Groups" in items[0].content


def test_aqi_content_unhealthy_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=165, category="Unhealthy", location="City", pollutant="PM2.5")])
    assert "Unhealthy" in items[0].content


def test_aqi_content_very_unhealthy_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=225, category="Very Unhealthy", location="City", pollutant="PM2.5")])
    assert "Very Unhealthy" in items[0].content


def test_aqi_content_hazardous_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=305, category="Hazardous", location="City", pollutant="PM2.5")])
    assert "Hazardous" in items[0].content


def test_aqi_content_format_has_for_pollutant():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="PM2.5")])
    assert "for PM2.5" in items[0].content


def test_aqi_content_format_at_location():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(location="Denver")])
    assert "at Denver:" in items[0].content


def test_aqi_content_format_on_date():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(date_observed="2024-06-15")])
    assert "on 2024-06-15" in items[0].content


def test_aqi_content_ozone_pollutant_in_content():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(pollutant="Ozone", aqi=88)])
    assert "Ozone" in items[0].content
    assert "88" in items[0].content


def test_aqi_structured_forecast_matches_category():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(category="Moderate")])
    assert items[0].structured_data["forecast"] == "Moderate"


# ===========================================================================
# 17. Seasonal flag detection in prepare_items
# ===========================================================================

def test_seasonal_flu_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Flu Update")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_seasonal_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Seasonal Health Tips for Winter")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_winter_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Winter Storm Safety Guidelines")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_summer_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Summer Heat Wave Warning")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_pollen_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Pollen Count High Today")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_allerg_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Allergy Relief Strategies")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_influenza_keyword_in_title():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Influenza A Activity")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_non_matching_title_is_zero():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="General Health Reminder")])
    assert items[0].structured_data["seasonal"] == 0


def test_seasonal_cancer_title_is_zero():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Cancer Screening Guidelines")])
    assert items[0].structured_data["seasonal"] == 0


def test_seasonal_food_safety_title_is_zero():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Salmonella Outbreak Investigation")])
    assert items[0].structured_data["seasonal"] == 0


def test_seasonal_flu_mixed_case():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="FLU SEASON BEGINS")])
    assert items[0].structured_data["seasonal"] == 1


def test_seasonal_influenza_partial_match():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw(title="Influenza Surveillance")])
    assert items[0].structured_data["seasonal"] == 1


# ===========================================================================
# 18. Multiple AQI readings (PM2.5, ozone) in one gather
# ===========================================================================

def test_gather_two_pollutants_returned():
    eng = _new_engine()
    obs = [
        {"AQI": 42, "Category": {"Name": "Good"}, "ParameterName": "PM2.5", "ReportingArea": "City", "DateObserved": "2024-01-15", "HourObserved": 8},
        {"AQI": 55, "Category": {"Name": "Moderate"}, "ParameterName": "Ozone", "ReportingArea": "City", "DateObserved": "2024-01-15", "HourObserved": 8},
    ]
    resp = _make_urlopen_mock(json.dumps(obs).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_airnow_aqi("key", "55401")
    assert len(result) == 2
    pollutants = {r["pollutant"] for r in result}
    assert "PM2.5" in pollutants
    assert "Ozone" in pollutants


def test_two_pollutant_prepare_items_two_metrics():
    eng = _new_engine()
    raw = [
        _airnow_raw(pollutant="PM2.5", aqi=42),
        _airnow_raw(pollutant="Ozone", aqi=55),
    ]
    items = eng.prepare_items(raw)
    metrics = {i.structured_data["metric"] for i in items}
    assert "AQI_PM2.5" in metrics
    assert "AQI_Ozone" in metrics


def test_two_pollutant_different_quality_hints():
    eng = _new_engine()
    raw = [
        _airnow_raw(pollutant="PM2.5"),
        _airnow_raw(pollutant="Ozone"),
    ]
    items = eng.prepare_items(raw)
    for item in items:
        assert item.quality_hint == pytest.approx(0.8)


def test_two_pollutant_both_environmental_data():
    eng = _new_engine()
    raw = [
        _airnow_raw(pollutant="PM2.5"),
        _airnow_raw(pollutant="Ozone"),
    ]
    items = eng.prepare_items(raw)
    for item in items:
        assert item.fact_type == "environmental_data"


def test_two_pollutant_tags_differ():
    eng = _new_engine()
    raw = [
        _airnow_raw(pollutant="PM2.5"),
        _airnow_raw(pollutant="Ozone"),
    ]
    items = eng.prepare_items(raw)
    tags_set = {i.tags for i in items}
    assert len(tags_set) == 2


# ===========================================================================
# 19. CDC RSS with no items
# ===========================================================================

def test_cdc_rss_no_items_empty_channel():
    eng = _new_engine()
    xml = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>CDC</title>
  </channel>
</rss>"""
    resp = _make_urlopen_mock(xml)
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert [r for r in result if r.get("type") == "cdc_rss"] == []


def test_cdc_rss_no_items_prepare_returns_empty():
    eng = _new_engine()
    items = eng.prepare_items([])
    assert items == []


def test_cdc_atom_no_entries():
    eng = _new_engine()
    xml = b"""<?xml version="1.0"?>
<atom:feed xmlns:atom="http://www.w3.org/2005/Atom">
  <atom:title>Empty Feed</atom:title>
</atom:feed>"""
    resp = _make_urlopen_mock(xml)
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_cdc_rss()
    assert [r for r in result if r.get("type") == "cdc_rss"] == []


# ===========================================================================
# 20. OpenFDA serious=1 vs serious=0 quality_hint difference
# ===========================================================================

def test_openfda_serious_1_quality_hint_is_07():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert items[0].quality_hint == pytest.approx(0.7)


def test_openfda_serious_0_quality_hint_is_05():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert items[0].quality_hint == pytest.approx(0.5)


def test_openfda_serious_1_relevance_is_08():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert items[0].structured_data["relevance"] == pytest.approx(0.8)


def test_openfda_serious_0_relevance_is_05():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert items[0].structured_data["relevance"] == pytest.approx(0.5)


def test_openfda_serious_1_content_says_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    assert "(serious)" in items[0].content


def test_openfda_serious_0_content_says_non_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert "(non-serious)" in items[0].content


def test_openfda_serious_1_tags_include_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=1)])
    tag_list = items[0].tags.split(",")
    assert "serious" in tag_list


def test_openfda_serious_0_tags_include_non_serious():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(serious=0)])
    assert "non-serious" in items[0].tags


def test_openfda_mixed_serious_different_quality():
    eng = _new_engine()
    raw = [_openfda_raw(serious=1), _openfda_raw(serious=0)]
    items = eng.prepare_items(raw)
    hints = [i.quality_hint for i in items]
    assert pytest.approx(0.7) in hints
    assert pytest.approx(0.5) in hints


# ===========================================================================
# Additional edge case: engine attributes
# ===========================================================================

def test_health_engine_name():
    eng = _new_engine()
    assert eng.name == "health_engine"


def test_health_engine_domain():
    eng = _new_engine()
    assert eng.domain == "health"


def test_health_engine_schedule():
    eng = _new_engine()
    assert eng.schedule == "0 7,19 * * *"


def test_health_engine_has_gather():
    eng = _new_engine()
    assert callable(eng.gather)


def test_health_engine_has_prepare_items():
    eng = _new_engine()
    assert callable(eng.prepare_items)


def test_health_engine_has_improve():
    eng = _new_engine()
    assert callable(eng.improve)


def test_health_engine_has_run_cycle():
    eng = _new_engine()
    assert callable(eng.run_cycle)


# ===========================================================================
# Additional: gather() source ordering and isolation
# ===========================================================================

def test_gather_airnow_items_have_type_airnow():
    eng = _new_engine()
    airnow_resp = _make_urlopen_mock(_make_airnow_response())
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "airnowapi" in url:
            return airnow_resp
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", "key"), \
         patch("jarvis.config.HOME_ZIP_CODE", "55401"), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    for item in result:
        assert item.get("type") in ("airnow", "cdc_rss", "openfda")


def test_gather_cdc_items_have_type_cdc_rss():
    eng = _new_engine()
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", ""), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    cdc_items = [r for r in result if r.get("type") == "cdc_rss"]
    assert len(cdc_items) >= 1


def test_gather_openfda_items_have_type_openfda():
    eng = _new_engine()
    cdc_resp = _make_urlopen_mock(_make_rss2_response())
    openfda_resp = _make_urlopen_mock(_make_openfda_response())

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "cdc.gov" in url or "tools.cdc.gov" in url:
            return cdc_resp
        return openfda_resp

    with patch("jarvis.config.AIRNOW_API_KEY", ""), \
         patch("urllib.request.urlopen", side_effect=side_effect):
        result = eng.gather()

    openfda_items = [r for r in result if r.get("type") == "openfda"]
    assert len(openfda_items) >= 1


# ===========================================================================
# Additional: _fetch_openfda_events caps at 10 results
# ===========================================================================

def test_fetch_openfda_max_10_results():
    eng = _new_engine()
    events = [
        {
            "serious": 0,
            "receivedate": f"2024010{i}",
            "patient": {
                "drug": [{"medicinalproduct": f"DRUG{i}"}],
                "reaction": [{"reactionmeddrapt": "Headache"}],
            },
        }
        for i in range(15)
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert len(result) <= 10


def test_fetch_openfda_source_url_constant():
    eng = _new_engine()
    resp = _make_urlopen_mock(_make_openfda_response())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert result[0]["source_url"] == "https://api.fda.gov/drug/event.json?limit=10&sort=receivedate:desc"


# ===========================================================================
# Additional: prepare_items structured_data source_url for openfda
# ===========================================================================

def test_prepare_openfda_structured_data_source_url():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw(source_url="https://api.fda.gov/test")])
    assert items[0].structured_data["source_url"] == "https://api.fda.gov/test"


def test_prepare_openfda_structured_data_source_url_default_empty():
    eng = _new_engine()
    raw = {
        "type": "openfda",
        "drug_names": "ASPIRIN",
        "reactions": "Nausea",
        "serious": 0,
        "receive_date": "20240115",
    }
    items = eng.prepare_items([raw])
    assert items[0].structured_data.get("source_url", "") == ""


# ===========================================================================
# Additional: _fetch_airnow_aqi URL construction
# ===========================================================================

def test_fetch_airnow_url_contains_api_key():
    eng = _new_engine()
    captured_urls = []

    class CapturingMock:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b"[]"

    def side_effect(req, timeout=15):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return CapturingMock()

    with patch("urllib.request.urlopen", side_effect=side_effect):
        eng._fetch_airnow_aqi("MY_SECRET_KEY", "55401")

    assert any("MY_SECRET_KEY" in u for u in captured_urls)


def test_fetch_airnow_url_contains_zip():
    eng = _new_engine()
    captured_urls = []

    class CapturingMock:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return b"[]"

    def side_effect(req, timeout=15):
        captured_urls.append(req.full_url if hasattr(req, "full_url") else str(req))
        return CapturingMock()

    with patch("urllib.request.urlopen", side_effect=side_effect):
        eng._fetch_airnow_aqi("key", "90210")

    assert any("90210" in u for u in captured_urls)


# ===========================================================================
# Additional: classify boundary conditions
# ===========================================================================

def test_classify_title_with_only_spaces():
    result = _classify_cdc_title("   ")
    assert result == "general_health"


def test_classify_title_numbers_only():
    result = _classify_cdc_title("12345 67890")
    assert result == "general_health"


def test_classify_title_with_covid_uppercase():
    result = _classify_cdc_title("COVID VARIANT SURGE")
    assert result == "respiratory"


def test_classify_title_asthma_is_seasonal_not_respiratory():
    # asthma is in seasonal_health check, not respiratory
    result = _classify_cdc_title("Asthma Rates Increasing")
    assert result == "seasonal_health"


def test_classify_title_cold_is_respiratory():
    result = _classify_cdc_title("Cold Weather Health Risks")
    assert result == "respiratory"


def test_classify_title_depression_case_variations():
    result = _classify_cdc_title("DEPRESSION IN TEENAGERS RISING")
    assert result == "mental_health"


def test_classify_title_e_coli_with_period():
    result = _classify_cdc_title("E. coli O157 Outbreak Linked to Lettuce")
    assert result == "food_safety"


def test_classify_title_tumor_partial():
    result = _classify_cdc_title("Tumor Marker Research Published")
    assert result == "chronic_disease"


# ===========================================================================
# Additional: prepare_items airnow hour zero-padding
# ===========================================================================

def test_prepare_airnow_hour_1_zero_padded():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(hour_observed=1)])
    assert "T01:00:00" in items[0].structured_data["measured_at"]


def test_prepare_airnow_hour_12():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(hour_observed=12)])
    assert "T12:00:00" in items[0].structured_data["measured_at"]


def test_prepare_airnow_hour_9_zero_padded():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(hour_observed=9)])
    assert "T09:00:00" in items[0].structured_data["measured_at"]


# ===========================================================================
# Additional: multiple CDC feeds both attempted
# ===========================================================================

def test_cdc_rss_fetches_two_feed_urls():
    eng = _new_engine()
    urls_called = []

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        urls_called.append(url)
        return _make_urlopen_mock(_make_rss2_response())

    with patch("urllib.request.urlopen", side_effect=side_effect):
        eng._fetch_cdc_rss()

    assert len(urls_called) == 2


def test_cdc_rss_first_feed_url_is_tools_cdc():
    eng = _new_engine()
    urls_called = []

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        urls_called.append(url)
        return _make_urlopen_mock(_make_rss2_response())

    with patch("urllib.request.urlopen", side_effect=side_effect):
        eng._fetch_cdc_rss()

    assert "tools.cdc.gov" in urls_called[0]


def test_cdc_rss_second_feed_url_is_www_cdc():
    eng = _new_engine()
    urls_called = []

    def side_effect(req, timeout=15):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        urls_called.append(url)
        return _make_urlopen_mock(_make_rss2_response())

    with patch("urllib.request.urlopen", side_effect=side_effect):
        eng._fetch_cdc_rss()

    assert "www.cdc.gov" in urls_called[1]


# ===========================================================================
# Additional: openfda reactions capped at 3
# ===========================================================================

def test_fetch_openfda_reactions_capped_at_3():
    eng = _new_engine()
    events = [
        {
            "serious": 0,
            "receivedate": "20240115",
            "patient": {
                "drug": [{"medicinalproduct": "ASPIRIN"}],
                "reaction": [
                    {"reactionmeddrapt": "Nausea"},
                    {"reactionmeddrapt": "Vomiting"},
                    {"reactionmeddrapt": "Dizziness"},
                    {"reactionmeddrapt": "Headache"},
                    {"reactionmeddrapt": "Rash"},
                ],
            },
        }
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    # Only first 3 reactions should appear
    assert "Headache" not in result[0]["reactions"]
    assert "Rash" not in result[0]["reactions"]


def test_fetch_openfda_reactions_first_three_present():
    eng = _new_engine()
    events = [
        {
            "serious": 0,
            "receivedate": "20240115",
            "patient": {
                "drug": [{"medicinalproduct": "ASPIRIN"}],
                "reaction": [
                    {"reactionmeddrapt": "Nausea"},
                    {"reactionmeddrapt": "Vomiting"},
                    {"reactionmeddrapt": "Dizziness"},
                    {"reactionmeddrapt": "Headache"},
                ],
            },
        }
    ]
    resp = _make_urlopen_mock(json.dumps({"results": events}).encode())
    with patch("urllib.request.urlopen", return_value=resp):
        result = eng._fetch_openfda_events()
    assert "Nausea" in result[0]["reactions"]
    assert "Vomiting" in result[0]["reactions"]
    assert "Dizziness" in result[0]["reactions"]


# ===========================================================================
# Additional: prepare_items all RawItem fields are correct types
# ===========================================================================

def test_prepare_airnow_content_is_str():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert isinstance(items[0].content, str)


def test_prepare_cdc_content_is_str():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert isinstance(items[0].content, str)


def test_prepare_openfda_content_is_str():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert isinstance(items[0].content, str)


def test_prepare_airnow_quality_hint_is_float():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert isinstance(items[0].quality_hint, float)


def test_prepare_cdc_quality_hint_is_float():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert isinstance(items[0].quality_hint, float)


def test_prepare_openfda_quality_hint_is_float():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert isinstance(items[0].quality_hint, float)


def test_prepare_airnow_structured_data_value_is_float():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw(aqi=42)])
    assert isinstance(items[0].structured_data["value"], float)


def test_prepare_airnow_tags_is_str():
    eng = _new_engine()
    items = eng.prepare_items([_airnow_raw()])
    assert isinstance(items[0].tags, str)


def test_prepare_cdc_tags_is_str():
    eng = _new_engine()
    items = eng.prepare_items([_cdc_raw()])
    assert isinstance(items[0].tags, str)


def test_prepare_openfda_tags_is_str():
    eng = _new_engine()
    items = eng.prepare_items([_openfda_raw()])
    assert isinstance(items[0].tags, str)
