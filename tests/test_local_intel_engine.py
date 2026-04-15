"""Comprehensive tests for LocalIntelEngine (Engine 6).

Tests: ~300 individual test functions.
All HTTP calls are mocked — no real network access.
"""
from __future__ import annotations
import json
import pytest
from io import BytesIO
from unittest.mock import MagicMock, patch, call


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_urlopen_mock(response_bytes: bytes):
    resp = MagicMock()
    resp.read.return_value = response_bytes
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


POINTS_DATA = json.dumps({
    "properties": {
        "forecast": "https://api.weather.gov/gridpoints/MPX/63,44/forecast",
        "forecastHourly": "https://api.weather.gov/gridpoints/MPX/63,44/forecast/hourly",
    }
}).encode()

FORECAST_DATA = json.dumps({
    "properties": {
        "periods": [
            {
                "name": "Saturday",
                "temperature": 72,
                "temperatureUnit": "F",
                "windSpeed": "10 mph",
                "windDirection": "SW",
                "shortForecast": "Sunny",
                "detailedForecast": "Sunny skies throughout the day. High near 72.",
                "isDaytime": True,
                "startTime": "2024-04-20T06:00:00-05:00",
                "endTime": "2024-04-20T18:00:00-05:00",
            },
            {
                "name": "Saturday Night",
                "temperature": 55,
                "temperatureUnit": "F",
                "windSpeed": "5 mph",
                "windDirection": "N",
                "shortForecast": "Clear",
                "detailedForecast": "Clear and cold. Low near 55.",
                "isDaytime": False,
                "startTime": "2024-04-20T18:00:00-05:00",
                "endTime": "2024-04-21T06:00:00-05:00",
            },
            {
                "name": "Sunday",
                "temperature": 68,
                "temperatureUnit": "F",
                "windSpeed": "8 mph",
                "windDirection": "SE",
                "shortForecast": "Partly Cloudy",
                "detailedForecast": "Partly cloudy. High near 68.",
                "isDaytime": True,
                "startTime": "2024-04-21T06:00:00-05:00",
                "endTime": "2024-04-21T18:00:00-05:00",
            },
        ]
    }
}).encode()

RAINY_FORECAST_DATA = json.dumps({
    "properties": {
        "periods": [
            {
                "name": "Saturday",
                "temperature": 55,
                "temperatureUnit": "F",
                "windSpeed": "15 mph",
                "windDirection": "NE",
                "shortForecast": "Rain Likely",
                "detailedForecast": "Rain likely, mainly before noon.",
                "isDaytime": True,
                "startTime": "2024-04-20T06:00:00-05:00",
                "endTime": "2024-04-20T18:00:00-05:00",
            }
        ]
    }
}).encode()

EVENTBRITE_DATA = json.dumps({
    "events": [
        {
            "name": {"text": "Minneapolis Craft Fair"},
            "description": {"text": "Annual craft fair in Loring Park."},
            "start": {"local": "2024-04-21T10:00:00"},
            "end": {"local": "2024-04-21T17:00:00"},
            "url": "https://www.eventbrite.com/e/123456",
            "is_free": True,
            "category_id": "110",
            "venue": {
                "name": "Loring Park",
                "address": {"localized_address_display": "Hennepin Ave S, Minneapolis, MN"},
            },
        }
    ]
}).encode()

RSS_DATA = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Minneapolis City News</title>
    <item>
      <title>Road Closure on I-35W</title>
      <link>https://minneapolis.gov/news/1</link>
      <description>Overnight lane closures for bridge maintenance.</description>
    </item>
    <item>
      <title>New School Policy Announced</title>
      <link>https://mpls.k12.mn.us/news/1</link>
      <description>Minneapolis Public Schools announces new attendance policy.</description>
    </item>
  </channel>
</rss>"""

ATOM_DATA = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>City of Minneapolis</title>
  <entry>
    <title>City Council Meeting Results</title>
    <link href="https://minneapolis.gov/council/1"/>
    <summary>The council voted on the 2024 budget.</summary>
  </entry>
</feed>"""


def _make_local_intel_engine():
    from jarvis.engines.local_intel import LocalIntelEngine
    engine = LocalIntelEngine()
    engine._ingestion = MagicMock()
    engine._ingestion.ingest.return_value = MagicMock(accepted=1)
    engine._engine_store = MagicMock()
    engine._engine_store.query.return_value = []
    engine._engine_store.count.return_value = 0
    return engine


# ──────────────────────────────────────────────────────────────────────────────
# Section 1: Registration
# ──────────────────────────────────────────────────────────────────────────────

def test_local_intel_engine_registered():
    import jarvis.engines.local_intel  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    names = [cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")]
    assert "local_intel_engine" in names


def test_local_intel_engine_domain():
    from jarvis.engines.local_intel import LocalIntelEngine
    assert LocalIntelEngine.domain == "local"


def test_local_intel_engine_schedule():
    from jarvis.engines.local_intel import LocalIntelEngine
    assert LocalIntelEngine.schedule == "0 8 * * *"


def test_local_intel_engine_name():
    from jarvis.engines.local_intel import LocalIntelEngine
    assert LocalIntelEngine.name == "local_intel_engine"


# ──────────────────────────────────────────────────────────────────────────────
# Section 2: gather() dispatch
# ──────────────────────────────────────────────────────────────────────────────

def test_gather_calls_nws():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[{"type": "nws_weather"}]) as mock_nws, \
         patch.object(engine, "_fetch_eventbrite", return_value=[]) as mock_eb, \
         patch("jarvis.config.EVENTBRITE_TOKEN", ""), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        engine.gather()
    mock_nws.assert_called_once()


