from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock


def test_is_configured_false_when_no_file(tmp_path):
    from jarvis.integrations.google import GoogleSync
    gs = GoogleSync(credentials_path=str(tmp_path / "nonexistent_creds.json"))
    assert gs.is_configured() is False


def test_is_configured_true_when_file_exists(tmp_path):
    creds_file = tmp_path / "google_credentials.json"
    creds_file.write_text('{"type": "authorized_user"}')
    from jarvis.integrations.google import GoogleSync
    gs = GoogleSync(credentials_path=str(creds_file))
    assert gs.is_configured() is True


def test_sync_calendar_returns_empty_when_not_configured(tmp_path):
    from jarvis.integrations.google import GoogleSync
    gs = GoogleSync(credentials_path=str(tmp_path / "nonexistent.json"))
    result = gs.sync_calendar()
    assert result == []


def test_sync_sheets_returns_empty_when_not_configured(tmp_path):
    from jarvis.integrations.google import GoogleSync
    gs = GoogleSync(credentials_path=str(tmp_path / "nonexistent.json"))
    result = gs.sync_sheets("some-sheet-id")
    assert result == []


def test_sync_calendar_handles_import_error(tmp_path):
    creds_file = tmp_path / "google_credentials.json"
    creds_file.write_text('{"type": "authorized_user"}')
    from jarvis.integrations.google import GoogleSync
    gs = GoogleSync(credentials_path=str(creds_file))
    with patch.object(gs, "_get_service", side_effect=ImportError("google-auth not installed")):
        result = gs.sync_calendar()
    assert result == []


def test_sync_calendar_handles_any_exception(tmp_path):
    creds_file = tmp_path / "google_credentials.json"
    creds_file.write_text('{"type": "authorized_user"}')
    from jarvis.integrations.google import GoogleSync
    gs = GoogleSync(credentials_path=str(creds_file))
    with patch.object(gs, "_get_service", side_effect=RuntimeError("unexpected error")):
        result = gs.sync_calendar()
    assert result == []
