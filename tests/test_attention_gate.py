from __future__ import annotations
from jarvis.memory_tiers.attention import AttentionGate
from jarvis.memory_tiers.types import MemoryRecall


def test_gate_includes_working_memory():
    gate = AttentionGate()
    recall = MemoryRecall(
        working=[{"role": "user", "text": "hello world", "timestamp": "2026-01-01T00:00:00"}]
    )
    result = gate.gate("hello", recall, budget=2000)
    assert "hello world" in result


def test_gate_includes_semantic_facts():
    gate = AttentionGate()
    recall = MemoryRecall(
        semantic=[{"domain": "grocery", "content": "chicken is on sale"}]
    )
    result = gate.gate("grocery", recall, budget=2000)
    assert "chicken" in result


def test_gate_includes_episodic_summaries():
    gate = AttentionGate()
    recall = MemoryRecall(
        episodic=[{"id": "ep1", "summary": "discussed meal planning for the week"}]
    )
    result = gate.gate("meals", recall, budget=2000)
    assert "meal planning" in result


def test_gate_respects_budget():
    gate = AttentionGate()
    recall = MemoryRecall(
        working=[{"role": "user", "text": "a" * 500, "timestamp": "2026-01-01"}
                  for _ in range(20)],
        semantic=[{"domain": "x", "content": "b" * 500} for _ in range(10)],
    )
    result = gate.gate("test", recall, budget=100)
    assert len(result) <= 100 * 4 + 200


def test_gate_empty_recall_returns_empty_string():
    gate = AttentionGate()
    recall = MemoryRecall()
    result = gate.gate("test", recall, budget=2000)
    assert result == ""
