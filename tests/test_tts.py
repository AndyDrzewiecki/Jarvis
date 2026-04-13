"""Tests for jarvis/tts.py"""
import asyncio
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from jarvis.tts import _preprocess, synthesize, synthesize_sync


def _make_fake_edge_tts(communicate_cls):
    """Return a minimal fake edge_tts module with the given Communicate class."""
    mod = types.ModuleType("edge_tts")
    mod.Communicate = communicate_cls
    return mod


class TestPreprocess:
    def test_preprocess_strips_xml_tags(self):
        result = _preprocess("<b>hello</b>")
        assert result == "hello"

    def test_preprocess_strips_markdown(self):
        result = _preprocess("**bold** _italic_")
        assert result == "bold italic"

    def test_preprocess_truncates_at_500(self):
        long_text = "a" * 600
        result = _preprocess(long_text)
        assert len(result) == 500


class TestSynthesize:
    def test_synthesize_returns_bytes(self):
        async def mock_stream():
            yield {"type": "audio", "data": b"fakemp3"}

        mock_communicate = MagicMock()
        mock_communicate.stream = mock_stream
        mock_communicate_cls = MagicMock(return_value=mock_communicate)

        fake_edge_tts = _make_fake_edge_tts(mock_communicate_cls)
        with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}):
            result = asyncio.run(synthesize("hello"))

        assert result == b"fakemp3"

    def test_synthesize_returns_empty_on_failure(self):
        async def raising_stream():
            raise Exception("TTS error")
            yield  # make it an async generator

        mock_communicate = MagicMock()
        mock_communicate.stream = raising_stream
        mock_communicate_cls = MagicMock(return_value=mock_communicate)

        fake_edge_tts = _make_fake_edge_tts(mock_communicate_cls)
        with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}):
            result = asyncio.run(synthesize("hello"))

        assert result == b""

    def test_voice_env_override(self):
        async def mock_stream():
            yield {"type": "audio", "data": b"data"}

        mock_communicate = MagicMock()
        mock_communicate.stream = mock_stream
        mock_communicate_cls = MagicMock(return_value=mock_communicate)

        fake_edge_tts = _make_fake_edge_tts(mock_communicate_cls)
        with patch.dict(sys.modules, {"edge_tts": fake_edge_tts}):
            with patch.dict(os.environ, {"JARVIS_TTS_VOICE": "en-US-AriaNeural"}):
                asyncio.run(synthesize("hello"))

        call_args = mock_communicate_cls.call_args
        assert call_args[0][1] == "en-US-AriaNeural"
