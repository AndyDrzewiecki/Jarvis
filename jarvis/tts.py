"""
TTS engine wrapping edge-tts with en-GB-RyanNeural voice.
Returns MP3 bytes. Never raises — returns b"" on failure.
"""
import asyncio
import os
import re

# edge-tts is imported inline to allow easy mocking in tests

_DEFAULT_VOICE = "en-GB-RyanNeural"
_MAX_CHARS = 500


def _preprocess(text: str) -> str:
    """Strip markdown/XML tags, collapse whitespace, truncate to 500 chars."""
    # Strip XML/HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Strip markdown bold/italic/code
    text = re.sub(r"[*_`#]+", "", text)
    # Collapse whitespace
    text = " ".join(text.split())
    # Truncate
    return text[:_MAX_CHARS]


async def synthesize(text: str, voice: str | None = None) -> bytes:
    """Async: synthesize text to MP3 bytes using edge-tts."""
    import edge_tts
    import io

    chosen_voice = voice or os.getenv("JARVIS_TTS_VOICE", _DEFAULT_VOICE)
    processed = _preprocess(text)
    if not processed:
        return b""

    tts_rate = os.getenv("JARVIS_TTS_RATE", "-5%")
    tts_pitch = os.getenv("JARVIS_TTS_PITCH", "-10Hz")

    try:
        communicate = edge_tts.Communicate(processed, chosen_voice, rate=tts_rate, pitch=tts_pitch)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()
    except Exception:
        return b""


def synthesize_sync(text: str, voice: str | None = None) -> bytes:
    """Sync wrapper for synthesize()."""
    try:
        return asyncio.run(synthesize(text, voice))
    except Exception:
        return b""
