"""OllamaGateway — manages model selection, health checks, and fallback chains for Forge agents.

Each Forge agent declares a preferred model. The gateway checks availability and walks
a fallback chain so agents keep working even when their preferred model isn't loaded.

Model tiers (configured via env vars or defaults):
  FORGE_MODEL_LARGE  — heavy reasoning tasks (default: gemma3:27b)
  FORGE_MODEL_MEDIUM — balanced tasks (default: qwen2.5:14b)
  FORGE_MODEL_SMALL  — fast evaluation tasks (default: qwen2.5:0.5b)

Per-agent model env vars (override tiers):
  FORGE_MODEL_CRITIC, FORGE_MODEL_ANALYST, FORGE_MODEL_TESTER,
  FORGE_MODEL_AUDITOR, FORGE_MODEL_TRAINER
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import urllib.request
import urllib.error
import json

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Model tier defaults
# ------------------------------------------------------------------
_LARGE  = os.getenv("FORGE_MODEL_LARGE",  "gemma3:27b")
_MEDIUM = os.getenv("FORGE_MODEL_MEDIUM", "qwen2.5:14b")
_SMALL  = os.getenv("FORGE_MODEL_SMALL",  "qwen2.5:0.5b")

# Per-agent overrides → fallback chain
_AGENT_MODELS: dict[str, list[str]] = {
    "critic":          [os.getenv("FORGE_MODEL_CRITIC",  _SMALL),  _SMALL, _MEDIUM],
    "pattern_analyst": [os.getenv("FORGE_MODEL_ANALYST", _MEDIUM), _SMALL, _LARGE],
    "tester":          [os.getenv("FORGE_MODEL_TESTER",  _MEDIUM), _SMALL],
    "code_auditor":    [os.getenv("FORGE_MODEL_AUDITOR", _MEDIUM), _SMALL, _LARGE],
    "trainer":         [os.getenv("FORGE_MODEL_TRAINER", _SMALL),  _SMALL],
    "orchestrator":    [_SMALL],
    "default":         [_SMALL, _MEDIUM],
}

_OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@dataclass
class ModelHealth:
    model: str
    available: bool
    latency_ms: int
    error: str | None = None
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OllamaGateway:
    """Manages model availability and routes Forge agent calls to the right Ollama model.

    Usage::

        gw = OllamaGateway()
        response = gw.generate(agent="critic", prompt="Evaluate this output...")
        print(response)
    """

    def __init__(self, base_url: str | None = None, cache_ttl_s: int = 60):
        self._base = (base_url or _OLLAMA_BASE).rstrip("/")
        self._cache_ttl = cache_ttl_s
        self._health_cache: dict[str, ModelHealth] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        agent: str = "default",
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0.3,
        timeout: int = 120,
    ) -> str:
        """Generate a response. Tries each model in the agent's fallback chain.

        Args:
            prompt:      The user prompt.
            agent:       Agent name — selects fallback chain.
            model:       Override model (skips chain selection).
            system:      Optional system prompt prepended to request.
            temperature: Sampling temperature.
            timeout:     HTTP timeout in seconds.

        Returns:
            Response text, or empty string on total failure.
        """
        if model:
            chain = [model]
        else:
            chain = self._chain_for(agent)

        for candidate in chain:
            if not self._is_available(candidate):
                logger.debug("Gateway: model %s not available, skipping", candidate)
                continue
            try:
                return self._call(candidate, prompt, system, temperature, timeout)
            except Exception as exc:
                logger.warning("Gateway: %s failed: %s — trying next", candidate, exc)

        # All models failed — last-ditch attempt with whatever is first in chain
        logger.error("Gateway: all models failed for agent=%s, attempting %s unchecked", agent, chain[0])
        try:
            return self._call(chain[0], prompt, system, temperature, timeout)
        except Exception as exc:
            logger.error("Gateway: complete failure for agent=%s: %s", agent, exc)
            return ""

    def check_health(self, model: str, force: bool = False) -> ModelHealth:
        """Probe Ollama for model availability. Results cached for cache_ttl_s."""
        cached = self._health_cache.get(model)
        if cached and not force:
            age = time.time() - time.mktime(
                datetime.fromisoformat(cached.checked_at).timetuple()
            )
            if age < self._cache_ttl:
                return cached

        start = time.monotonic()
        try:
            data = json.dumps({"model": model, "prompt": "hi", "stream": False}).encode()
            req = urllib.request.Request(
                f"{self._base}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            latency = int((time.monotonic() - start) * 1000)
            health = ModelHealth(model=model, available=True, latency_ms=latency)
        except urllib.error.HTTPError as exc:
            latency = int((time.monotonic() - start) * 1000)
            health = ModelHealth(
                model=model, available=False, latency_ms=latency,
                error=f"HTTP {exc.code}: {exc.reason}",
            )
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            health = ModelHealth(
                model=model, available=False, latency_ms=latency, error=str(exc)
            )

        self._health_cache[model] = health
        return health

    def available_models(self) -> list[str]:
        """List models currently loaded in Ollama."""
        try:
            req = urllib.request.Request(f"{self._base}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            return [m["name"] for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Gateway.available_models error: %s", exc)
            return []

    def health_report(self) -> list[dict[str, Any]]:
        """Check health of all models in all agent chains and return results."""
        seen: set[str] = set()
        results = []
        for chain in _AGENT_MODELS.values():
            for model in chain:
                if model in seen:
                    continue
                seen.add(model)
                h = self.check_health(model, force=True)
                results.append({
                    "model": h.model,
                    "available": h.available,
                    "latency_ms": h.latency_ms,
                    "error": h.error,
                })
        return results

    def best_model_for(self, agent: str) -> str | None:
        """Return the first available model in the agent's fallback chain."""
        for model in self._chain_for(agent):
            if self._is_available(model):
                return model
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _chain_for(self, agent: str) -> list[str]:
        return _AGENT_MODELS.get(agent, _AGENT_MODELS["default"])

    def _is_available(self, model: str) -> bool:
        return self.check_health(model).available

    def _call(
        self,
        model: str,
        prompt: str,
        system: str | None,
        temperature: float,
        timeout: int,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if system:
            payload["system"] = system

        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read())
        return body.get("response", "")


# ------------------------------------------------------------------
# Module-level singleton for convenience imports
# ------------------------------------------------------------------
_default_gateway: OllamaGateway | None = None


def get_gateway() -> OllamaGateway:
    """Return the module-level OllamaGateway singleton."""
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = OllamaGateway()
    return _default_gateway


def forge_generate(
    prompt: str,
    agent: str = "default",
    model: str | None = None,
    system: str | None = None,
    temperature: float = 0.3,
) -> str:
    """Convenience function — generates via the module-level gateway."""
    return get_gateway().generate(prompt, agent=agent, model=model, system=system, temperature=temperature)
