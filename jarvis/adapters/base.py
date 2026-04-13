"""
TUTORIAL: BaseAdapter is the contract every adapter must fulfill.
- AdapterResult wraps all responses: success flag, text, data dict.
- safe_run() catches all exceptions so one bad adapter never crashes Jarvis.
- safe_run() also writes every execution decision to agent_memory automatically.
- Each adapter declares its name and capabilities so the LLM can route correctly.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AdapterResult:
    success: bool
    text: str
    data: dict = field(default_factory=dict)
    adapter: str = ""

    def to_dict(self) -> dict:
        return {"success": self.success, "text": self.text, "data": self.data, "adapter": self.adapter}


class BaseAdapter:
    name: str = "base"
    description: str = "Base adapter"
    capabilities: list[str] = []

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        raise NotImplementedError

    def safe_run(
        self,
        capability: str,
        params: dict[str, Any],
        linked_message_id: Optional[str] = None,
    ) -> AdapterResult:
        """Run the adapter, catching all exceptions. Logs every execution to agent_memory."""
        import jarvis.agent_memory as _am

        start = time.monotonic()
        try:
            result = self.run(capability, params)
            outcome = "success" if result.success else "failure"
            try:
                _am.log_decision(
                    agent=self.name,
                    capability=capability,
                    decision=f"Executed {capability} — {outcome}",
                    reasoning=result.text[:500],
                    outcome=outcome,
                    linked_message_id=linked_message_id,
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
            except Exception:
                pass
            return result
        except Exception as exc:
            duration = int((time.monotonic() - start) * 1000)
            try:
                _am.log_decision(
                    agent=self.name,
                    capability=capability,
                    decision=f"Executed {capability} — failure",
                    reasoning=str(exc)[:500],
                    outcome="failure",
                    linked_message_id=linked_message_id,
                    duration_ms=duration,
                )
            except Exception:
                pass
            return AdapterResult(
                success=False,
                text=f"[{self.name}] Error: {exc}",
                data={"error": str(exc)},
                adapter=self.name,
            )
