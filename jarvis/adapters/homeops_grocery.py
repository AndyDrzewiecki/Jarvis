"""
HomeopsGroceryAdapter — wraps the homeops-grocery FastAPI backend.

Source: C:/AI-Lab/homeops-grocery/GroceryConceirge/
Port:   8001 (HOMEOPS_GROCERY_URL env var to override)

If the service is down, returns a helpful "how to start it" message.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from jarvis.adapters.base import BaseAdapter, AdapterResult

HOMEOPS_GROCERY_URL = os.getenv("HOMEOPS_GROCERY_URL", "http://localhost:8001")


class HomeopsGroceryAdapter(BaseAdapter):
    name = "homeops_grocery"
    description = (
        "Full grocery management: inventory, shopping list, meal plans, receipts, spend dashboard"
    )
    capabilities = [
        "dashboard",
        "inventory_list",
        "shopping_list",
        "shopping_add",
        "shopping_check_off",
        "mealplan_current",
        "mealplan_generate",
        "receipts",
        "expiring_soon",
    ]

    def _base_url(self) -> str:
        return HOMEOPS_GROCERY_URL.rstrip("/")

    def _service_down(self) -> AdapterResult:
        url = self._base_url()
        return AdapterResult(
            success=False,
            text=(
                f"HomeOps Grocery not reachable at {url}. "
                "Start with: uvicorn app.main:app --port 8001"
            ),
            adapter=self.name,
        )

    def _filter_expiring(self, inventory: list, days: int) -> list:
        """Return items whose expiry date falls within `days` days from today."""
        cutoff = datetime.now(timezone.utc) + timedelta(days=days)
        result = []
        for item in inventory if isinstance(inventory, list) else []:
            expiry_str = item.get("expires_at") or item.get("expiry_date")
            if not expiry_str:
                continue
            try:
                # Try ISO format first, then date-only
                try:
                    expiry = datetime.fromisoformat(str(expiry_str))
                except ValueError:
                    expiry = datetime.strptime(str(expiry_str), "%Y-%m-%d")
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry <= cutoff:
                    result.append(item)
            except Exception:
                # If we can't parse the date, include the item to be safe
                result.append(item)
        return result

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        base = self._base_url()
        try:
            if capability == "dashboard":
                r = requests.get(f"{base}/dashboard", timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "inventory_list":
                r = requests.get(f"{base}/inventory", timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "shopping_list":
                r = requests.get(f"{base}/shopping-list", timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "shopping_add":
                payload = {
                    "name": params.get("name", ""),
                    "quantity": params.get("quantity", 1),
                    "unit": params.get("unit", ""),
                }
                r = requests.post(f"{base}/shopping-list", json=payload, timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=f"Added item: {payload['name']}", data=data, adapter=self.name
                )

            elif capability == "shopping_check_off":
                item_id = params.get("item_id")
                if not item_id:
                    return AdapterResult(
                        success=False,
                        text="[homeops_grocery] shopping_check_off requires 'item_id' param",
                        adapter=self.name,
                    )
                r = requests.patch(f"{base}/shopping-list/{item_id}", timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=f"Checked off item {item_id}", data=data, adapter=self.name
                )

            elif capability == "mealplan_current":
                r = requests.get(f"{base}/mealplan/current", timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "mealplan_generate":
                r = requests.post(f"{base}/mealplan/generate", json=params, timeout=30)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "receipts":
                r = requests.get(f"{base}/receipts", timeout=10)
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "expiring_soon":
                days = int(params.get("days", 3))
                r = requests.get(f"{base}/inventory", timeout=10)
                r.raise_for_status()
                inventory = r.json()
                expiring = self._filter_expiring(inventory, days)
                if not expiring:
                    return AdapterResult(
                        success=True,
                        text=f"No items expiring within {days} day(s).",
                        data={"items": []},
                        adapter=self.name,
                    )
                names = ", ".join(
                    f"{i.get('name', 'Unknown')} "
                    f"({i.get('expires_at') or i.get('expiry_date', 'soon')})"
                    for i in expiring
                )
                return AdapterResult(
                    success=True,
                    text=f"{len(expiring)} item(s) expiring soon: {names}",
                    data={"items": expiring},
                    adapter=self.name,
                )

            else:
                return AdapterResult(
                    success=False,
                    text=f"[homeops_grocery] Unknown capability: {capability}",
                    adapter=self.name,
                )

        except requests.exceptions.ConnectionError:
            return self._service_down()
        except requests.exceptions.Timeout:
            return AdapterResult(
                success=False,
                text=f"[homeops_grocery] Request timed out for capability '{capability}'",
                adapter=self.name,
            )
        except requests.exceptions.HTTPError as e:
            return AdapterResult(
                success=False,
                text=f"[homeops_grocery] HTTP error: {e}",
                adapter=self.name,
            )
