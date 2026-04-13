"""Tests for jarvis/personality.py"""
import os
from unittest.mock import MagicMock, patch, call

import pytest

from jarvis.adapters.base import AdapterResult
from jarvis.personality import PersonalityLayer, _strip_markdown


def _make_result(text="Hello world", adapter="test", success=True):
    return AdapterResult(success=success, text=text, data={}, adapter=adapter)


class TestPersonalityLayer:
    def test_disabled_returns_raw_no_llm_call(self):
        layer = PersonalityLayer()
        mock_result = _make_result("raw response")

        with patch("jarvis.core.chat", return_value=mock_result):
            with patch("jarvis.core._ask_ollama") as mock_ollama:
                with patch.dict(os.environ, {"JARVIS_PERSONALITY_ENABLED": "false"}):
                    result = layer.process("hello")

        mock_ollama.assert_not_called()
        assert result.text == "raw response"

    def test_enabled_calls_rewrite_with_sir(self):
        layer = PersonalityLayer()
        mock_result = _make_result("some response")

        with patch("jarvis.core.chat", return_value=mock_result):
            with patch("jarvis.core._ask_ollama", return_value="Certainly, Sir.") as mock_ollama:
                with patch.dict(os.environ, {"JARVIS_PERSONALITY_ENABLED": "true"}):
                    with patch("jarvis.preferences.get", return_value="Sir"):
                        result = layer.process("hello")

        mock_ollama.assert_called_once()
        prompt_arg = mock_ollama.call_args[0][0]
        assert "Sir" in prompt_arg

    def test_fallback_on_rewrite_failure(self):
        layer = PersonalityLayer()
        mock_result = _make_result("original text")

        with patch("jarvis.core.chat", return_value=mock_result):
            with patch("jarvis.core._ask_ollama", side_effect=Exception("LLM down")):
                with patch.dict(os.environ, {"JARVIS_PERSONALITY_ENABLED": "true"}):
                    result = layer.process("hello")

        assert result.text == "original text"

    def test_process_returns_adapter_result(self):
        layer = PersonalityLayer()
        mock_result = _make_result("some text", adapter="grocery", success=True)

        with patch("jarvis.core.chat", return_value=mock_result):
            with patch("jarvis.core._ask_ollama", return_value="Rewritten text."):
                with patch.dict(os.environ, {"JARVIS_PERSONALITY_ENABLED": "true"}):
                    result = layer.process("hello")

        assert isinstance(result, AdapterResult)
        assert result.success is True
        assert result.adapter == "grocery"
        assert result.text == "Rewritten text."

    def test_address_name_from_preferences(self):
        layer = PersonalityLayer()
        mock_result = _make_result("some response")

        with patch("jarvis.core.chat", return_value=mock_result):
            with patch("jarvis.core._ask_ollama", return_value="Right away, Andy.") as mock_ollama:
                with patch.dict(os.environ, {"JARVIS_PERSONALITY_ENABLED": "true"}):
                    with patch("jarvis.preferences.get", return_value="Andy"):
                        result = layer.process("hello")

        mock_ollama.assert_called_once()
        prompt_arg = mock_ollama.call_args[0][0]
        assert "Andy" in prompt_arg

    def test_markdown_stripped_before_rewrite(self):
        layer = PersonalityLayer()
        mock_result = _make_result("**bold** response with _italic_")

        with patch("jarvis.core.chat", return_value=mock_result):
            with patch("jarvis.core._ask_ollama", return_value="Rewritten.") as mock_ollama:
                with patch.dict(os.environ, {"JARVIS_PERSONALITY_ENABLED": "true"}):
                    with patch("jarvis.preferences.get", return_value="Sir"):
                        result = layer.process("hello")

        mock_ollama.assert_called_once()
        prompt_arg = mock_ollama.call_args[0][0]
        assert "**bold**" not in prompt_arg
        assert "bold" in prompt_arg