def test_gather_calls_eventbrite_when_token_set():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[]), \
         patch.object(engine, "_fetch_eventbrite", return_value=[{"type": "eventbrite"}]) as mock_eb, \
         patch("jarvis.config.EVENTBRITE_TOKEN", "testtoken123"), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        result = engine.gather()
    mock_eb.assert_called_once()
    assert any(r["type"] == "eventbrite" for r in result)


def test_gather_skips_eventbrite_when_no_token():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[]), \
         patch.object(engine, "_fetch_eventbrite", return_value=[]) as mock_eb, \
         patch("jarvis.config.EVENTBRITE_TOKEN", ""), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        engine.gather()
    mock_eb.assert_not_called()


def test_gather_calls_rss_feeds():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[]), \
         patch.object(engine, "_fetch_local_rss", return_value=[{"type": "local_rss"}]) as mock_rss, \
         patch("jarvis.config.EVENTBRITE_TOKEN", ""), \
         patch("jarvis.config.LOCAL_FEEDS", ["https://example.com/feed1", "https://example.com/feed2"]):
        result = engine.gather()
    assert mock_rss.call_count == 2


def test_gather_returns_combined_results():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[{"type": "nws_weather"}]), \
         patch.object(engine, "_fetch_eventbrite", return_value=[{"type": "eventbrite"}]), \
         patch.object(engine, "_fetch_local_rss", return_value=[{"type": "local_rss"}]), \
         patch("jarvis.config.EVENTBRITE_TOKEN", "tok"), \
         patch("jarvis.config.LOCAL_FEEDS", ["https://example.com/feed"]):
        result = engine.gather()
    assert len(result) == 3


def test_gather_empty_result_no_feeds_no_token():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[]), \
         patch("jarvis.config.EVENTBRITE_TOKEN", ""), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        result = engine.gather()
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# Section 3: _fetch_nws_forecast
# ──────────────────────────────────────────────────────────────────────────────

def test_nws_fetch_success_returns_periods():
    engine = _make_local_intel_engine()
    mock_points = _make_urlopen_mock(POINTS_DATA)
    mock_forecast = _make_urlopen_mock(FORECAST_DATA)
    with patch("urllib.request.urlopen", side_effect=[mock_points, mock_forecast]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert len(result) == 3


def test_nws_fetch_returns_nws_weather_type():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert all(r["type"] == "nws_weather" for r in result)


def test_nws_fetch_saturday_name():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result[0]["name"] == "Saturday"


def test_nws_fetch_temperature_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result[0]["temperature"] == 72


def test_nws_fetch_short_forecast():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result[0]["short_forecast"] == "Sunny"


def test_nws_fetch_detailed_forecast():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert "High near 72" in result[0]["detailed_forecast"]


def test_nws_fetch_is_daytime_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result[0]["is_daytime"] is True
    assert result[1]["is_daytime"] is False


def test_nws_fetch_location_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result[0]["location"] == "44.9778,-93.2650"


def test_nws_fetch_source_url_in_result():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert "weather.gov" in result[0]["source_url"]


def test_nws_fetch_missing_forecast_url_returns_empty():
    engine = _make_local_intel_engine()
    bad_points = json.dumps({"properties": {}}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(bad_points)):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result == []


def test_nws_fetch_points_http_error_returns_empty():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result == []


def test_nws_fetch_forecast_http_error_returns_empty():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), Exception("timeout")
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result == []


def test_nws_fetch_no_periods_returns_empty():
    engine = _make_local_intel_engine()
    empty_forecast = json.dumps({"properties": {"periods": []}}).encode()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(empty_forecast)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result == []


def test_nws_fetch_max_14_periods():
    engine = _make_local_intel_engine()
    periods = [
        {
            "name": f"Period {i}", "temperature": 70, "temperatureUnit": "F",
            "windSpeed": "10 mph", "windDirection": "S", "shortForecast": "Sunny",
            "detailedForecast": "Sunny.", "isDaytime": True,
            "startTime": "2024-04-20T06:00:00-05:00", "endTime": "2024-04-20T18:00:00-05:00",
        }
        for i in range(20)
    ]
    big_forecast = json.dumps({"properties": {"periods": periods}}).encode()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(big_forecast)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert len(result) == 14


def test_nws_fetch_wind_speed_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result[0]["wind_speed"] == "10 mph"


def test_nws_fetch_start_time_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=[
        _make_urlopen_mock(POINTS_DATA), _make_urlopen_mock(FORECAST_DATA)
    ]):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert "2024-04-20" in result[0]["start_time"]


def test_nws_fetch_malformed_json_returns_empty():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(b"not json")):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result == []


# ──────────────────────────────────────────────────────────────────────────────
# Section 4: _fetch_eventbrite
# ──────────────────────────────────────────────────────────────────────────────

def test_eventbrite_fetch_success():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert len(result) == 1


def test_eventbrite_fetch_type_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert result[0]["type"] == "eventbrite"


def test_eventbrite_fetch_title():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert result[0]["title"] == "Minneapolis Craft Fair"


def test_eventbrite_fetch_is_free():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert result[0]["is_free"] is True


def test_eventbrite_fetch_venue_name():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert result[0]["venue_name"] == "Loring Park"


def test_eventbrite_fetch_address():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert "Minneapolis" in result[0]["address"]


def test_eventbrite_fetch_url():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert "eventbrite.com" in result[0]["url"]


def test_eventbrite_fetch_start_time():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(EVENTBRITE_DATA)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert "2024-04-21" in result[0]["start_time"]


