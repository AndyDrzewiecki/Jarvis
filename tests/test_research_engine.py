"""TDD RED — tests/test_research_engine.py
Tests for ResearchEngine.
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch


_ARXIV_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Advances in Large Language Models for Agent Systems</title>
    <summary>This paper presents advances in LLM-based agent architectures for autonomous systems.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <author><name>Alice Researcher</name></author>
    <author><name>Bob Scientist</name></author>
    <category term="cs.AI" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>"""


def _make_github_response():
    return json.dumps({
        "items": [
            {
                "html_url": "https://github.com/test/llm-agents",
                "full_name": "test/llm-agents",
                "description": "A framework for LLM-based agents",
                "stargazers_count": 5000,
                "language": "Python",
                "topics": ["llm", "agents"],
                "pushed_at": "2024-01-15T10:00:00Z",
            }
        ]
    }).encode()


def _make_hf_response():
    return json.dumps([
        {
            "id": "meta-llama/Llama-2-7b",
            "tags": ["text-generation", "pytorch"],
            "lastModified": "2024-01-15T10:00:00Z",
        }
    ]).encode()


# 1. ResearchEngine in ENGINE_REGISTRY
def test_research_engine_registered():
    import jarvis.engines.research  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    names = [cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")]
    assert "research_engine" in names


# 2. mock urlopen with Atom XML → gather returns paper dicts
def test_gather_arxiv_mock():
    from jarvis.engines.research import ResearchEngine

    eng = ResearchEngine()
    resp_mock = MagicMock()
    resp_mock.read.return_value = _ARXIV_SAMPLE
    resp_mock.__enter__ = lambda s: s
    resp_mock.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=resp_mock), \
         patch("jarvis.config.GITHUB_TOKEN", ""):
        result = eng._fetch_arxiv_papers()

    assert len(result) >= 1
    paper = result[0]
    assert paper["type"] == "paper"
    assert "title" in paper
    assert "abstract" in paper
    assert "2401" in paper.get("arxiv_id", "")


# 3. mock urlopen with GitHub JSON → gather returns repo dicts
def test_gather_github_mock():
    from jarvis.engines.research import ResearchEngine

    eng = ResearchEngine()
    resp_mock = MagicMock()
    resp_mock.read.return_value = _make_github_response()
    resp_mock.__enter__ = lambda s: s
    resp_mock.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=resp_mock), \
         patch("jarvis.config.GITHUB_TOKEN", ""):
        result = eng._fetch_github_repos()

    assert len(result) == 1
    repo = result[0]
    assert repo["type"] == "repo"
    assert repo["name"] == "test/llm-agents"
    assert repo["stars"] == 5000


# 4. urlopen raises → gather returns [] (no crash)
def test_gather_handles_http_error():
    from jarvis.engines.research import ResearchEngine
    import urllib.error

    eng = ResearchEngine()
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")), \
         patch("jarvis.config.GITHUB_TOKEN", ""):
        result = eng.gather()

    assert isinstance(result, list)


# 5. paper dict → RawItem with fact_type="research_paper"
def test_prepare_items_paper():
    from jarvis.engines.research import ResearchEngine

    eng = ResearchEngine()
    raw = [{
        "type": "paper",
        "arxiv_id": "2401.12345",
        "title": "Test Paper Title",
        "authors": "Alice, Bob",
        "abstract": "This is a test abstract about machine learning and agents.",
        "published_date": "2024-01-15",
        "categories": "cs.AI,cs.LG",
    }]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert item.fact_type == "research_paper"
    assert item.structured_data is not None
    assert item.structured_data["title"] == "Test Paper Title"
    assert "abstract" in item.structured_data
    assert item.source == "arxiv"


# 6. repo dict → RawItem with fact_type="tracked_repo"
def test_prepare_items_repo():
    from jarvis.engines.research import ResearchEngine

    eng = ResearchEngine()
    raw = [{
        "type": "repo",
        "github_url": "https://github.com/test/repo",
        "name": "test/repo",
        "description": "A test repo",
        "stars": 3000,
        "language": "Python",
        "topics": "llm,agents",
        "last_commit": "2024-01-15T10:00:00Z",
    }]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert item.fact_type == "tracked_repo"
    assert item.structured_data is not None
    assert item.structured_data["github_url"] == "https://github.com/test/repo"
    assert item.source == "github"


# 7. model dict → RawItem with fact_type="model_registry"
def test_prepare_items_model():
    from jarvis.engines.research import ResearchEngine

    eng = ResearchEngine()
    raw = [{
        "type": "model",
        "hf_model_id": "meta-llama/Llama-2-7b",
        "name": "meta-llama/Llama-2-7b",
        "tags": "text-generation,pytorch",
        "last_modified": "2024-01-15T10:00:00Z",
    }]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert item.fact_type == "model_registry"
    assert item.structured_data is not None
    assert item.structured_data["hf_model_id"] == "meta-llama/Llama-2-7b"
    assert item.source == "huggingface"


# 8. improve() returns list
def test_improve_returns_list():
    from jarvis.engines.research import ResearchEngine

    eng = ResearchEngine()
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    result = eng.improve()
    assert isinstance(result, list)


# 9. mock ingestion.ingest → called during run_cycle when items exist
def test_run_cycle_uses_ingestion_buffer():
    from jarvis.engines.research import ResearchEngine
    from jarvis.ingestion import RawItem

    eng = ResearchEngine()
    raw_items = [RawItem(content="test paper content", source="arxiv", fact_type="research_paper")]
    eng.gather = MagicMock(return_value=[{"type": "paper", "title": "T"}])
    eng.prepare_items = MagicMock(return_value=raw_items)
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=1)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    mock_ingest.ingest.assert_called_once()
    assert report.insights == 1
