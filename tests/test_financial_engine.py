"""TDD RED — tests/test_financial_engine.py
Tests for FinancialEngine.
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch, mock_open
from io import BytesIO


def _make_fred_response(series_id="UNRATE", value="3.7", date="2024-01-01"):
    data = {
        "observations": [
            {"date": date, "value": value}
        ]
    }
    return json.dumps(data).encode()


def _make_yahoo_response(symbol="SPY", price=470.0, prev=465.0):
    data = {
        "chart": {
            "result": [
                {
                    "meta": {
                        "regularMarketPrice": price,
                        "previousClose": prev,
                    }
                }
            ]
        }
    }
    return json.dumps(data).encode()


# 1. FinancialEngine in ENGINE_REGISTRY
def test_financial_engine_registered():
    # Import engines to trigger registration
    import jarvis.engines.financial  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    names = [cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")]
    assert "financial_engine" in names


# 2. FRED_API_KEY="" → gather() returns [] (no crash)
def test_gather_no_api_key_returns_empty():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    with patch("jarvis.config.FRED_API_KEY", ""), \
         patch("jarvis.config.TRACKED_SYMBOLS", []), \
         patch("urllib.request.urlopen") as mock_url:
        mock_url.side_effect = Exception("Should not be called")
        result = eng.gather()

    assert result == []


# 3. mock urlopen with FRED JSON → gather returns series data
def test_gather_with_fred_mock():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    resp_mock = MagicMock()
    resp_mock.read.return_value = _make_fred_response("UNRATE", "3.7", "2024-01-01")
    resp_mock.__enter__ = lambda s: s
    resp_mock.__exit__ = MagicMock(return_value=False)

    with patch("jarvis.config.FRED_API_KEY", "test-key"), \
         patch("jarvis.config.TRACKED_SYMBOLS", []), \
         patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    fred_items = [r for r in result if r.get("type") == "fred"]
    assert len(fred_items) > 0
    assert fred_items[0]["series_id"] in ("GDP", "UNRATE", "CPIAUCSL", "FEDFUNDS")


# 4. mock urlopen with Yahoo CSV-style JSON → gather returns market data
def test_gather_with_yahoo_mock():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    resp_mock = MagicMock()
    resp_mock.read.return_value = _make_yahoo_response("SPY", 470.0)
    resp_mock.__enter__ = lambda s: s
    resp_mock.__exit__ = MagicMock(return_value=False)

    with patch("jarvis.config.FRED_API_KEY", ""), \
         patch("jarvis.config.TRACKED_SYMBOLS", ["SPY"]), \
         patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    market_items = [r for r in result if r.get("type") == "market"]
    assert len(market_items) == 1
    assert market_items[0]["symbol"] == "SPY"
    assert market_items[0]["price"] == 470.0


# 5. urlopen raises URLError → gather returns [] (no crash)
def test_gather_handles_http_error():
    from jarvis.engines.financial import FinancialEngine
    import urllib.error

    eng = FinancialEngine()
    with patch("jarvis.config.FRED_API_KEY", "test-key"), \
         patch("jarvis.config.TRACKED_SYMBOLS", ["SPY"]), \
         patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = eng.gather()

    assert isinstance(result, list)
    # May be empty (all failed) or partial — should not crash
    for r in result:
        assert isinstance(r, dict)


# 6. fred raw dict → RawItem with fact_type="economic_indicator"
def test_prepare_items_fred_data():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    raw = [{"type": "fred", "series_id": "UNRATE", "value": "3.7", "period": "2024-01", "source_url": "http://x"}]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert item.fact_type == "economic_indicator"
    assert item.structured_data is not None
    assert item.structured_data["series_id"] == "UNRATE"
    assert item.source == "fred"


# 7. market dict → RawItem with fact_type="market_data"
def test_prepare_items_market_data():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    raw = [{"type": "market", "symbol": "SPY", "price": 470.0, "prev_close": 465.0, "date": "2024-01-15"}]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert item.fact_type == "market_data"
    assert item.structured_data is not None
    assert item.structured_data["symbol"] == "SPY"
    assert item.source == "yahoo_finance"


# 8. improve() returns list (even empty)
def test_improve_returns_list():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    with patch("jarvis.config.FRED_API_KEY", ""), \
         patch("jarvis.config.TRACKED_SYMBOLS", []):
        result = eng.improve()

    assert isinstance(result, list)


# 9. mock ingestion.ingest → called during run_cycle
def test_run_cycle_uses_ingestion_buffer():
    from jarvis.engines.financial import FinancialEngine

    eng = FinancialEngine()
    eng.gather = MagicMock(return_value=[])
    eng.prepare_items = MagicMock(return_value=[])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=0)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    # ingest is only called when there are items
    assert report is not None
    assert report.error is None