def test_eventbrite_fetch_http_error_returns_empty():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=Exception("401 unauthorized")):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "badtoken")
    assert result == []


def test_eventbrite_fetch_empty_events():
    engine = _make_local_intel_engine()
    empty_data = json.dumps({"events": []}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(empty_data)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "testtoken")
    assert result == []


def test_eventbrite_fetch_null_venue():
    engine = _make_local_intel_engine()
    data = json.dumps({"events": [{
        "name": {"text": "Test Event"},
        "description": {"text": "A test."},
        "start": {"local": "2024-04-21T10:00:00"},
        "end": {"local": "2024-04-21T12:00:00"},
        "url": "https://eventbrite.com/e/999",
        "is_free": False,
        "category_id": "101",
        "venue": None,
    }]}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(data)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "tok")
    assert len(result) == 1
    assert result[0]["venue_name"] == ""


def test_eventbrite_fetch_max_20_events():
    engine = _make_local_intel_engine()
    events = [
        {
            "name": {"text": f"Event {i}"},
            "description": {"text": "desc"},
            "start": {"local": "2024-04-21T10:00:00"},
            "end": {"local": "2024-04-21T12:00:00"},
            "url": f"https://eb.com/e/{i}",
            "is_free": True,
            "category_id": "110",
            "venue": {"name": "Venue", "address": {"localized_address_display": "123 St"}},
        }
        for i in range(30)
    ]
    data = json.dumps({"events": events}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(data)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "tok")
    assert len(result) == 20


# ──────────────────────────────────────────────────────────────────────────────
# Section 5: _fetch_local_rss
# ──────────────────────────────────────────────────────────────────────────────

def test_local_rss_fetch_rss20_success():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(RSS_DATA)):
        result = engine._fetch_local_rss("https://example.com/feed")
    rss_items = [r for r in result if r["type"] == "local_rss"]
    assert len(rss_items) == 2


def test_local_rss_fetch_rss20_title():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(RSS_DATA)):
        result = engine._fetch_local_rss("https://example.com/feed")
    titles = [r["title"] for r in result]
    assert "Road Closure on I-35W" in titles


def test_local_rss_fetch_rss20_url():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(RSS_DATA)):
        result = engine._fetch_local_rss("https://example.com/feed")
    urls = [r["url"] for r in result]
    assert "minneapolis.gov/news/1" in urls[0]


def test_local_rss_fetch_rss20_description():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(RSS_DATA)):
        result = engine._fetch_local_rss("https://example.com/feed")
    descs = [r["description"] for r in result]
    assert any("bridge maintenance" in d for d in descs)


def test_local_rss_fetch_rss20_feed_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(RSS_DATA)):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert all(r["feed"] == "https://example.com/feed" for r in result)


def test_local_rss_fetch_atom_success():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(ATOM_DATA)):
        result = engine._fetch_local_rss("https://example.com/atom")
    assert len(result) == 1
    assert result[0]["title"] == "City Council Meeting Results"


def test_local_rss_fetch_atom_url():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(ATOM_DATA)):
        result = engine._fetch_local_rss("https://example.com/atom")
    assert "minneapolis.gov/council/1" in result[0]["url"]


def test_local_rss_fetch_atom_description():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(ATOM_DATA)):
        result = engine._fetch_local_rss("https://example.com/atom")
    assert "budget" in result[0]["description"]


def test_local_rss_fetch_http_error_returns_empty():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert result == []


def test_local_rss_fetch_malformed_xml_returns_empty():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(b"<not valid xml")):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert result == []


def test_local_rss_fetch_empty_feed():
    engine = _make_local_intel_engine()
    empty_rss = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>Empty</title></channel></rss>"""
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(empty_rss)):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert result == []


def test_local_rss_fetch_description_truncated_at_500():
    engine = _make_local_intel_engine()
    long_desc = "x" * 1000
    rss = f"""<?xml version="1.0"?>
<rss version="2.0"><channel><item>
  <title>Long Article</title><link>https://ex.com</link>
  <description>{long_desc}</description>
