"""
TUTORIAL: Stub adapters are placeholders for future integrations.
Each returns a helpful message explaining it's not yet implemented.
All inherit from BaseAdapter and use safe_run() via the parent.
"""
from __future__ import annotations
from typing import Any
from jarvis.adapters.base import BaseAdapter, AdapterResult


class _StubAdapter(BaseAdapter):
    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        return AdapterResult(
            success=False,
            text=f"[{self.name}] Not yet implemented. Capability '{capability}' is planned.",
            adapter=self.name,
        )


class CalendarAdapter(_StubAdapter):
    name = "calendar"
    description = "Calendar events, reminders, scheduling"
    capabilities = ["today", "week", "add_event", "reminders"]


class EmailAdapter(_StubAdapter):
    name = "email"
    description = "Read and send email summaries"
    capabilities = ["unread", "summary", "send"]


class FinanceAdapter(_StubAdapter):
    name = "finance"
    description = "Personal finance tracking, budget summaries"
    capabilities = ["budget", "spending", "accounts"]


class HomeAdapter(_StubAdapter):
    name = "home"
    description = "Smart home control (lights, thermostat, locks)"
    capabilities = ["status", "set_temp", "lights"]


class MusicAdapter(_StubAdapter):
    name = "music"
    description = "Music playback control"
    capabilities = ["play", "pause", "next", "queue"]


class NewsAdapter(_StubAdapter):
    name = "news"
    description = "Top news headlines and summaries"
    capabilities = ["headlines", "summary", "search"]


class SalesAgentAdapter(BaseAdapter):
    """
    SalesAgentAdapter — wraps C:/AI-Lab/agents/sales_agent.py.

    Capabilities:
      scrape_all        — run all store scrapers (returns live data when promoted)
      scrape_store      — scrape a single store
      update_pricebook  — merge scraped sales into the price book
      generate_scrapers — use DevTeam to scaffold the 5 store scraper functions
      scraper_status    — report stub vs live status for each scraper
    """
    name = "sales_agent"
    description = "Scrape store weekly ads and sales (aldi, cub, target, walmart, costco)"
    capabilities = [
        "scrape_all",
        "scrape_store",
        "update_pricebook",
        "generate_scrapers",
        "scraper_status",
    ]

    # Stores that sales_agent.py covers
    _STORES = ["aldi", "cub", "target", "walmart", "costco"]

    _SCRAPER_PROMPT = (
        "Build a Python module 'sales_scrapers.py' with 5 store-specific functions "
        "that scrape weekly ad sales data from public web pages using requests and "
        "BeautifulSoup. Each function signature: "
        "scrape_{store}() -> list[dict] where each dict has keys: "
        "item (str), price (float), sale_price (float), store (str), valid_through (str). "
        "Stores: aldi, cub, target, walmart, costco. "
        "Also implement normalize_key(name: str) -> str (lowercase, strip whitespace). "
        "Include a pytest test file 'test_sales_scrapers.py' with at least one test per function "
        "that mocks requests.get and asserts the return type is a list."
    )

    def run(self, capability: str, params: dict) -> "AdapterResult":
        from jarvis.adapters.base import AdapterResult as _AR
        if capability == "scrape_all":
            return self._scrape_all(params)
        elif capability == "scrape_store":
            return self._scrape_store(params)
        elif capability == "update_pricebook":
            return self._update_pricebook(params)
        elif capability == "generate_scrapers":
            return self._generate_scrapers(params)
        elif capability == "scraper_status":
            return self._scraper_status(params)
        else:
            return _AR(
                success=False,
                text=f"[sales_agent] Unknown capability: {capability}",
                adapter=self.name,
            )

    def _scrape_all(self, params: dict) -> "AdapterResult":
        from jarvis.adapters.base import AdapterResult as _AR
        try:
            import sys
            sys.path.insert(0, "C:/AI-Lab/agents")
            import sales_agent
            results = []
            for store in self._STORES:
                fn = getattr(sales_agent, f"scrape_{store}", None)
                if fn:
                    results.extend(fn() or [])
            return _AR(
                success=True,
                text=f"Scraped {len(results)} sales items across all stores.",
                data={"items": results},
                adapter=self.name,
            )
        except Exception as exc:
            return _AR(
                success=False,
                text=f"[sales_agent] scrape_all failed: {exc}",
                adapter=self.name,
            )

    def _scrape_store(self, params: dict) -> "AdapterResult":
        from jarvis.adapters.base import AdapterResult as _AR
        store = params.get("store", "").lower()
        if store not in self._STORES:
            return _AR(
                success=False,
                text=f"[sales_agent] Unknown store '{store}'. Options: {self._STORES}",
                adapter=self.name,
            )
        try:
            import sys
            sys.path.insert(0, "C:/AI-Lab/agents")
            import sales_agent
            fn = getattr(sales_agent, f"scrape_{store}", None)
            if fn is None:
                return _AR(
                    success=False,
                    text=f"[sales_agent] Scraper for '{store}' not found.",
                    adapter=self.name,
                )
            items = fn() or []
            return _AR(
                success=True,
                text=f"Scraped {len(items)} items from {store}.",
                data={"items": items, "store": store},
                adapter=self.name,
            )
        except Exception as exc:
            return _AR(
                success=False,
                text=f"[sales_agent] scrape_store failed: {exc}",
                adapter=self.name,
            )

    def _update_pricebook(self, params: dict) -> "AdapterResult":
        from jarvis.adapters.base import AdapterResult as _AR
        try:
            import sys
            sys.path.insert(0, "C:/AI-Lab/agents")
            import sales_agent
            result = sales_agent.apply_updates()
            return _AR(
                success=True,
                text=f"Price book updated: {result}",
                data={"result": result},
                adapter=self.name,
            )
        except Exception as exc:
            return _AR(
                success=False,
                text=f"[sales_agent] update_pricebook failed: {exc}",
                adapter=self.name,
            )

    def _generate_scrapers(self, params: dict) -> "AdapterResult":
        from jarvis.adapters.base import AdapterResult as _AR
        try:
            from jarvis.adapters import ALL_ADAPTERS
            devteam = next((a for a in ALL_ADAPTERS if a.name == "devteam"), None)
            if devteam is None:
                return _AR(
                    success=False,
                    text="[sales_agent] DevTeam adapter not available.",
                    adapter=self.name,
                )
            result = devteam.run("build_app", {"task": self._SCRAPER_PROMPT})
            return _AR(
                success=result.success,
                text=result.text,
                data=result.data,
                adapter=self.name,
            )
        except Exception as exc:
            return _AR(
                success=False,
                text=f"[sales_agent] generate_scrapers failed: {exc}",
                adapter=self.name,
            )

    def _scraper_status(self, params: dict) -> "AdapterResult":
        from jarvis.adapters.base import AdapterResult as _AR
        import sys
        sys.path.insert(0, "C:/AI-Lab/agents")
        status = {}
        try:
            import sales_agent
            for store in self._STORES:
                fn = getattr(sales_agent, f"scrape_{store}", None)
                if fn is None:
                    status[store] = "missing"
                    continue
                try:
                    data = fn()
                    status[store] = "live" if data else "stub"
                except Exception:
                    status[store] = "error"
        except ImportError:
            for store in self._STORES:
                status[store] = "not installed"
        lines = [f"{s}: {v}" for s, v in status.items()]
        return _AR(
            success=True,
            text="Scraper status:\n" + "\n".join(lines),
            data={"status": status},
            adapter=self.name,
        )
