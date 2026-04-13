"""
Local speech-to-text via faster-whisper (CPU, private — audio never leaves the house).

Model is loaded lazily on first call (~150MB download on first use).

Environment variables:
  JARVIS_STT_ENABLED  — "true"/"false" (default false). When false, returns stub.
  JARVIS_STT_MODEL    — model name (default: distil-whisper/distil-small.en)

Returns: {"text": str, "confidence": float, "language": str}
"""
from __future__ import annotations
import io
import os

STT_ENABLED = os.getenv("JARVIS_STT_ENABLED", "false").lower() in ("true", "1", "yes")
STT_MODEL_NAME = os.getenv("JARVIS_STT_MODEL", "distil-whisper/distil-small.en")

_model = None  # lazy global — loaded once on first real call


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(STT_MODEL_NAME, device="cpu", compute_type="int8")
    return _model


def transcribe(audio_bytes: bytes) -> dict:
    """
    Transcribe raw audio bytes to text.
    Returns {"text": str, "confidence": float, "language": str}.
    Never raises — returns empty text on any error.
    """
    if not STT_ENABLED:
        return {"text": "STT not enabled", "confidence": 0.0, "language": "en"}

    if not audio_bytes:
        return {"text": "", "confidence": 0.0, "language": "en"}

    try:
        model = _get_model()
        audio_file = io.BytesIO(audio_bytes)
        segments, info = model.transcribe(audio_file, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return {
            "text": text,
            "confidence": 0.9,  # faster-whisper doesn't expose per-file confidence
            "language": info.language,
        }
    except Exception:
        return {"text": "", "confidence": 0.0, "language": "en"}
