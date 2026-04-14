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
    hs.is_budget_sensitive.return_value = False
    return hs


@pytest.fixture
def mock_context_engine():
    ce = MagicMock()
    ce.inject.side_effect = lambda domain, prompt: prompt
    return ce


def make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    from jarvis.specialists.finance_spec import FinanceSpec
    spec = FinanceSpec()
    spec._lake = mock_lake
    spec._blackboard = mock_blackboard
    spec._household_state = mock_household
    spec._context_engine = mock_context_engine
    return spec


def test_gather_reads_kb_facts(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    mock_lake.query_facts.return_value = [{"id": "f1", "content": "budget data", "domain": "finance"}]
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    result = spec.gather()
    assert any(item.get("content") == "budget data" for item in result)


def test_gather_reads_blackboard(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    mock_blackboard.read.return_value = [{"agent": "finance_specialist", "topic": "budget", "content": "alert"}]
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    result = spec.gather()
    assert any(item.get("content") == "alert" for item in result)


def test_analyze_returns_insights(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    gathered = [{"content": "spending data"}]
    with patch("jarvis.core._ask_ollama", return_value="[ALERT]: over budget this month"):
        insights = spec.analyze(gathered)
    assert len(insights) >= 1
    assert insights[0].content == "over budget this month"


def test_analyze_posts_alert_to_blackboard(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    gathered = [{"content": "spending data"}]
    with patch("jarvis.core._ask_ollama", return_value="[ALERT]: over budget this month"):
        spec.analyze(gathered)
    mock_blackboard.post.assert_called_once()
    call_kwargs = mock_blackboard.post.call_args
    assert call_kwargs[1]["urgency"] == "high" or (len(call_kwargs[0]) > 3 and call_kwargs[0][3] == "high")


def test_analyze_budget_sensitive_prepends_note(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    mock_household.is_budget_sensitive.return_value = True
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    gathered = [{"content": "spending data"}]
    captured_prompt = []

    def capture_prompt(prompt, model=None):
        captured_prompt.append(prompt)
        return "[TIP]: save money"

    with patch("jarvis.core._ask_ollama", side_effect=capture_prompt):
        spec.analyze(gathered)

    assert len(captured_prompt) == 1
    assert "BUDGET SENSITIVE" in captured_prompt[0]


def test_improve_posts_when_no_kb_data(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine):
    mock_lake.query_facts.return_value = []
    spec = make_spec(tmp_path, mock_lake, mock_blackboard, mock_household, mock_context_engine)
    spec.improve([])
    mock_blackboard.post.assert_called_once()
