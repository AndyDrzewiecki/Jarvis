from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO


@pytest.fixture(autouse=True)
def isolate_db(tmp_path, monkeypatch):
    import jarvis.agent_memory as am
    monkeypatch.setattr(am, "DB_PATH", str(tmp_path / "decisions.db"))
    am._inited.discard(str(tmp_path / "decisions.db"))


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


def make_spec(mock_blackboard, mock_context_engine):
    from jarvis.specialists.news_spec import NewsSpec
    spec = NewsSpec()
    spec._blackboard = mock_blackboard
    spec._context_engine = mock_context_engine
    return spec


def test_gather_returns_empty_when_no_feeds_configured(mock_blackboard, mock_context_engine, monkeypatch):
    import jarvis.config as config
    monkeypatch.setattr(config, "NEWS_FEED_URLS", [])
    spec = make_spec(mock_blackboard, mock_context_engine)
    result = spec.gather()
    assert result == []


RSS_XML = b"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>Market rises 2%</title>
      <link>http://example.com/1</link>
      <description>Stock market had a great day</description>
    </item>
    <item>
      <title>Local festival this weekend</title>
      <link>http://example.com/2</link>
      <description>Community event downtown</description>
    </item>
  </channel>
</rss>"""


def test_gather_parses_rss_feed(mock_blackboard, mock_context_engine, monkeypatch):
    import jarvis.config as config
    monkeypatch.setattr(config, "NEWS_FEED_URLS", ["http://example.com/feed"])

    mock_response = MagicMock()
    mock_response.read.return_value = RSS_XML
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    spec = make_spec(mock_blackboard, mock_context_engine)
    with patch("urllib.request.urlopen", return_value=mock_response):
        result = spec.gather()

    assert len(result) == 2
    titles = [item["title"] for item in result]
    assert "Market rises 2%" in titles
    assert "Local festival this weekend" in titles


def test_gather_handles_fetch_error(mock_blackboard, mock_context_engine, monkeypatch):
    import jarvis.config as config
    monkeypatch.setattr(config, "NEWS_FEED_URLS", ["http://example.com/broken"])

    spec = make_spec(mock_blackboard, mock_context_engine)
    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        result = spec.gather()

    assert result == []


def test_analyze_returns_insights(mock_blackboard, mock_context_engine, monkeypatch):
    import jarvis.config as config
    monkeypatch.setattr(config, "NEWS_FEED_URLS", [])
    spec = make_spec(mock_blackboard, mock_context_engine)
    gathered = [{"title": "Stocks rise", "description": "market up 2%"}]
    with patch("jarvis.core._ask_ollama", return_value="[FINANCE]: market up 2% today"):
        insights = spec.analyze(gathered)
    assert len(insights) >= 1
    assert "finance" in insights[0].tags


def test_analyze_posts_alert_to_blackboard(mock_blackboard, mock_context_engine, monkeypatch):
    import jarvis.config as config
    monkeypatch.setattr(config, "NEWS_FEED_URLS", [])
    spec = make_spec(mock_blackboard, mock_context_engine)
    gathered = [{"title": "Breaking news", "description": "urgent situation"}]
    with patch("jarvis.core._ask_ollama", return_value="[ALERT]: urgent breaking news"):
        spec.analyze(gathered)
    mock_blackboard.post.assert_called_once()
    call_kwargs = mock_blackboard.post.call_args
    urgency = call_kwargs[1].get("urgency") or (call_kwargs[0][3] if len(call_kwargs[0]) > 3 else None)
    assert urgency == "urgent"


def test_improve_posts_when_no_feeds(mock_blackboard, mock_context_engine, monkeypatch):
    import jarvis.config as config
    monkeypatch.setattr(config, "NEWS_FEED_URLS", [])
    spec = make_spec(mock_blackboard, mock_context_engine)
    spec.improve([])
    mock_blackboard.post.assert_called_once()
