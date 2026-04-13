"""Tests for BaseAdapter, AdapterResult, stub adapters, and decision memory integration."""
from __future__ import annotations
import pytest
import jarvis.agent_memory as am
from jarvis.adapters.base import BaseAdapter, AdapterResult
from jarvis.adapters.weather import WeatherAdapter
from jarvis.adapters.stubs import (
    CalendarAdapter, EmailAdapter,
    FinanceAdapter, HomeAdapter, MusicAdapter, NewsAdapter,
    SalesAgentAdapter,
)


@pytest.fixture(autouse=True)
def tmp_decisions(tmp_path, monkeypatch):
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))


def test_adapter_result_to_dict():
    r = AdapterResult(success=True, text="hello", data={"k": "v"}, adapter="test")
    d = r.to_dict()
    assert d["success"] is True
    assert d["text"] == "hello"
    assert d["data"] == {"k": "v"}
    assert d["adapter"] == "test"


def test_base_adapter_safe_run_catches_exception():
    class BrokenAdapter(BaseAdapter):
        name = "broken"
        def run(self, capability, params):
            raise ValueError("boom")

    a = BrokenAdapter()
    result = a.safe_run("anything", {})
    assert result.success is False
    assert "boom" in result.text


def test_base_adapter_run_raises_not_implemented():
    a = BaseAdapter()
    with pytest.raises(NotImplementedError):
        a.run("x", {})


@pytest.mark.parametrize("AdapterClass", [
    CalendarAdapter, EmailAdapter,
    FinanceAdapter, HomeAdapter, MusicAdapter, NewsAdapter,
])
def test_stub_adapters_return_not_implemented(AdapterClass):
    a = AdapterClass()
    result = a.safe_run(a.capabilities[0], {})
    assert result.success is False
    assert "Not yet implemented" in result.text
    assert result.adapter == a.name


@pytest.mark.parametrize("AdapterClass", [
    CalendarAdapter, EmailAdapter,
    FinanceAdapter, HomeAdapter, MusicAdapter, NewsAdapter,
])
def test_stub_adapters_have_name_description_capabilities(AdapterClass):
    a = AdapterClass()
    assert a.name
    assert a.description
    assert len(a.capabilities) > 0


def test_weather_adapter_has_live_capabilities():
    """WeatherAdapter is now a live adapter (not a stub)."""
    a = WeatherAdapter()
    assert a.name == "weather"
    assert "current" in a.capabilities
    assert "forecast" in a.capabilities
    assert "alerts" in a.capabilities


def test_adapter_result_defaults():
    r = AdapterResult(success=True, text="ok")
    assert r.data == {}
    assert r.adapter == ""


# ── stub adapter additions ────────────────────────────────────────────────────

def test_sales_agent_has_metadata():
    a = SalesAgentAdapter()
    assert a.name == "sales_agent"
    assert a.description
    assert "scrape_all" in a.capabilities
    assert "generate_scrapers" in a.capabilities
    assert "scraper_status" in a.capabilities


# ── decision memory integration ───────────────────────────────────────────────

def test_safe_run_logs_success_decision():
    class OkAdapter(BaseAdapter):
        name = "ok_adapter"
        def run(self, capability, params):
            return AdapterResult(success=True, text="done", adapter=self.name)

    a = OkAdapter()
    a.safe_run("do_thing", {})

    decisions = am.recent_decisions(n=10)
    assert any(d["agent"] == "ok_adapter" for d in decisions)
    match = next(d for d in decisions if d["agent"] == "ok_adapter")
    assert match["outcome"] == "success"
    assert match["capability"] == "do_thing"


def test_safe_run_logs_failure_decision():
    class FailAdapter(BaseAdapter):
        name = "fail_adapter"
        def run(self, capability, params):
            raise RuntimeError("exploded")

    a = FailAdapter()
    a.safe_run("explode", {})

    decisions = am.recent_decisions(n=10)
    match = next(d for d in decisions if d["agent"] == "fail_adapter")
    assert match["outcome"] == "failure"
    assert "exploded" in match["reasoning"]


def test_safe_run_logs_linked_message_id():
    class TraceAdapter(BaseAdapter):
        name = "trace_adapter"
        def run(self, capability, params):
            return AdapterResult(success=True, text="traced", adapter=self.name)

    a = TraceAdapter()
    a.safe_run("trace", {}, linked_message_id="msg-xyz-456")

    decisions = am.recent_decisions(n=10)
    match = next(d for d in decisions if d["agent"] == "trace_adapter")
    assert match["linked_message_id"] == "msg-xyz-456"


def test_safe_run_logs_duration_ms():
    class FastAdapter(BaseAdapter):
        name = "fast_adapter"
        def run(self, capability, params):
            return AdapterResult(success=True, text="fast", adapter=self.name)

    a = FastAdapter()
    a.safe_run("go", {})

    decisions = am.recent_decisions(n=10)
    match = next(d for d in decisions if d["agent"] == "fast_adapter")
    assert match["duration_ms"] is not None
    assert match["duration_ms"] >= 0
