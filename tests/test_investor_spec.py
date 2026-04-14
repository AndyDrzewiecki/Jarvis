from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


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


@pytest.fixture
def mock_blackboard():
    bb = MagicMock()
    bb.read.return_value = []
    return bb


@pytest.fixture
def mock_context_engine():
    ce = MagicMock()
    ce.inject.side_effect = lambda domain, prompt: prompt
    return ce


def make_spec(mock_lake, mock_blackboard, mock_context_engine):
    from jarvis.specialists.investor_spec import InvestorSpec
    spec = InvestorSpec()
    spec._lake = mock_lake
    spec._blackboard = mock_blackboard
    spec._context_engine = mock_context_engine
    return spec


def test_gather_calls_investor_adapter(mock_lake, mock_blackboard, mock_context_engine):
    spec = make_spec(mock_lake, mock_blackboard, mock_context_engine)
    mock_result = MagicMock()
    mock_result.success = True
    mock_result.text = "Market brief: S&P up 1%"

    mock_adapter = MagicMock()
    mock_adapter.safe_run.return_value = mock_result

    with patch("jarvis.adapters.investor.InvestorAdapter", return_value=mock_adapter):
        result = spec.gather()

    assert any(item.get("content", "").startswith("Market brief") for item in result)


def test_gather_adapter_failure_graceful(mock_lake, mock_blackboard, mock_context_engine):
    spec = make_spec(mock_lake, mock_blackboard, mock_context_engine)
    with patch("jarvis.adapters.investor.InvestorAdapter", side_effect=Exception("adapter broken")):
        result = spec.gather()
    # Should not crash and should return empty or partial list
    assert isinstance(result, list)


def test_analyze_returns_insights(mock_lake, mock_blackboard, mock_context_engine):
    spec = make_spec(mock_lake, mock_blackboard, mock_context_engine)
    gathered = [{"content": "market data today"}]
    with patch("jarvis.core._ask_ollama", return_value="[RISK]: volatility is high today"):
        insights = spec.analyze(gathered)
    assert len(insights) >= 1
    assert "volatility is high today" in insights[0].content


def test_analyze_posts_risk_to_blackboard(mock_lake, mock_blackboard, mock_context_engine):
    spec = make_spec(mock_lake, mock_blackboard, mock_context_engine)
    gathered = [{"content": "market data"}]
    with patch("jarvis.core._ask_ollama", return_value="[RISK]: market crash risk elevated"):
        spec.analyze(gathered)
    mock_blackboard.post.assert_called_once()
    call_kwargs = mock_blackboard.post.call_args
    urgency = call_kwargs[1].get("urgency") or (call_kwargs[0][3] if len(call_kwargs[0]) > 3 else None)
    assert urgency == "high"


def test_improve_posts_when_no_data(mock_lake, mock_blackboard, mock_context_engine):
    mock_lake.query_facts.return_value = []
    spec = make_spec(mock_lake, mock_blackboard, mock_context_engine)
    spec.improve([])
    mock_blackboard.post.assert_called_once()