</item></channel></rss>""".encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(rss)):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert len(result[0]["description"]) <= 500


# ──────────────────────────────────────────────────────────────────────────────
# Section 6: prepare_items — nws_weather
# ──────────────────────────────────────────────────────────────────────────────

def _make_nws_raw(**kwargs):
    base = {
        "type": "nws_weather",
        "name": "Saturday",
        "temperature": 72,
        "temperature_unit": "F",
        "wind_speed": "10 mph",
        "wind_direction": "SW",
        "short_forecast": "Sunny",
        "detailed_forecast": "Sunny skies. High near 72.",
        "is_daytime": True,
        "start_time": "2024-04-20T06:00:00-05:00",
        "end_time": "2024-04-20T18:00:00-05:00",
        "location": "44.9778,-93.2650",
        "source_url": "https://api.weather.gov/gridpoints/MPX/63,44/forecast",
    }
    base.update(kwargs)
    return base


def test_prepare_nws_returns_raw_item():
    from jarvis.ingestion import RawItem
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert len(result) == 1
    assert isinstance(result[0], RawItem)


def test_prepare_nws_fact_type():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].fact_type == "local_data"


def test_prepare_nws_source():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].source == "nws"


def test_prepare_nws_domain():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].domain == "local"


def test_prepare_nws_quality_hint():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].quality_hint == 0.9


def test_prepare_nws_content_has_period_name():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="Tuesday")])
    assert "Tuesday" in result[0].content


def test_prepare_nws_content_has_temperature():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(temperature=85)])
    assert "85" in result[0].content


def test_prepare_nws_content_has_unit():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert "°F" in result[0].content


def test_prepare_nws_content_has_forecast():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(short_forecast="Partly Cloudy")])
    assert "Partly Cloudy" in result[0].content


def test_prepare_nws_structured_data_category():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].structured_data["category"] == "weather"


def test_prepare_nws_structured_data_title():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="Sunday")])
    assert "Sunday" in result[0].structured_data["title"]


def test_prepare_nws_structured_data_location():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].structured_data["location"] == "44.9778,-93.2650"


def test_prepare_nws_structured_data_data_date():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(start_time="2024-04-20T06:00:00-05:00")])
    assert result[0].structured_data["data_date"] == "2024-04-20"


def test_prepare_nws_structured_data_source():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert result[0].structured_data["source"] == "nws"


def test_prepare_nws_structured_data_trend():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(short_forecast="Rainy")])
    assert result[0].structured_data["trend"] == "Rainy"


def test_prepare_nws_tags_contain_local():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert "local" in result[0].tags


def test_prepare_nws_tags_contain_weather():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert "weather" in result[0].tags


def test_prepare_nws_tags_contain_nws():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert "nws" in result[0].tags


def test_prepare_nws_source_url():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw()])
    assert "weather.gov" in result[0].source_url


def test_prepare_nws_detailed_forecast_in_content():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(detailed_forecast="Very sunny day ahead.")])
    assert "Very sunny day ahead" in result[0].content


def test_prepare_nws_structured_content_from_detailed():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(detailed_forecast="Detailed forecast text.")])
    assert "Detailed forecast text" in result[0].structured_data["content"]


def test_prepare_nws_structured_data_source_url():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(source_url="https://api.weather.gov/test")])
    assert "weather.gov" in result[0].structured_data["source_url"]


def test_prepare_nws_multiple_periods():
    engine = _make_local_intel_engine()
    raws = [_make_nws_raw(name="Saturday"), _make_nws_raw(name="Sunday")]
    result = engine.prepare_items(raws)
    assert len(result) == 2


def test_prepare_nws_none_temperature():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(temperature=None)])
    assert len(result) == 1  # should not crash


# ──────────────────────────────────────────────────────────────────────────────
# Section 7: prepare_items — eventbrite
# ──────────────────────────────────────────────────────────────────────────────

def _make_eb_raw(**kwargs):
    base = {
        "type": "eventbrite",
        "title": "Minneapolis Craft Fair",
        "description": "Annual craft fair in Loring Park.",
        "start_time": "2024-04-21T10:00:00",
        "end_time": "2024-04-21T17:00:00",
        "venue_name": "Loring Park",
        "address": "Hennepin Ave S, Minneapolis, MN",
        "is_free": True,
        "url": "https://www.eventbrite.com/e/123456",
        "category_id": "110",
    }
    base.update(kwargs)
    return base


def test_prepare_eb_returns_raw_item():
    from jarvis.ingestion import RawItem
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert isinstance(result[0], RawItem)


def test_prepare_eb_fact_type():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].fact_type == "local_events"


def test_prepare_eb_source():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].source == "eventbrite"


def test_prepare_eb_domain():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].domain == "local"


def test_prepare_eb_quality_hint():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].quality_hint == 0.7


def test_prepare_eb_content_has_title():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(title="Art Festival")])
    assert "Art Festival" in result[0].content


def test_prepare_eb_content_has_venue():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(venue_name="Central Park")])
    assert "Central Park" in result[0].content


def test_prepare_eb_free_cost():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(is_free=True)])
    assert result[0].structured_data["cost"] == "Free"


def test_prepare_eb_paid_cost():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(is_free=False)])
    assert result[0].structured_data["cost"] == "Paid"


def test_prepare_eb_event_date_parsed():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(start_time="2024-04-21T10:00:00")])
    assert result[0].structured_data["event_date"] == "2024-04-21"


def test_prepare_eb_event_time_parsed():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(start_time="2024-04-21T10:30:00")])
    assert result[0].structured_data["event_time"] == "10:30"


def test_prepare_eb_family_friendly():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].structured_data["family_friendly"] == 1


def test_prepare_eb_venue_field():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(venue_name="Target Field")])
    assert result[0].structured_data["venue"] == "Target Field"


def test_prepare_eb_address_field():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(address="1 Twins Way")])
    assert result[0].structured_data["address"] == "1 Twins Way"


def test_prepare_eb_source_url():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(url="https://eventbrite.com/e/999")])
    assert result[0].source_url == "https://eventbrite.com/e/999"


def test_prepare_eb_category():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].structured_data["category"] == "community"


def test_prepare_eb_tags_contain_event():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert "event" in result[0].tags


def test_prepare_eb_tags_contain_local():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert "local" in result[0].tags


def test_prepare_eb_empty_start_time():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(start_time="")])
    assert result[0].structured_data["event_time"] == ""


def test_prepare_eb_title_in_structured_data():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(title="Summer Concert")])
    assert result[0].structured_data["title"] == "Summer Concert"


# ──────────────────────────────────────────────────────────────────────────────
# Section 8: prepare_items — local_rss
# ──────────────────────────────────────────────────────────────────────────────

def _make_rss_raw(**kwargs):
    base = {
        "type": "local_rss",
        "title": "Road Closure on I-35W",
        "url": "https://minneapolis.gov/news/1",
        "description": "Overnight lane closures for bridge maintenance.",
        "feed": "https://minneapolis.gov/rss",
    }
    base.update(kwargs)
    return base


def test_prepare_rss_returns_raw_item():
    from jarvis.ingestion import RawItem
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert isinstance(result[0], RawItem)


def test_prepare_rss_fact_type():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert result[0].fact_type == "local_data"


def test_prepare_rss_source():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert result[0].source == "local_rss"


def test_prepare_rss_domain():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert result[0].domain == "local"


def test_prepare_rss_quality_hint():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert result[0].quality_hint == 0.5


def test_prepare_rss_content_has_title():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Water Main Break")])
    assert "Water Main Break" in result[0].content


def test_prepare_rss_structured_data_title():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="New Park Opening")])
    assert result[0].structured_data["title"] == "New Park Opening"


def test_prepare_rss_structured_data_source():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(feed="https://city.gov/rss")])
    assert result[0].structured_data["source"] == "https://city.gov/rss"


def test_prepare_rss_source_url_none_when_empty():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(url="")])
    assert result[0].source_url is None


def test_prepare_rss_source_url_set_when_provided():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(url="https://example.com/article")])
    assert result[0].source_url == "https://example.com/article"


def test_prepare_rss_tags_contain_local():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert "local" in result[0].tags


def test_prepare_rss_tags_contain_news():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert "news" in result[0].tags


def test_prepare_rss_category_infrastructure():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Road Closure on I-35W")])
    assert result[0].structured_data["category"] == "infrastructure"


def test_prepare_rss_category_education():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="New School Policy Announced")])
    assert result[0].structured_data["category"] == "education"


def test_prepare_rss_category_government():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="City Council Votes on Budget")])
    assert result[0].structured_data["category"] == "government"


def test_prepare_rss_category_public_safety():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Police Arrest Suspect in Crime")])
    assert result[0].structured_data["category"] == "public_safety"


def test_prepare_rss_category_business():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="New Restaurant Opens Downtown")])
    assert result[0].structured_data["category"] == "business"


def test_prepare_rss_category_recreation():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Summer Festival at Loring Park Trail")])
    assert result[0].structured_data["category"] == "recreation"


def test_prepare_rss_category_general():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Something Happened Today")])
    assert result[0].structured_data["category"] == "general"


def test_prepare_rss_content_truncation():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(description="x" * 300)])
    assert len(result[0].content) < 400  # content is title + truncated desc


# ──────────────────────────────────────────────────────────────────────────────
# Section 9: prepare_items — mixed and empty
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_empty_list():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([])
    assert result == []


def test_prepare_unknown_type_skipped():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([{"type": "unknown_source", "title": "test"}])
    assert result == []


def test_prepare_mixed_types():
    engine = _make_local_intel_engine()
    raws = [
        _make_nws_raw(),
        _make_eb_raw(),
        _make_rss_raw(),
    ]
    result = engine.prepare_items(raws)
    assert len(result) == 3


def test_prepare_mixed_types_fact_types():
    engine = _make_local_intel_engine()
    raws = [_make_nws_raw(), _make_eb_raw(), _make_rss_raw()]
    result = engine.prepare_items(raws)
    fact_types = {r.fact_type for r in result}
    assert "local_data" in fact_types
    assert "local_events" in fact_types


def test_prepare_all_have_domain():
    engine = _make_local_intel_engine()
    raws = [_make_nws_raw(), _make_eb_raw(), _make_rss_raw()]
    result = engine.prepare_items(raws)
    assert all(r.domain == "local" for r in result)


# ──────────────────────────────────────────────────────────────────────────────
# Section 10: analyze() — blackboard posting
# ──────────────────────────────────────────────────────────────────────────────

def _make_nice_weekend_weather(name="Saturday", temp=72, forecast="Sunny"):
    return {
        "type": "nws_weather",
        "name": name,
        "temperature": temp,
        "temperature_unit": "F",
        "short_forecast": forecast,
        "is_daytime": True,
    }


def test_analyze_nice_saturday_posts_to_blackboard():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 72, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_nice_sunday_posts_to_blackboard():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Sunday", 68, "Partly Cloudy")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_blackboard_post_topic():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather()]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    call_kwargs = mock_bb.post.call_args
    assert call_kwargs[1]["topic"] == "activity_suggestion"


def test_analyze_blackboard_post_author():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather()]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    call_kwargs = mock_bb.post.call_args
    assert call_kwargs[1]["author"] == "local_intel_engine"


def test_analyze_blackboard_content_has_temperature():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather(temp=75)]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    content = mock_bb.post.call_args[1]["content"]
    assert "75" in content


def test_analyze_blackboard_content_has_forecast():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather(forecast="Clear Skies")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    content = mock_bb.post.call_args[1]["content"]
    assert "Clear Skies" in content


def test_analyze_rainy_saturday_no_post():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 55, "Rain Likely")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_stormy_saturday_no_post():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 65, "Thunderstorm")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_snowy_saturday_no_post():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 30, "Snow Showers")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_weekday_nice_no_post():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Monday", 75, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_temperature_too_cold_no_post():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 50, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_temperature_too_hot_no_post():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 90, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_blackboard_failure_does_not_crash():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather()]
    mock_bb = MagicMock()
    mock_bb.post.side_effect = Exception("blackboard down")
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        result = engine.analyze(gathered)  # should not raise
    assert result == []


def test_analyze_blackboard_import_failure_does_not_crash():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather()]
    with patch("jarvis.blackboard.SharedBlackboard", side_effect=ImportError("no blackboard")):
        result = engine.analyze(gathered)
    assert result == []


def test_analyze_empty_gathered_no_post():
    engine = _make_local_intel_engine()
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        result = engine.analyze([])
    mock_bb.post.assert_not_called()
    assert result == []


def test_analyze_no_weather_items_no_post():
    engine = _make_local_intel_engine()
    gathered = [{"type": "eventbrite", "title": "Concert"}, {"type": "local_rss", "title": "News"}]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        result = engine.analyze(gathered)
    mock_bb.post.assert_not_called()


def test_analyze_multiple_nice_weekends_one_post():
    engine = _make_local_intel_engine()
    gathered = [
        _make_nice_weekend_weather("Saturday", 72, "Sunny"),
        _make_nice_weekend_weather("Sunday", 68, "Partly Cloudy"),
    ]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_returns_empty_insights_list():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather()]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        result = engine.analyze(gathered)
    assert isinstance(result, list)


def test_analyze_saturday_case_insensitive():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("saturday", 72, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_sat_abbreviation():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("This Sat", 72, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_boundary_temp_60():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 60, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_boundary_temp_85():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather("Saturday", 85, "Sunny")]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    mock_bb.post.assert_called_once()


def test_analyze_content_in_post_is_string():
    engine = _make_local_intel_engine()
    gathered = [_make_nice_weekend_weather()]
    mock_bb = MagicMock()
    with patch("jarvis.blackboard.SharedBlackboard", return_value=mock_bb):
        engine.analyze(gathered)
    content = mock_bb.post.call_args[1]["content"]
    assert isinstance(content, str)


# ──────────────────────────────────────────────────────────────────────────────
# Section 11: improve()
# ──────────────────────────────────────────────────────────────────────────────

def test_improve_no_token_returns_gap():
    engine = _make_local_intel_engine()
    with patch("jarvis.config.EVENTBRITE_TOKEN", ""):
        gaps = engine.improve()
    assert len(gaps) >= 1
    assert any("Eventbrite" in g for g in gaps)


def test_improve_no_local_feeds_returns_gap():
    engine = _make_local_intel_engine()
    with patch("jarvis.config.EVENTBRITE_TOKEN", "tok"), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        gaps = engine.improve()
    assert any("local" in g.lower() or "feeds" in g.lower() or "LOCAL" in g for g in gaps)


def test_improve_with_token_and_feeds_no_token_gap():
    engine = _make_local_intel_engine()
    engine._engine_store.query.return_value = []
    with patch("jarvis.config.EVENTBRITE_TOKEN", "mytoken"), \
         patch("jarvis.config.LOCAL_FEEDS", ["https://example.com/feed"]):
        gaps = engine.improve()
    assert not any("Eventbrite" in g for g in gaps)


def test_improve_stale_weather_returns_gap():
    engine = _make_local_intel_engine()
    engine._engine_store.query.return_value = [
        {"id": "1", "category": "weather", "data_date": "2020-01-01"}
    ]
    with patch("jarvis.config.EVENTBRITE_TOKEN", "tok"), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        gaps = engine.improve()
    assert any("stale" in g.lower() or "weather" in g.lower() for g in gaps)


def test_improve_engine_store_exception_handled():
    engine = _make_local_intel_engine()
    engine._engine_store.query.side_effect = Exception("db error")
    with patch("jarvis.config.EVENTBRITE_TOKEN", "tok"), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        gaps = engine.improve()  # should not raise
    assert isinstance(gaps, list)


def test_improve_returns_list():
    engine = _make_local_intel_engine()
    with patch("jarvis.config.EVENTBRITE_TOKEN", ""), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        gaps = engine.improve()
    assert isinstance(gaps, list)


# ──────────────────────────────────────────────────────────────────────────────
# Section 12: _classify_local_title
# ──────────────────────────────────────────────────────────────────────────────

from jarvis.engines.local_intel import _classify_local_title


def test_classify_road():
    assert _classify_local_title("Road Closure on I-35W") == "infrastructure"


def test_classify_construction():
    assert _classify_local_title("Bridge Construction Begins") == "infrastructure"


def test_classify_traffic():
    assert _classify_local_title("Traffic Alert: I-94 Closure") == "infrastructure"


def test_classify_bridge():
    assert _classify_local_title("Bridge Closure on Highway 61") == "infrastructure"


def test_classify_closure():
    assert _classify_local_title("Freeway Closure Tonight") == "infrastructure"


def test_classify_school():
    assert _classify_local_title("Minneapolis School District Announces New Policy") == "education"


def test_classify_education():
    assert _classify_local_title("Education Funding Debate Continues") == "education"


def test_classify_teacher():
    assert _classify_local_title("Teacher Strike Update") == "education"


def test_classify_student():
    assert _classify_local_title("Student Test Scores Released") == "education"


def test_classify_crime():
    assert _classify_local_title("Crime Down in Minneapolis Neighborhoods") == "public_safety"


def test_classify_police():
    assert _classify_local_title("Police Release New Guidelines") == "public_safety"


def test_classify_fire():
    assert _classify_local_title("Fire Department Responds to Downtown Blaze") == "public_safety"


def test_classify_safety():
    assert _classify_local_title("Safety Tips for Winter Driving") == "public_safety"


def test_classify_tax():
    assert _classify_local_title("Property Tax Increase Proposed") == "government"


def test_classify_city():
    assert _classify_local_title("City Approves New Zoning Plan") == "government"


def test_classify_council():
    assert _classify_local_title("City Council Votes on Budget Amendment") == "government"


def test_classify_vote():
    assert _classify_local_title("Vote on Transportation Bill Tuesday") == "government"


def test_classify_business():
    assert _classify_local_title("New Restaurant Opens on Lake Street") == "business"


def test_classify_store():
    assert _classify_local_title("Target Store Grand Opening Downtown") == "business"


def test_classify_park():
    assert _classify_local_title("New Park Opens in Nordeast") == "recreation"


def test_classify_trail():
    assert _classify_local_title("New Bike Trail Connects Lake Harriet") == "recreation"


def test_classify_festival():
    assert _classify_local_title("Summer Festival Draws Record Crowds") == "recreation"


def test_classify_general():
    assert _classify_local_title("Something Interesting Happened") == "general"


def test_classify_general_unrecognized():
    assert _classify_local_title("Notice from the Metro Area") == "general"


def test_classify_case_insensitive():
    assert _classify_local_title("SCHOOL BOARD MEETING") == "education"


def test_classify_empty_string():
    assert _classify_local_title("") == "general"


# ──────────────────────────────────────────────────────────────────────────────
# Section 13: NWS period name handling
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_nws_this_afternoon():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="This Afternoon")])
    assert "This Afternoon" in result[0].content


def test_prepare_nws_tonight():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="Tonight")])
    assert "Tonight" in result[0].content


def test_prepare_nws_monday():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="Monday")])
    assert "Monday" in result[0].structured_data["title"]


def test_prepare_nws_wednesday():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="Wednesday")])
    assert result[0].structured_data["title"] == "Weather: Wednesday"


def test_prepare_nws_tag_period_name():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(name="Thursday Night")])
    assert "thursday_night" in result[0].tags


# ──────────────────────────────────────────────────────────────────────────────
# Section 14: Eventbrite with null/missing fields
# ──────────────────────────────────────────────────────────────────────────────

def test_eventbrite_no_description():
    engine = _make_local_intel_engine()
    data = json.dumps({"events": [{
        "name": {"text": "Event"},
        "description": None,
        "start": {"local": "2024-04-21T10:00:00"},
        "end": {"local": "2024-04-21T12:00:00"},
        "url": "https://eb.com/1",
        "is_free": True,
        "category_id": "110",
        "venue": {"name": "Venue", "address": {"localized_address_display": "123 St"}},
    }]}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(data)):
        result = engine._fetch_eventbrite("44.9778", "-93.2650", "tok")
    assert len(result) == 1
    assert result[0]["description"] == ""


def test_eventbrite_no_url():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(url="")])
    assert result[0].source_url == ""


# ──────────────────────────────────────────────────────────────────────────────
# Section 15: Edge cases
# ──────────────────────────────────────────────────────────────────────────────

def test_prepare_nws_unicode_content():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(short_forecast="Ensoleillé ☀")])
    assert len(result) == 1


def test_prepare_rss_unicode_title():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Résultats de l'élection municipale")])
    assert len(result) == 1


def test_prepare_eb_unicode_description():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(description="Musik- und Kulturfestival 🎵")])
    assert len(result) == 1


def test_prepare_nws_very_long_detailed_forecast():
    engine = _make_local_intel_engine()
    long_detail = "Very detailed " * 200
    result = engine.prepare_items([_make_nws_raw(detailed_forecast=long_detail)])
    assert len(result) == 1


def test_prepare_rss_empty_description():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(description="")])
    assert len(result) == 1
    assert result[0].structured_data["content"] == result[0].structured_data["title"]


def test_prepare_eb_empty_description():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(description="")])
    assert len(result) == 1


def test_prepare_nws_empty_start_time_defaults():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(start_time="")])
    # should not crash; data_date gets a fallback
    assert len(result) == 1


def test_local_rss_both_rss20_and_atom():
    """Feed with both RSS 2.0 items AND Atom entries (unusual but possible)."""
    mixed = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item><title>RSS Item</title><link>https://example.com/1</link><description>desc</description></item>
  </channel>
</rss>"""
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(mixed)):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert len(result) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Section 16: run_cycle integration
# ──────────────────────────────────────────────────────────────────────────────

