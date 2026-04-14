"""Jarvis Phase 3 — Knowledge Accumulation Engines."""
from __future__ import annotations

ENGINE_REGISTRY: list = []

def register_engine(cls):
    """Decorator to register a knowledge engine."""
    ENGINE_REGISTRY.append(cls)
    return cls
