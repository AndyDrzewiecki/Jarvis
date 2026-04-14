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


def make_spec(tmp_path, mock_lake, mock_blackboard, mock_context_engine):
    from jarvis.specialists.home_spec import HomeSpec
    spec = HomeSpec()
    spec._lake = mock_lake
    spec._blackboard = mock_blackboard
    spec._context_engine = mock_context_engine
    return spec


def test_gather_reads_kb_facts(tmp_path, mock_lake, mock_blackboard, mock_context_engine):
    mock_lake.query_facts.return_value = [{"id": "h1", "content": "HVAC filter due", "domain": "home"}]
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_context_engine)
    result = spec.gather()
    assert any(item.get("content") == "HVAC filter due" for item in result)


def test_gather_reads_blackboard(tmp_path, mock_lake, mock_blackboard, mock_context_engine):
    mock_blackboard.read.return_value = [{"agent": "weather_specialist", "topic": "weather", "content": "storm coming"}]
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_context_engine)
    result = spec.gather()
    assert any(item.get("content") == "storm coming" for item in result)


def test_analyze_returns_insights(tmp_path, mock_lake, mock_blackboard, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_context_engine)
    gathered = [{"content": "HVAC filter has not been replaced in 6 months"}]
    with patch("jarvis.core._ask_ollama", return_value="[URGENT]: HVAC filter replacement needed"):
        insights = spec.analyze(gathered)
    assert len(insights) >= 1
    assert "HVAC filter replacement needed" in insights[0].content


def test_analyze_posts_urgent_to_blackboard(tmp_path, mock_lake, mock_blackboard, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_context_engine)
    gathered = [{"content": "maintenance data"}]
    with patch("jarvis.core._ask_ollama", return_value="[URGENT]: fix roof leak immediately"):
        spec.analyze(gathered)
    mock_blackboard.post.assert_called_once()
    call_kwargs = mock_blackboard.post.call_args
    urgency = call_kwargs[1].get("urgency") or (call_kwargs[0][3] if len(call_kwargs[0]) > 3 else None)
    assert urgency == "high"


def test_improve_posts_when_no_data(tmp_path, mock_lake, mock_blackboard, mock_context_engine):
    mock_lake.query_facts.return_value = []
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_context_engine)
    spec.improve([])
    mock_blackboard.post.assert_called_once()