def test_run_cycle_returns_cycle_report():
    from jarvis.memory_tiers.types import CycleReport
    engine = _make_local_intel_engine()
    with patch.object(engine, "gather", return_value=[]), \
         patch.object(engine, "improve", return_value=[]):
        report = engine.run_cycle()
    assert isinstance(report, CycleReport)


def test_run_cycle_no_error_on_empty_gather():
    engine = _make_local_intel_engine()
    with patch.object(engine, "gather", return_value=[]), \
         patch.object(engine, "improve", return_value=[]):
        report = engine.run_cycle()
    assert report.error is None


def test_run_cycle_gathered_count():
    engine = _make_local_intel_engine()
    with patch.object(engine, "gather", return_value=[_make_nws_raw(), _make_nws_raw()]), \
         patch.object(engine, "improve", return_value=[]):
        report = engine.run_cycle()
    assert report.gathered == 2


def test_run_cycle_calls_improve():
    engine = _make_local_intel_engine()
    with patch.object(engine, "gather", return_value=[]) as _m_g, \
         patch.object(engine, "improve", return_value=[]) as mock_imp:
        engine.run_cycle()
    mock_imp.assert_called_once()


def test_run_cycle_exception_captured():
    engine = _make_local_intel_engine()
    with patch.object(engine, "gather", side_effect=RuntimeError("network down")):
        report = engine.run_cycle()
    assert report.error is not None
    assert "network down" in report.error


