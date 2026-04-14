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
def mock_household():
    hs = MagicMock()
    hs.current.return_value = {"primary": "normal"}
    return hs


@pytest.fixture
def mock_context_engine():
    ce = MagicMock()
    ce.inject.side_effect = lambda domain, prompt: prompt
    return ce


def make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    from jarvis.specialists.calendar_spec import CalendarSpec
    spec = CalendarSpec()
    spec._lake = mock_lake
    spec._blackboard = mock_blackboard
    spec._household_state = mock_household
    spec._context_engine = mock_context_engine
    return spec


def test_gather_reads_kb_facts(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    mock_lake.query_facts.return_value = [{"id": "c1", "content": "dentist appt", "domain": "calendar"}]
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    result = spec.gather()
    assert any(item.get("content") == "dentist appt" for item in result)


def test_gather_google_sync_skipped_when_unconfigured(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    with patch("jarvis.integrations.google.GoogleSync.is_configured", return_value=False):
        result = spec.gather()
    # Should not crash and should return a list
    assert isinstance(result, list)


def test_analyze_returns_insights(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    gathered = [{"content": "dentist 3pm, meeting 3pm"}]
    with patch("jarvis.core._ask_ollama", return_value="[CONFLICT]: dentist and meeting overlap"):
        insights = spec.analyze(gathered)
    assert len(insights) >= 1
    assert "dentist and meeting overlap" in insights[0].content


def test_analyze_posts_conflict_to_blackboard(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    gathered = [{"content": "scheduling data"}]
    with patch("jarvis.core._ask_ollama", return_value="[CONFLICT]: overlap at 3pm"):
        spec.analyze(gathered)
    mock_blackboard.post.assert_called_once()
    call_kwargs = mock_blackboard.post.call_args
    # Check urgency is "high" — may be passed as kwarg or positional arg
    kwargs = call_kwargs.kwargs if hasattr(call_kwargs, "kwargs") else call_kwargs[1]
    args = call_kwargs.args if hasattr(call_kwargs, "args") else call_kwargs[0]
    urgency = kwargs.get("urgency") or (args[3] if len(args) > 3 else None)
    assert urgency == "high"


def test_improve_posts_when_no_data(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    mock_lake.query_facts.return_value = []
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    spec.improve([])
    mock_blackboard.post.assert_called_once()
