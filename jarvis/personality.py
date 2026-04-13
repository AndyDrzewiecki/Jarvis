"""
PersonalityLayer — wraps core.chat() and post-processes the response text
through a fast LLM style-rewrite to give Jarvis a British butler personality.

Controlled by:
  JARVIS_PERSONALITY_ENABLED env var (default: read from preferences)
  preferences.personality_enabled (default: True)

Uses JARVIS_FALLBACK_MODEL (qwen2.5:0.5b) for speed.
Falls back to raw AdapterResult.text on any failure.
Does NOT modify core.py.
"""
from __future__ import annotations
import os
import re

from jarvis.adapters.base import AdapterResult


_STYLE_PROMPT_TEMPLATE = """You are J.A.R.V.I.S. Rewrite the following in character.
Rules: Address user as "{address_name}". Be direct. Lead with the key fact.
Use dry British understatement. Be concise — no padding. Do not invent
information not in the source. Keep all technical details accurate.

Source: {text}
Rewritten:"""


def _strip_markdown(text: str) -> str:
    """Remove markdown formatting from text."""
    text = re.sub(r"[*_`#]+", "", text)
    return " ".join(text.split())


class PersonalityLayer:
    def __init__(self):
        pass

    def _is_enabled(self) -> bool:
        env = os.getenv("JARVIS_PERSONALITY_ENABLED")
        if env is not None:
            return env.lower() not in ("false", "0", "no")
        try:
            import jarvis.preferences as prefs
            return bool(prefs.get("personality_enabled", True))
        except Exception:
            return True

    def _get_address_name(self) -> str:
        try:
            import jarvis.preferences as prefs
            return str(prefs.get("address_name", "Sir"))
        except Exception:
            return "Sir"

    def _rewrite(self, text: str, address_name: str) -> str:
        """Call qwen2.5:0.5b to rewrite text in JARVIS style."""
        from jarvis.core import _ask_ollama, FALLBACK_MODEL
        prompt = _STYLE_PROMPT_TEMPLATE.format(
            address_name=address_name,
            text=_strip_markdown(text)[:1000],
        )
        try:
            result = _ask_ollama(prompt, model=FALLBACK_MODEL)
            return result.strip() if result.strip() else text
        except Exception:
            return text

    def process(self, message: str) -> AdapterResult:
        """Process a message: route via core.chat(), then optionally rewrite in JARVIS style."""
        from jarvis.core import chat
        result = chat(message)

        if not self._is_enabled():
            return result

        address_name = self._get_address_name()
        rewritten = self._rewrite(result.text, address_name)
        return AdapterResult(
            success=result.success,
            text=rewritten,
            data=result.data,
            adapter=result.adapter,
        )
