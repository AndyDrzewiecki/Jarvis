"""Tests for jarvis/ambient.py"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from jarvis.ambient import _time_of_day, get_context, format_for_prompt


# ── Time bucketing ─────────────────────────────────────────────────────────────

class TestTimeBucketing:
    def test_night_before_dawn(self):
        assert _time_of_day(3) == "Night"

    def test_morning(self):
        assert _time_of_day(8) == "Morning"

    def test_afternoon(self):
        assert _time_of_day(14) == "Afternoon"

    def test_evening(self):
        assert _time_of_day(19) == "Evening"

    def test_late_night(self):
        assert _time_of_day(23) == "Night"

    def test_boundary_morning_start(self):
        assert _time_of_day(6) == "Morning"

    def test_boundary_afternoon_start(self):
        assert _time_of_day(12) == "Afternoon"

    def test_boundary_evening_start(self):
        assert _time_of_day(17) == "Evening"


# ── is_workday ─────────────────────────────────────────────────────────────────

class TestIsWorkday:
    def test_monday_is_workday(self):
        # Monday = weekday 0
        with patch("jarvis.ambient.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 13)  # Monday
            ctx = get_context()
        assert ctx["is_workday"] is True

    def test_friday_is_workday(self):
        with patch("jarvis.ambient.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 17)  # Friday
            ctx = get_context()
        assert ctx["is_workday"] is True

    def test_saturday_is_not_workday(self):
        with patch("jarvis.ambient.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 18)  # Saturday
            ctx = get_context()
        assert ctx["is_workday"] is False

    def test_sunday_is_not_workday(self):
        with patch("jarvis.ambient.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 19)  # Sunday
            ctx = get_context()
        assert ctx["is_workday"] is False


# ── format_for_prompt ──────────────────────────────────────────────────────────

class TestFormatForPrompt:
    def test_contains_ambient_context_tags(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AMBIENT_ENABLED", "true")
        result = format_for_prompt()
        assert "<ambient_context>" in result
        assert "</ambient_context>" in result

    def test_contains_day_of_week(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AMBIENT_ENABLED", "true")
        result = format_for_prompt()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        assert any(day in result for day in days)

    def test_disabled_returns_empty_string(self, monkeypatch):
        monkeypatch.setenv("JARVIS_AMBIENT_ENABLED", "false")
        result = format_for_prompt()
        assert result == ""


# ── Weather cache ──────────────────────────────────────────────────────────────

class TestWeatherCache:
    def test_missing_cache_returns_empty_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr("jarvis.ambient._WEATHER_CACHE", str(tmp_path / "no_cache.json"))
        from jarvis.ambient import _weather_summary
        assert _weather_summary() == ""

    def test_fresh_cache_returns_summary(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "ambient_cache.json"
        cache_file.write_text(json.dumps({
            "summary": "34°F, Overcast (Minneapolis)",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
        monkeypatch.setattr("jarvis.ambient._WEATHER_CACHE", str(cache_file))
        from jarvis.ambient import _weather_summary
        assert "34°F" in _weather_summary()

    def test_stale_cache_returns_empty_string(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "ambient_cache.json"
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cache_file.write_text(json.dumps({
            "summary": "60°F, Sunny",
            "updated_at": stale_time,
        }), encoding="utf-8")
        monkeypatch.setattr("jarvis.ambient._WEATHER_CACHE", str(cache_file))
        from jarvis.ambient import _weather_summary
        assert _weather_summary() == ""
