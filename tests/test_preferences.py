"""Tests for jarvis/preferences.py — all I/O directed to tmp_path."""
from __future__ import annotations
import json
import pytest


@pytest.fixture(autouse=True)
def tmp_prefs_path(tmp_path, monkeypatch):
    """Redirect prefs to a temp file for each test."""
    monkeypatch.setenv("JARVIS_PREFS_PATH", str(tmp_path / "preferences.json"))


@pytest.fixture
def prefs():
    import jarvis.preferences as p
    return p


def test_load_creates_defaults(prefs):
    data = prefs.load()
    assert "city" in data
    assert data["city"] == "Minneapolis,US"
    assert data["budget_monthly"] == 800
    assert data["notification_level"] == "important"


def test_load_persists_file(prefs, tmp_path):
    prefs.load()
    path = tmp_path / "preferences.json"
    assert path.exists()
    with open(path) as f:
        data = json.load(f)
    assert "city" in data


def test_load_twice_consistent(prefs):
    first = prefs.load()
    second = prefs.load()
    assert first == second


def test_get_existing_key(prefs):
    assert prefs.get("city") == "Minneapolis,US"


def test_get_missing_key_returns_default(prefs):
    assert prefs.get("nonexistent_key", "fallback") == "fallback"


def test_get_missing_key_returns_none_by_default(prefs):
    assert prefs.get("nonexistent_key") is None


def test_set_persists(prefs):
    prefs.set("city", "Chicago,US")
    assert prefs.get("city") == "Chicago,US"


def test_set_new_key(prefs):
    prefs.set("custom_key", 42)
    assert prefs.get("custom_key") == 42


def test_update_merges(prefs):
    result = prefs.update({"city": "Denver,US", "budget_monthly": 500})
    assert result["city"] == "Denver,US"
    assert result["budget_monthly"] == 500
    # Existing keys preserved
    assert "dietary_restrictions" in result
    assert "notification_level" in result


def test_update_returns_full_dict(prefs):
    result = prefs.update({"city": "Austin,US"})
    assert isinstance(result, dict)
    assert len(result) >= len(prefs.DEFAULTS)


def test_update_persists(prefs):
    prefs.update({"budget_monthly": 1200})
    # Fresh load should see the updated value
    reloaded = prefs.load()
    assert reloaded["budget_monthly"] == 1200


def test_defaults_has_expected_keys(prefs):
    expected = {
        "city", "budget_monthly", "dietary_restrictions",
        "preferred_stores", "notification_level", "brief_include_weather"
    }
    assert expected.issubset(set(prefs.DEFAULTS.keys()))
