"""Tests for jarvis/stt.py — mocks faster_whisper via sys.modules injection."""
from __future__ import annotations
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_fake_faster_whisper(text="hello world", language="en"):
    """Build a fake faster_whisper module whose WhisperModel returns fixed output."""
    mod = types.ModuleType("faster_whisper")

    class FakeSegment:
        def __init__(self):
            self.text = text

    class FakeInfo:
        def __init__(self):
            self.language = language

    class FakeWhisperModel:
        def __init__(self, model_name, device="cpu", compute_type="int8"):
            self.model_name = model_name

        def transcribe(self, audio_file, beam_size=5):
            return iter([FakeSegment()]), FakeInfo()

    mod.WhisperModel = FakeWhisperModel
    return mod


class TestTranscribe:
    def test_disabled_returns_stub(self, monkeypatch):
        monkeypatch.setenv("JARVIS_STT_ENABLED", "false")
        # Force module re-evaluation of STT_ENABLED
        import importlib
        import jarvis.stt as stt_mod
        monkeypatch.setattr(stt_mod, "STT_ENABLED", False)
        result = stt_mod.transcribe(b"audio_data")
        assert result["text"] == "STT not enabled"
        assert result["confidence"] == 0.0

    def test_transcribe_returns_expected_dict(self, monkeypatch):
        fake_fw = _make_fake_faster_whisper(text="turn on the lights", language="en")
        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            import importlib
            import jarvis.stt as stt_mod
            # Reset lazy global
            stt_mod._model = None
            monkeypatch.setattr(stt_mod, "STT_ENABLED", True)
            result = stt_mod.transcribe(b"fake_audio_bytes")
        assert result["text"] == "turn on the lights"
        assert result["confidence"] == 0.9
        assert result["language"] == "en"

    def test_empty_audio_returns_gracefully(self, monkeypatch):
        fake_fw = _make_fake_faster_whisper()
        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            import jarvis.stt as stt_mod
            monkeypatch.setattr(stt_mod, "STT_ENABLED", True)
            result = stt_mod.transcribe(b"")
        assert result["text"] == ""
        assert result["confidence"] == 0.0

    def test_stt_model_env_override(self, monkeypatch):
        """JARVIS_STT_MODEL controls which model is loaded."""
        loaded_names = []

        class TrackingModel:
            def __init__(self, model_name, device="cpu", compute_type="int8"):
                loaded_names.append(model_name)

            def transcribe(self, audio_file, beam_size=5):
                class Seg:
                    text = "hi"
                class Info:
                    language = "en"
                return iter([Seg()]), Info()

        fake_fw = types.ModuleType("faster_whisper")
        fake_fw.WhisperModel = TrackingModel

        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            import jarvis.stt as stt_mod
            stt_mod._model = None
            monkeypatch.setattr(stt_mod, "STT_ENABLED", True)
            monkeypatch.setattr(stt_mod, "STT_MODEL_NAME", "tiny.en")
            stt_mod.transcribe(b"audio")

        assert "tiny.en" in loaded_names
