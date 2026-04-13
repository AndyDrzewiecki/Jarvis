from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))


@pytest.fixture
def mock_lake():
    lake = MagicMock()
    lake.recent_by_domain.return_value = {}
    lake.store_fact.return_value = "fact-123"
    lake.query_facts.return_value = []
    return lake


def test_grocery_spec_attributes():
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    assert spec.name == "grocery_specialist"
    assert spec.domain == "grocery"
    assert "*/4" in spec.schedule


def test_gather_returns_list(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    spec._lake = mock_lake
    result = spec.gather()
    assert isinstance(result, list)


def test_gather_includes_kb_prices(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    # Return a fresh KB price fact (updated_at = now)
    now = datetime.now(timezone.utc).isoformat()
    mock_lake.query_facts.side_effect = lambda **kwargs: (
        [{"id": "p1", "summary": "chicken $2/lb", "updated_at": now, "confidence": 0.9}]
        if kwargs.get("fact_type") == "price" else []
    )
    spec = GrocerySpec()
    spec._lake = mock_lake
    data = spec.gather()
    assert any(d.get("summary") == "chicken $2/lb" for d in data)


def test_gather_detects_stale_data(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    # Return stale data (49 hours old)
    stale_ts = (datetime.now(timezone.utc) - timedelta(hours=49)).isoformat()
    mock_lake.query_facts.return_value = [
        {"id": "p1", "summary": "old price", "updated_at": stale_ts, "confidence": 0.5}
    ]
    spec = GrocerySpec()
    spec._lake = mock_lake
    # _gather_from_adapter will be called; mock it
    with patch.object(spec, "_gather_from_adapter", return_value=[{"source": "adapter", "content": "fresh"}]) as mock_fresh:
        spec.gather()
        mock_fresh.assert_called_once()


def test_gather_fresh_data_skips_adapter(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    now = datetime.now(timezone.utc).isoformat()
    mock_lake.query_facts.return_value = [
        {"id": "p1", "summary": "fresh price", "updated_at": now, "confidence": 0.9}
    ]
    spec = GrocerySpec()
    spec._lake = mock_lake
    with patch.object(spec, "_gather_from_adapter") as mock_fresh:
        spec.gather()
        mock_fresh.assert_not_called()


def test_analyze_returns_insights(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    spec._lake = mock_lake
    raw = [{"source": "kb_price", "summary": "chicken $2/lb"}]
    with patch("jarvis.core._ask_ollama", return_value="[PRICE] Chicken is cheaper this week.\n[INVENTORY] Running low on milk."):
        insights = spec.analyze(raw, {})
    assert len(insights) == 2
    assert insights[0].fact_type == "price"
    assert insights[1].fact_type == "inventory"


def test_analyze_empty_data_returns_no_insights(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    spec._lake = mock_lake
    insights = spec.analyze([], {})
    assert insights == []


def test_analyze_llm_failure_returns_empty(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    spec._lake = mock_lake
    with patch("jarvis.core._ask_ollama", side_effect=Exception("LLM down")):
        insights = spec.analyze([{"x": 1}], {})
    assert insights == []


def test_improve_returns_list(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    spec._lake = mock_lake
    result = spec.improve()
    assert isinstance(result, list)


def test_improve_flags_low_confidence_facts(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    now = datetime.now(timezone.utc).isoformat()
    mock_lake.query_facts.return_value = [
        {"id": "f1", "summary": "old price data", "confidence": 0.3, "updated_at": now}
    ]
    spec = GrocerySpec()
    spec._lake = mock_lake
    gaps = spec.improve()
    assert len(gaps) >= 1
    assert any("0.30" in g or "Low confidence" in g for g in gaps)


def test_full_run_cycle(mock_lake):
    from jarvis.specialists.grocery_spec import GrocerySpec
    spec = GrocerySpec()
    spec._lake = mock_lake
    spec._bus = MagicMock()
    with patch("jarvis.core._ask_ollama", return_value="[MEAL] Try chicken stir-fry this week."):
        report = spec.run_cycle()
    assert report.specialist == "grocery_specialist"
    assert report.error is None


def test_grocery_spec_registered():
    from jarvis.specialists import SPECIALIST_REGISTRY
    names = [cls.name for cls in SPECIALIST_REGISTRY]
    assert "grocery_specialist" in names
