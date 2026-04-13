from __future__ import annotations

SPECIALIST_REGISTRY: list = []

def register(spec_class):
    """Decorator to register a specialist class."""
    SPECIALIST_REGISTRY.append(spec_class)
    return spec_class

def start_all() -> list:
    """Instantiate and return all registered specialists."""
    return [cls() for cls in SPECIALIST_REGISTRY]

def stop_all() -> None:
    """Cleanup hook for shutdown."""
    pass
