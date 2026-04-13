from __future__ import annotations
from datetime import datetime, timezone
from jarvis.memory_tiers.types import MemoryRecall

class AttentionGate:
    def gate(self, query: str, recall: MemoryRecall, budget: int = 2000) -> str:
        char_budget = budget * 4
        sections = []
        if recall.working:
            lines = [f"{m['role']}: {m['text']}" for m in recall.working[-5:]]
            sections.append("## Recent Conversation\n" + "\n".join(lines))
        if recall.semantic:
            facts = [f"- [{f.get('domain','?')}] {f.get('content', f.get('summary', ''))}" for f in recall.semantic[:5]]
            sections.append("## Relevant Knowledge\n" + "\n".join(facts))
        if recall.episodic:
            eps = [f"- {e.get('summary', '')}" for e in recall.episodic[:3] if e.get('summary')]
            if eps:
                sections.append("## Past Context\n" + "\n".join(eps))
        result = "\n\n".join(sections)
        if len(result) > char_budget:
            result = result[:char_budget]
        return result
