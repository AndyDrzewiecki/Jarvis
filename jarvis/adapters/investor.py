"""
TUTORIAL: InvestorAdapter wraps the AI_Agent_Investor orchestrator.
It adds the investor project to sys.path and calls run_once() which executes
the full multi-agent pipeline (MarketWatcher, Historian, Forecaster, etc.)
and returns a structured dict with daily_brief and market_output keys.

This is a heavy call — it may take 30-120 seconds if Ollama is running.
"""
from __future__ import annotations
import sys
import os
from typing import Any

_INVESTOR_DIR = os.path.normpath(r"C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group")
if _INVESTOR_DIR not in sys.path:
    sys.path.insert(0, _INVESTOR_DIR)


def _import_investor_orchestrator():
    try:
        import orchestrator as inv_orch
        return inv_orch
    except ImportError as e:
        return None


from jarvis.adapters.base import BaseAdapter, AdapterResult


class InvestorAdapter(BaseAdapter):
    name = "investor"
    description = "Daily market brief, portfolio analysis, investment signals"
    capabilities = ["daily_brief", "market_check"]

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        inv = _import_investor_orchestrator()
        if inv is None:
            return AdapterResult(
                success=False,
                text="Investor pipeline not available. Ensure C:/AI-Lab/AI_Agent_Investor/AI-Agent-Investment-Group/orchestrator.py exists and all dependencies are installed.",
                adapter=self.name,
            )

        if capability == "daily_brief":
            result = inv.run_once()
            brief = result.get("daily_brief") or "No brief generated."
            return AdapterResult(
                success=True,
                text=str(brief),
                data=result,
                adapter=self.name,
            )

        elif capability == "market_check":
            result = inv.run_once()
            market = result.get("market_output") or {}
            risk = market.get("risk_label", "unknown")
            summary = market.get("summary", str(market)[:500])
            return AdapterResult(
                success=True,
                text=f"Market risk: {risk}\n{summary}",
                data=market,
                adapter=self.name,
            )

        return AdapterResult(
            success=False,
            text=f"Unknown capability '{capability}'. Available: {self.capabilities}",
            adapter=self.name,
        )
