"""Tests for jarvis.notifier.DiscordNotifier — mocks requests.post."""
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock

from jarvis.notifier import DiscordNotifier, notify


def _ok_response():
    m = MagicMock()
    m.status_code = 204
    m.raise_for_status = lambda: None
    return m


# ── no webhook configured ─────────────────────────────────────────────────────

def test_notify_without_webhook_prints_and_returns_true(capsys):
    n = DiscordNotifier(webhook="")
    result = n.notify("hello", title="Test")
    assert result is True
    captured = capsys.readouterr()
    assert "hello" in captured.out
    assert "Test" in captured.out


def test_module_level_notify_without_webhook(monkeypatch, capsys):
    monkeypatch.setenv("JARVIS_DISCORD_WEBHOOK", "")
    import jarvis.notifier as mod
    monkeypatch.setattr(mod, "_notifier", DiscordNotifier(webhook=""))
    result = notify("test message")
    assert result is True


# ── webhook configured ────────────────────────────────────────────────────────

def test_notify_posts_to_webhook():
    n = DiscordNotifier(webhook="https://discord.example.com/webhook/abc")
    with patch("jarvis.notifier.requests.post", return_value=_ok_response()) as mock_post:
        result = n.notify("Market alert", title="Investor")
    assert result is True
    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert "Market alert" in str(kwargs.get("json", ""))
    assert "Investor" in str(kwargs.get("json", ""))


def test_notify_includes_title_and_message_in_payload():
    n = DiscordNotifier(webhook="https://discord.example.com/webhook/x")
    with patch("jarvis.notifier.requests.post", return_value=_ok_response()) as mock_post:
        n.notify("Chicken expires Saturday", title="Pantry Alert")
    payload = mock_post.call_args[1]["json"]
    assert "Chicken expires Saturday" in payload["content"]
    assert "Pantry Alert" in payload["content"]


def test_notify_returns_false_on_http_error():
    n = DiscordNotifier(webhook="https://discord.example.com/webhook/x")
    with patch("jarvis.notifier.requests.post", side_effect=Exception("timeout")):
        result = n.notify("test")
    assert result is False


def test_notify_returns_false_on_bad_status():
    n = DiscordNotifier(webhook="https://discord.example.com/webhook/x")
    bad = MagicMock()
    import requests as req
    bad.raise_for_status.side_effect = req.exceptions.HTTPError("403")
    with patch("jarvis.notifier.requests.post", return_value=bad):
        result = n.notify("test")
    assert result is False


def test_notify_uses_env_var_webhook(monkeypatch):
    monkeypatch.setenv("JARVIS_DISCORD_WEBHOOK", "https://discord.example.com/wh/env")
    n = DiscordNotifier()
    assert "env" in n._webhook
    with patch("jarvis.notifier.requests.post", return_value=_ok_response()) as mock_post:
        n.notify("env test")
    mock_post.assert_called_once()
