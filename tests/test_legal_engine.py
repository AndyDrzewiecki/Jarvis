"""TDD RED — tests/test_legal_engine.py
Tests for LegalEngine (Engine 4).
"""
from __future__ import annotations
import json
import pytest
from unittest.mock import MagicMock, patch
from io import BytesIO


def _make_federal_register_response(docs=None):
    if docs is None:
        docs = [
            {
                "title": "New Overtime Wage Rule",
                "abstract": "Department of Labor updates overtime threshold for exempt employees.",
                "publication_date": "2024-01-15",
                "document_number": "2024-00123",
                "html_url": "https://www.federalregister.gov/documents/2024/01/15/2024-00123",
                "agencies": [{"name": "Department of Labor"}],
                "effective_on": "2024-03-01",
            }
        ]
    return json.dumps({"results": docs}).encode()


def _make_irs_rss_response(items=None):
    if items is None:
        items = [
            ("IRS Updates Tax Filing Deadline", "https://irs.gov/news/1", "Updated deadlines for 2024 tax year."),
        ]
    item_xml = ""
    for title, link, desc in items:
        item_xml += f"""
        <item>
            <title>{title}</title>
            <link>{link}</link>
            <description>{desc}</description>
        </item>"""
    xml = f"""<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>IRS News</title>{item_xml}
  </channel>
</rss>""".encode()
    return xml


def _make_urlopen_mock(response_bytes: bytes):
    resp = MagicMock()
    resp.read.return_value = response_bytes
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# 1. LegalEngine in ENGINE_REGISTRY
def test_legal_engine_registered():
    import jarvis.engines.legal  # noqa: F401
    from jarvis.engines import ENGINE_REGISTRY
    names = [cls.name for cls in ENGINE_REGISTRY if hasattr(cls, "name")]
    assert "legal_engine" in names


# 2. mock urlopen with Federal Register JSON → gather returns doc dicts
def test_gather_federal_register_mock():
    from jarvis.engines.legal import LegalEngine

    eng = LegalEngine()
    resp_mock = _make_urlopen_mock(_make_federal_register_response())

    with patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    fed_items = [r for r in result if r.get("type") == "federal_register"]
    assert len(fed_items) >= 1
    assert "Overtime" in fed_items[0]["title"]


# 3. mock urlopen with IRS RSS XML → gather returns items
def test_gather_irs_rss_mock():
    from jarvis.engines.legal import LegalEngine

    eng = LegalEngine()
    resp_mock = _make_urlopen_mock(_make_irs_rss_response())

    with patch("urllib.request.urlopen", return_value=resp_mock):
        result = eng.gather()

    irs_items = [r for r in result if r.get("type") == "irs"]
    assert len(irs_items) >= 1
    assert "IRS" in irs_items[0]["title"]


# 4. urlopen raises URLError → gather returns [] (no crash)
def test_gather_handles_http_error():
    from jarvis.engines.legal import LegalEngine
    import urllib.error

    eng = LegalEngine()

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        result = eng.gather()

    assert isinstance(result, list)


# 5. federal_register doc dict → RawItem with fact_type="regulatory_change", jurisdiction="federal"
def test_prepare_items_federal_register():
    from jarvis.engines.legal import LegalEngine
    from jarvis.ingestion import RawItem

    eng = LegalEngine()
    raw = [
        {
            "type": "federal_register",
            "title": "New Overtime Wage Rule",
            "abstract": "Department of Labor updates overtime thresholds.",
            "publication_date": "2024-01-15",
            "document_number": "2024-00123",
            "document_url": "https://federalregister.gov/doc/2024-00123",
            "agencies": "Department of Labor",
            "effective_on": "2024-03-01",
        }
    ]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RawItem)
    assert item.fact_type == "regulatory_change"
    assert item.structured_data is not None
    assert item.structured_data.get("jurisdiction") == "federal"
    assert item.source == "federal_register"


# 6. irs dict → RawItem with domain="legal", jurisdiction="federal", domain_field="tax"
def test_prepare_items_irs():
    from jarvis.engines.legal import LegalEngine
    from jarvis.ingestion import RawItem

    eng = LegalEngine()
    raw = [
        {
            "type": "irs",
            "title": "IRS Announces 2024 Tax Deadlines",
            "url": "https://irs.gov/news/1",
            "description": "Updated tax filing deadlines for the 2024 tax year.",
        }
    ]
    items = eng.prepare_items(raw)

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, RawItem)
    assert item.domain == "legal"
    assert item.structured_data is not None
    assert item.structured_data.get("jurisdiction") == "federal"
    assert item.structured_data.get("domain") == "tax"
    assert item.source == "irs"


# 7. improve() returns list
def test_improve_returns_list():
    from jarvis.engines.legal import LegalEngine

    eng = LegalEngine()
    # Mock the engine_store to avoid actual DB
    mock_store = MagicMock()
    mock_store.query.return_value = []
    eng._engine_store = mock_store

    result = eng.improve()

    assert isinstance(result, list)


# 8. mock ingestion.ingest → called during run_cycle when items exist
def test_run_cycle_uses_ingestion_buffer():
    from jarvis.engines.legal import LegalEngine
    from jarvis.ingestion import RawItem

    eng = LegalEngine()

    dummy_item = RawItem(
        content="Federal regulation: New Overtime Wage Rule.",
        source="federal_register",
        fact_type="regulatory_change",
        domain="legal",
    )
    eng.gather = MagicMock(return_value=[{"type": "federal_register", "title": "Test Rule"}])
    eng.prepare_items = MagicMock(return_value=[dummy_item])
    eng.improve = MagicMock(return_value=[])

    mock_ingest = MagicMock()
    mock_ingest.ingest.return_value = MagicMock(accepted=1)
    eng._ingestion = mock_ingest

    with patch("jarvis.agent_memory.log_decision"):
        report = eng.run_cycle()

    mock_ingest.ingest.assert_called_once()
    assert report is not None
    assert report.error is None


# 9. analyze posts tax_alert when LLM returns [ALERT_TYPE]: tax_alert
def test_analyze_posts_tax_alert():
    from jarvis.engines.legal import LegalEngine

    eng = LegalEngine()

    # Mock blackboard
    mock_blackboard = MagicMock()
    eng._blackboard = mock_blackboard

    gathered = [
        {
            "type": "irs",
            "title": "IRS: File by Oct 15",
            "url": "https://irs.gov/news/1",
            "description": "Important: tax filing deadline is Oct 15, 2024.",
        }
    ]

    llm_response = (
        "[IMPACT]: Taxpayers must file by Oct 15 to avoid penalties\n"
        "[ACTION]: file by Oct 15\n"
        "[DOMAIN]: tax\n"
        "[ALERT_TYPE]: tax_alert\n"
    )

    with patch("jarvis.core._ask_ollama", return_value=llm_response), \
         patch("jarvis.config.FALLBACK_MODEL", "qwen2.5:0.5b"):
        insights = eng.analyze(gathered)

    mock_blackboard.post.assert_called_once()
    call_kwargs = mock_blackboard.post.call_args
    assert call_kwargs[1]["topic"] == "tax_alert" or (
        len(call_kwargs[0]) > 1 and call_kwargs[0][1] == "tax_alert"
    )
