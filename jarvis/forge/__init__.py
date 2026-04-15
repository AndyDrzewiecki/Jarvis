"""Project Forge — Autonomous Software Development framework.

Brain group:
  Brain 0: Jarvis user-facing (Gemma 4 27B) — routes requests, responds to users
  Brain 1: The Critic (12B)        — monitors output quality, catches hallucinations
  Brain 2: The Pattern Analyst     — reads feedback, identifies trends, proposes fixes
  Brain 3: The Tester (27B)        — runs sandboxed A/B tests, promotes or discards
  Brain 4: The Code Auditor (12B)  — reviews code/prompt changes for bugs/security

See ROADMAP.md §Phase 8 for the full design.
"""
from __future__ import annotations

__all__ = [
    "BaseDevAgent",
    "ForgeMemoryStore",
    "ForgeOrchestrator",
    "AgentTrainer",
    "Critic",
]
