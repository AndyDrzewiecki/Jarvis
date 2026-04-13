"""Tests for WeatherAdapter — all HTTP calls mocked."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

from jarvis.adapters.weather import WeatherAdapter, _kelvin_to_f, _mps_to_mph


@pytest.fixture
def adapter():
    return WeatherAdapter()


def _mock_current():
    m = MagicMock()
    m.raise_for_status = lambda: None
    m.json.return_value = {
        "name": "Minneapolis",
        "main": {"temp": 273.15, "feels_like": 270.0, "humidity": 65},
        "weather": [{"description": "overcast clouds", "icon": "04d"}],
        "wind": {"speed": 5.0},
        "coord": {"lat": 44.97, "lon": -93.26},
    }
    return m


def _mock_forecast():
    m = MagicMock()
    m.raise_for_status = lambda: None
    m.json.return_value = {
        "city": {"name": "Minneapolis"},
        "list": [
            {
                "dt_txt": "2026-04-13 12:00:00",
                "main": {"temp_max": 283.15, "temp_min": 273.15},
                "weather": [{"description": "clear sky"}],
            },
            {
                "dt_txt": "2026-04-13 15:00:00",
                "main": {"temp_max": 285.0, "temp_min": 274.0},
                "weather": [{"description": "partly cloudy"}],
            },
        ],
    }
    return m


# ── unit conversions ───────────────────────────────────────────────────────────

def test_kelvin_to_f_freezing():
    assert _kelvin_to_f(273.15) == 32.0


def test_kelvin_to_f_boiling():
    assert _kelvin_to_f(373.15) == 212.0


def test_mps_to_mph_zero():
    assert _mps_to_mph(0) == 0.0


def test_mps_to_mph_positive():
    assert _mps_to_mph(1.0) > 0


# ── adapter metadata ───────────────────────────────────────────────────────────

def test_adapter_name(adapter):
    assert adapter.name == "weather"


def test_adapter_capabilities(adapter):
    assert "current" in adapter.capabilities
    assert "forecast" in adapter.capabilities
    assert "alerts" in adapter.capabilities


# ── no API key ─────────────────────────────────────────────────────────────────

def test_no_api_key_current(adapter, monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    result = adapter.run("current", {})
    assert result.success is False
    assert "OPENWEATHER_API_KEY" in result.text


def test_no_api_key_forecast(adapter, monkeypatch):
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    result = adapter.run("forecast", {})
    assert result.success is False


# ── current capability ─────────────────────────────────────────────────────────

def test_current_success(adapter, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "testkey")
    with patch("jarvis.adapters.weather.requests.get", return_value=_mock_current()):
        result = adapter.run("current", {"city": "Minneapolis,US"})
    assert result.success is True
    assert result.adapter == "weather"
    assert result.data["temp_f"] == 32.0
    assert result.data["city"] == "Minneapolis"


def test_current_text_contains_temp(adapter, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "testkey")
    with patch("jarvis.adapters.weather.requests.get", return_value=_mock_current()):
        result = adapter.run("current", {"city": "Minneapolis,US"})
    assert "32.0°F" in result.text or "Minneapolis" in result.text


def test_current_data_structure(adapter, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "testkey")
    with patch("jarvis.adapters.weather.requests.get", return_value=_mock_current()):
        result = adapter.run("current", {"city": "Minneapolis,US"})
    assert "humidity" in result.data
    assert "wind_mph" in result.data
    assert "feels_like_f" in result.data
    assert "description" in result.data


# ── forecast capability ────────────────────────────────────────────────────────

def test_forecast_success(adapter, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "testkey")
    with patch("jarvis.adapters.weather.requests.get", return_value=_mock_forecast()):
        result = adapter.run("forecast", {"city": "Minneapolis,US"})
    assert result.success is True
    assert "forecast" in result.data
    assert isinstance(result.data["forecast"], list)
    assert len(result.data["forecast"]) >= 1


def test_forecast_day_structure(adapter, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "testkey")
    with patch("jarvis.adapters.weather.requests.get", return_value=_mock_forecast()):
        result = adapter.run("forecast", {"city": "Minneapolis,US"})
    day = result.data["forecast"][0]
    assert "date" in day
    assert "high_f" in day
    assert "low_f" in day
    assert "description" in day


# ── unknown capability ─────────────────────────────────────────────────────────

def test_unknown_capability(adapter, monkeypatch):
    monkeypatch.setenv("OPENWEATHER_API_KEY", "testkey")
    result = adapter.run("unknown_cap", {})
    assert result.success is False
    assert "Unknown capability" in result.text