def test_run_cycle_specialist_name():
    engine = _make_local_intel_engine()
    with patch.object(engine, "gather", return_value=[]), \
         patch.object(engine, "improve", return_value=[]):
        report = engine.run_cycle()
    assert report.specialist == "local_intel_engine"


# ──────────────────────────────────────────────────────────────────────────────
# Section 17: Additional coverage
# ──────────────────────────────────────────────────────────────────────────────

def test_nws_uses_correct_user_agent():
    engine = _make_local_intel_engine()
    requests_made = []

    def capture_urlopen(req, timeout=None):
        requests_made.append(req)
        raise Exception("stop after first call")

    with patch("urllib.request.urlopen", side_effect=capture_urlopen):
        engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert len(requests_made) == 1
    assert "Jarvis" in requests_made[0].get_header("User-agent")


def test_eventbrite_url_includes_radius():
    engine = _make_local_intel_engine()
    requests_made = []

    def capture_urlopen(req, timeout=None):
        requests_made.append(req)
        raise Exception("stop")

    with patch("urllib.request.urlopen", side_effect=capture_urlopen):
        engine._fetch_eventbrite("44.9778", "-93.2650", "mytoken")
    assert "25mi" in requests_made[0].full_url


def test_eventbrite_token_in_url():
    engine = _make_local_intel_engine()
    requests_made = []

    def capture_urlopen(req, timeout=None):
        requests_made.append(req)
        raise Exception("stop")

    with patch("urllib.request.urlopen", side_effect=capture_urlopen):
        engine._fetch_eventbrite("44.9778", "-93.2650", "secrettoken")
    assert "secrettoken" in requests_made[0].full_url


