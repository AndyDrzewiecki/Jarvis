"""Tests for ReceiptIngestAdapter — mocks the external receipt_ingest module."""
from __future__ import annotations
import os
import pytest
from unittest.mock import patch, MagicMock

from jarvis.adapters.receipt_ingest import ReceiptIngestAdapter


@pytest.fixture
def adapter():
    return ReceiptIngestAdapter()


def _make_mock_module(tmp_path):
    """Build a minimal mock of the external receipt_ingest module."""
    receipts_dir = str(tmp_path / "receipts")
    pricebook_path = str(tmp_path / "pricebook.json")

    mod = MagicMock()
    mod.RECEIPTS_DIR = receipts_dir
    mod.PRICEBOOK_PATH = pricebook_path

    # normalize_item_key: lowercase, replace spaces with underscores
    mod.normalize_item_key.side_effect = lambda s: s.lower().replace(" ", "_")

    # load_json returns a dict with items
    mod.load_json.return_value = {"items": {}}

    # save_json: no-op (side_effect to capture args if needed)
    mod.save_json.return_value = None

    # ingest: no-op
    mod.ingest.return_value = None

    return mod


# ── metadata ──────────────────────────────────────────────────────────────────

def test_adapter_name(adapter):
    assert adapter.name == "receipt_ingest"


def test_adapter_capabilities(adapter):
    assert "ingest_text" in adapter.capabilities
    assert "update_pricebook" in adapter.capabilities
    assert "list_recent" in adapter.capabilities


# ── ingest_text ───────────────────────────────────────────────────────────────

def test_ingest_text_success(adapter, tmp_path):
    mock_mod = _make_mock_module(tmp_path)
    with patch.object(adapter, "_import_module", return_value=mock_mod):
        result = adapter.run("ingest_text", {"text": "MILK 2 @ 1.99", "store": "walmart"})
    assert result.success is True
    assert "walmart" in result.text
    mock_mod.ingest.assert_called_once_with("walmart")


def test_ingest_text_writes_file_to_receipts_dir(adapter, tmp_path):
    mock_mod = _make_mock_module(tmp_path)
    receipts_dir = str(tmp_path / "receipts")
    mock_mod.RECEIPTS_DIR = receipts_dir

    with patch.object(adapter, "_import_module", return_value=mock_mod):
        adapter.run("ingest_text", {"text": "EGG 1 @ 3.49", "store": "aldi"})

    # A .txt file should have been created in receipts_dir
    assert os.path.exists(receipts_dir)
    files = [f for f in os.listdir(receipts_dir) if f.endswith(".txt")]
    assert len(files) == 1
    content = open(os.path.join(receipts_dir, files[0])).read()
    assert "EGG" in content


def test_ingest_text_missing_text_param(adapter):
    result = adapter.run("ingest_text", {"store": "walmart"})
    assert result.success is False
    assert "text" in result.text.lower()


def test_ingest_text_module_not_found(adapter):
    with patch.object(adapter, "_import_module", side_effect=FileNotFoundError("not found")):
        result = adapter.run("ingest_text", {"text": "MILK 1.99", "store": "walmart"})
    assert result.success is False
    assert "Error" in result.text


# ── update_pricebook ──────────────────────────────────────────────────────────

def test_update_pricebook_success(adapter, tmp_path):
    mock_mod = _make_mock_module(tmp_path)
    items = [
        {"item": "Whole Milk", "price": 2.99, "store": "walmart"},
        {"item": "Eggs", "price": 3.49, "store": "walmart"},
    ]
    with patch.object(adapter, "_import_module", return_value=mock_mod):
        result = adapter.run("update_pricebook", {"items": items})
    assert result.success is True
    assert "2" in result.text  # 2 entries updated
    mock_mod.save_json.assert_called_once()


def test_update_pricebook_missing_items(adapter):
    result = adapter.run("update_pricebook", {})
    assert result.success is False
    assert "items" in result.text.lower()


def test_update_pricebook_skips_items_without_price(adapter, tmp_path):
    mock_mod = _make_mock_module(tmp_path)
    items = [
        {"item": "Milk"},        # no price
        {"item": "Bread", "price": 1.99, "store": "target"},
    ]
    with patch.object(adapter, "_import_module", return_value=mock_mod):
        result = adapter.run("update_pricebook", {"items": items})
    assert result.success is True
    assert result.data["updated"] == 1


# ── list_recent ───────────────────────────────────────────────────────────────

def test_list_recent_no_receipts_dir(adapter, tmp_path):
    mock_mod = _make_mock_module(tmp_path)
    mock_mod.RECEIPTS_DIR = str(tmp_path / "nonexistent")
    with patch.object(adapter, "_import_module", return_value=mock_mod):
        result = adapter.run("list_recent", {})
    assert result.success is True
    assert result.data["receipts"] == []


def test_list_recent_returns_txt_files(adapter, tmp_path):
    mock_mod = _make_mock_module(tmp_path)
    receipts_dir = str(tmp_path / "receipts")
    os.makedirs(receipts_dir)
    for name in ["receipt_a.txt", "receipt_b.txt", "ignore.json"]:
        open(os.path.join(receipts_dir, name), "w").close()
    mock_mod.RECEIPTS_DIR = receipts_dir

    with patch.object(adapter, "_import_module", return_value=mock_mod):
        result = adapter.run("list_recent", {"n": 5})
    assert result.success is True
    assert len(result.data["receipts"]) == 2
    assert all(f.endswith(".txt") for f in result.data["receipts"])


# ── unknown capability ────────────────────────────────────────────────────────

def test_unknown_capability(adapter):
    result = adapter.run("teleport", {})
    assert result.success is False
    assert "Unknown capability" in result.text
