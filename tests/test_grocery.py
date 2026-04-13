"""Tests for GroceryAdapter — uses mocked grocery_agent module."""
from __future__ import annotations
import sys
import types
import pytest
from unittest.mock import patch, MagicMock


def _make_mock_ga():
    """Create a mock grocery_agent module."""
    ga = MagicMock()
    ga.generate_simple_meal_plan.return_value = {
        "meals": [
            {"day": "Mon", "main": "tacos", "side": "rice", "veg": "salad"},
        ],
        "needed_items": [{"item": "eggs_dozen", "qty": 2, "unit": "dozen"}],
    }
    ga.load_pricebook.return_value = {
        "_stores": {}, "_rules": {"monthly_budget": 800, "prefer_sale_items": True, "prefer_use_inventory_first": True}, "items": {}
    }
    ga.load_inventory.return_value = {
        "items": {},
        "_meta": {"last_updated": "2026-04-10"},
        "_raw_type": "dict",
    }
    ga.build_shopping_list.return_value = (
        {"unknown": [{"item": "eggs_dozen", "qty": 2}]},
        {"unknown": 0.0},
        0.0,
    )
    ga.normalize_item_key.side_effect = lambda s: s.lower().replace(" ", "_")
    return ga


@pytest.fixture(autouse=True)
def mock_grocery_agent(monkeypatch):
    mock_ga = _make_mock_ga()
    # Patch the _import_grocery function in the grocery module
    with patch("jarvis.adapters.grocery._import_grocery", return_value=mock_ga):
        yield mock_ga


def test_meal_plan_success(mock_grocery_agent):
    from jarvis.adapters.grocery import GroceryAdapter
    a = GroceryAdapter()
    result = a.safe_run("meal_plan", {})
    assert result.success is True
    assert "meal plan" in result.text.lower()
    assert result.adapter == "grocery"


def test_shopping_list_success(mock_grocery_agent):
    from jarvis.adapters.grocery import GroceryAdapter
    a = GroceryAdapter()
    result = a.safe_run("shopping_list", {})
    assert result.success is True
    assert "shopping list" in result.text.lower() or "$" in result.text


def test_inventory_empty(mock_grocery_agent):
    from jarvis.adapters.grocery import GroceryAdapter
    a = GroceryAdapter()
    result = a.safe_run("inventory", {})
    assert result.success is True
    assert "empty" in result.text.lower() or "0 item" in result.text.lower()


def test_inventory_with_items(mock_grocery_agent):
    mock_grocery_agent.load_inventory.return_value = {
        "items": {"eggs_dozen": {"qty": 2, "unit": "dozen"}},
        "_meta": {},
        "_raw_type": "dict",
    }
    from importlib import reload
    import jarvis.adapters.grocery as gmod
    a = gmod.GroceryAdapter()
    result = a.safe_run("inventory", {})
    assert result.success is True
    assert "1" in result.text


def test_price_check_not_found(mock_grocery_agent):
    mock_grocery_agent.load_pricebook.return_value = {"items": {}, "_stores": {}, "_rules": {}}
    from jarvis.adapters.grocery import GroceryAdapter
    a = GroceryAdapter()
    result = a.safe_run("price_check", {"item": "phantom_item"})
    assert result.success is True
    assert "not found" in result.text.lower()


def test_price_check_found(mock_grocery_agent):
    mock_grocery_agent.load_pricebook.return_value = {
        "items": {"eggs_dozen": {"stores": {"costco": {"price": 4.99, "sale": True}}}},
        "_stores": {}, "_rules": {},
    }
    from jarvis.adapters.grocery import GroceryAdapter
    a = GroceryAdapter()
    result = a.safe_run("price_check", {"item": "eggs_dozen"})
    assert result.success is True
    assert "4.99" in result.text or "costco" in result.text.lower()


def test_unknown_capability(mock_grocery_agent):
    from jarvis.adapters.grocery import GroceryAdapter
    a = GroceryAdapter()
    result = a.safe_run("unknown_cap", {})
    assert result.success is False
    assert "Unknown capability" in result.text


def test_grocery_agent_unavailable():
    with patch("jarvis.adapters.grocery._import_grocery", return_value=None):
        from jarvis.adapters.grocery import GroceryAdapter
        a = GroceryAdapter()
        result = a.safe_run("meal_plan", {})
        assert result.success is False
        assert "not available" in result.text.lower()