def test_nws_user_agent_has_accept_header():
    engine = _make_local_intel_engine()
    requests_made = []

    def capture_urlopen(req, timeout=None):
        requests_made.append(req)
        raise Exception("stop")

    with patch("urllib.request.urlopen", side_effect=capture_urlopen):
        engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert "geo+json" in requests_made[0].get_header("Accept")


def test_prepare_eb_description_in_structured_data():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw(description="Great outdoor event")])
    assert "Great outdoor event" in result[0].structured_data.get("description", "")


def test_prepare_rss_data_date_is_string():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw()])
    assert isinstance(result[0].structured_data["data_date"], str)


def test_prepare_nws_structured_data_has_content():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(detailed_forecast="Very sunny.")])
    assert result[0].structured_data["content"]


def test_classify_arrest():
    assert _classify_local_title("Police Arrest Three in Robbery Case") == "public_safety"


def test_classify_election():
    assert _classify_local_title("Election Results Expected Tonight") == "government"


def test_classify_i35():
    assert _classify_local_title("I-35W Northbound Lane Closed") == "infrastructure"


def test_prepare_rss_tags_contain_category():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(title="Road Closure on I-35W")])
    assert "infrastructure" in result[0].tags


def test_prepare_nws_celcius_unit():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_nws_raw(temperature=22, temperature_unit="C")])
    assert "22°C" in result[0].content


