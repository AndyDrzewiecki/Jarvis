from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class MemoryRecall:
    working: list[dict] = field(default_factory=list)
    episodic: list[dict] = field(default_factory=list)
    semantic: list[dict] = field(default_factory=list)
    procedural: list[dict] = field(default_factory=list)

@dataclass
class KBEntry:
    id: str
    domain: str
    fact_type: str
    summary: str
    source_agent: str
    confidence: float = 0.8
    storage: str = "sqlite"
    storage_ref: str | None = None
    created_at: str = ""
    updated_at: str = ""
    expires_at: str | None = None
    superseded_by: str | None = None
    tags: str = ""

@dataclass
class Insight:
    fact_type: str
    content: str
    confidence: float = 0.8
    tags: str = ""

@dataclass
class CycleReport:
    specialist: str
    started_at: str
    ended_at: str = ""
    gathered: int = 0
    insights: int = 0
    gaps_identified: int = 0
    error: str | None = None
