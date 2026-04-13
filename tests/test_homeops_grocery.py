"""Tests for HomeopsGroceryAdapter — all HTTP calls mocked."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
import requests

from jarvis.adapters.homeops_grocery import HomeopsGroceryAdapter


@pytest.fixture
def adapter():
    return HomeopsGroceryAdapter()


def _ok(data):
    """Build a mock response that returns data as JSON."""
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = data
    m.raise_for_status = lambda: None
    return m


# ── metadata ─────────────────────────────────────────────────────────────────

def test_adapter_metadata(adapter):
    assert adapter.name == "homeops_grocery"
    assert "dashboard" in adapter.capabilities
    assert "shopping_add" in adapter.capabilities
    assert "expiring_soon" in adapter.capabilities
    assert len(adapter.capabilities) == 9


# ── successful capabilities ───────────────────────────────────────────────────

def test_dashboard(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok({"spend": 100})):
        result = adapter.run("dashboard", {})
    assert result.success is True
    assert result.adapter == "homeops_grocery"


def test_inventory_list(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok([{"item": "milk"}])):
        result = adapter.run("inventory_list", {})
    assert result.success is True


def test_shopping_list(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok([])):
        result = adapter.run("shopping_list", {})
    assert result.success is True


def test_shopping_add(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.post", return_value=_ok({"id": 1})):
        result = adapter.run("shopping_add", {"name": "eggs", "quantity": 12, "unit": "count"})
    assert result.success is True
    assert "eggs" in result.text


def test_shopping_check_off(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.patch", return_value=_ok({"checked": True})):
        result = adapter.run("shopping_check_off", {"item_id": 42})
    assert result.success is True


def test_shopping_check_off_missing_item_id(adapter):
    result = adapter.run("shopping_check_off", {})
    assert result.success is False
    assert "item_id" in result.text


def test_mealplan_current(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok({"plan": "tacos"})):
        result = adapter.run("mealplan_current", {})
    assert result.success is True


def test_receipts(adapter):
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok([])):
        result = adapter.run("receipts", {})
    assert result.success is True


# ── service-down fallback ─────────────────────────────────────────────────────

def test_service_down_returns_helpful_message(adapter):
    with patch(
        "jarvis.adapters.homeops_grocery.requests.get",
        side_effect=requests.exceptions.ConnectionError("refused"),
    ):
        result = adapter.run("dashboard", {})
    assert result.success is False
    assert "not reachable" in result.text
    assert "8001" in result.text


# ── expiring_soon capability ──────────────────────────────────────────────────

def test_expiring_soon_returns_items(adapter):
    from datetime import datetime, timezone, timedelta
    future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    inventory = [
        {"name": "Chicken", "expires_at": future},
        {"name": "Rice"},  # no expiry field
    ]
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok(inventory)):
        result = adapter.run("expiring_soon", {"days": 3})
    assert result.success is True
    assert "Chicken" in result.text
    assert result.data["items"]


def test_expiring_soon_no_items(adapter):
    from datetime import datetime, timezone, timedelta
    far_future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    inventory = [{"name": "Pasta", "expires_at": far_future}]
    with patch("jarvis.adapters.homeops_grocery.requests.get", return_value=_ok(inventory)):
        result = adapter.run("expiring_soon", {"days": 2})
    assert result.success is True
    assert result.data["items"] == []


def test_expiring_soon_service_down(adapter):
    import requests as req
    with patch(
        "jarvis.adapters.homeops_grocery.requests.get",
        side_effect=req.exceptions.ConnectionError("refused"),
    ):
        result = adapter.run("expiring_soon", {})
    assert result.success is False


# ── unknown capability ────────────────────────────────────────────────────────

def test_unknown_capability(adapter):
    result = adapter.run("nonexistent", {})
    assert result.success is False
    assert "Unknown capability" in result.text