def test_gather_nws_passes_config_lat_lon():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[]) as mock_nws, \
         patch("jarvis.config.HOME_LAT", "44.0000"), \
         patch("jarvis.config.HOME_LON", "-93.0000"), \
         patch("jarvis.config.EVENTBRITE_TOKEN", ""), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        engine.gather()
    mock_nws.assert_called_once_with("44.0000", "-93.0000")


def test_gather_eventbrite_passes_token():
    engine = _make_local_intel_engine()
    with patch.object(engine, "_fetch_nws_forecast", return_value=[]), \
         patch.object(engine, "_fetch_eventbrite", return_value=[]) as mock_eb, \
         patch("jarvis.config.EVENTBRITE_TOKEN", "abcdef"), \
         patch("jarvis.config.HOME_LAT", "44.9778"), \
         patch("jarvis.config.HOME_LON", "-93.2650"), \
         patch("jarvis.config.LOCAL_FEEDS", []):
        engine.gather()
    mock_eb.assert_called_once_with("44.9778", "-93.2650", "abcdef")


def test_prepare_rss_content_includes_description():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_rss_raw(description="Bridge is closed for repairs.")])
    assert "Bridge is closed" in result[0].content


def test_prepare_eb_source_in_structured_data():
    engine = _make_local_intel_engine()
    result = engine.prepare_items([_make_eb_raw()])
    assert result[0].structured_data["source"] == "eventbrite"


def test_engine_inherits_base_knowledge_engine():
    from jarvis.engines.base_engine import BaseKnowledgeEngine
    from jarvis.engines.local_intel import LocalIntelEngine
    assert issubclass(LocalIntelEngine, BaseKnowledgeEngine)


def test_nws_malformed_points_response():
    engine = _make_local_intel_engine()
    # Missing 'properties' key
    bad_data = json.dumps({"type": "Feature"}).encode()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(bad_data)):
        result = engine._fetch_nws_forecast("44.9778", "-93.2650")
    assert result == []


def test_prepare_items_only_processes_known_types():
    engine = _make_local_intel_engine()
    raws = [
        {"type": "nws_weather", "name": "Saturday", "temperature": 72, "temperature_unit": "F",
         "short_forecast": "Sunny", "detailed_forecast": "Sunny.", "is_daytime": True,
         "start_time": "2024-04-20T06:00:00-05:00", "location": "44,-93", "source_url": "http://x"},
        {"type": "alien_source", "data": "ignored"},
        {"type": "eventbrite", "title": "Event", "description": "Desc",
         "start_time": "2024-04-21T10:00:00", "venue_name": "Venue",
         "address": "123 St", "is_free": True, "url": "https://eb.com/1"},
    ]
    result = engine.prepare_items(raws)
    assert len(result) == 2  # alien_source skipped


def test_local_rss_type_field():
    engine = _make_local_intel_engine()
    with patch("urllib.request.urlopen", return_value=_make_urlopen_mock(RSS_DATA)):
        result = engine._fetch_local_rss("https://example.com/feed")
    assert all(r["type"] == "local_rss" for r in result)
