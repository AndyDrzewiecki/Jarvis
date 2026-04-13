"""Tests for InvestorAdapter — mocks the investor orchestrator module."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


def _mock_run_once():
    return {
        "daily_brief": "Markets are choppy. Tech leading. Risk: moderate.",
        "market_output": {
            "risk_label": "moderate",
            "summary": "S&P 500 flat, NASDAQ up 0.5%",
        },
        "forecast_output": {},
        "signal_output": {},
    }


@pytest.fixture
def mock_investor():
    mock_inv = MagicMock()
    mock_inv.run_once.return_value = _mock_run_once()
    return mock_inv


def test_daily_brief_success(mock_investor):
    with patch("jarvis.adapters.investor._import_investor_orchestrator", return_value=mock_investor):
        from jarvis.adapters.investor import InvestorAdapter
        a = InvestorAdapter()
        result = a.safe_run("daily_brief", {})
        assert result.success is True
        assert "Markets" in result.text or "choppy" in result.text
        assert result.adapter == "investor"


def test_market_check_success(mock_investor):
    with patch("jarvis.adapters.investor._import_investor_orchestrator", return_value=mock_investor):
        from jarvis.adapters.investor import InvestorAdapter
        a = InvestorAdapter()
        result = a.safe_run("market_check", {})
        assert result.success is True
        assert "moderate" in result.text.lower()


def test_investor_unavailable():
    with patch("jarvis.adapters.investor._import_investor_orchestrator", return_value=None):
        from jarvis.adapters.investor import InvestorAdapter
        a = InvestorAdapter()
        result = a.safe_run("daily_brief", {})
        assert result.success is False
        assert "not available" in result.text.lower()


def test_investor_unknown_capability(mock_investor):
    with patch("jarvis.adapters.investor._import_investor_orchestrator", return_value=mock_investor):
        from jarvis.adapters.investor import InvestorAdapter
        a = InvestorAdapter()
        result = a.safe_run("unknown_cap", {})
        assert result.success is False
        assert "Unknown capability" in result.text


def test_daily_brief_no_brief_key(mock_investor):
    mock_investor.run_once.return_value = {"daily_brief": None, "market_output": {}}
    with patch("jarvis.adapters.investor._import_investor_orchestrator", return_value=mock_investor):
        from jarvis.adapters.investor import InvestorAdapter
        a = InvestorAdapter()
        result = a.safe_run("daily_brief", {})
        assert result.success is True
        assert "No brief" in result.text


def test_has_capabilities():
    from jarvis.adapters.investor import InvestorAdapter
    a = InvestorAdapter()
    assert "daily_brief" in a.capabilities
    assert "market_check" in a.capabilities
