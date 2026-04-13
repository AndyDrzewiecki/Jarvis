"""
TUTORIAL: GroceryAdapter wraps the grocery_agent.py that lives in C:/AI-Lab/agents/.
Uses jarvis.integrations to add the agents directory to sys.path cleanly.
Capabilities: meal_plan, shopping_list, inventory, price_check.
"""
from __future__ import annotations
from typing import Any

from jarvis.adapters.base import BaseAdapter, AdapterResult


def _import_grocery():
    """Lazy import so tests can mock before import."""
    from jarvis.integrations import import_integration
    return import_integration("grocery_agent")


class GroceryAdapter(BaseAdapter):
    name = "grocery"
    description = "Meal planning, shopping lists, inventory tracking, price checking"
    capabilities = ["meal_plan", "shopping_list", "inventory", "price_check"]

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        ga = _import_grocery()
        if ga is None:
            return AdapterResult(
                success=False,
                text="Grocery agent not available. Ensure C:/AI-Lab/agents/grocery_agent.py exists.",
                adapter=self.name,
            )

        if capability == "meal_plan":
            plan = ga.generate_simple_meal_plan()
            meals = plan.get("meals", [])
            lines = [f"{m['day']}: {m['main']} + {m['side']}" for m in meals]
            return AdapterResult(
                success=True,
                text="Weekly meal plan:\n" + "\n".join(lines),
                data=plan,
                adapter=self.name,
            )

        elif capability == "shopping_list":
            plan = ga.generate_simple_meal_plan()
            pb = ga.load_pricebook()
            inv = ga.load_inventory()
            shopping, totals, weekly_total = ga.build_shopping_list(plan, pb, inv)
            stores = list(shopping.keys())
            return AdapterResult(
                success=True,
                text=f"Shopping list ready. Estimated total: ${weekly_total}. Stores: {', '.join(stores) or 'unknown'}",
                data={"shopping_by_store": shopping, "store_totals": totals, "weekly_total": weekly_total},
                adapter=self.name,
            )

        elif capability == "inventory":
            inv = ga.load_inventory()
            items = inv.get("items", {})
            count = len(items)
            return AdapterResult(
                success=True,
                text=f"Inventory has {count} item(s)." if count else "Inventory is empty. Add items to C:/AI-Lab/agents/data/inventory.json",
                data=inv,
                adapter=self.name,
            )

        elif capability == "price_check":
            pb = ga.load_pricebook()
            item_key = ga.normalize_item_key(params.get("item", ""))
            items = pb.get("items", {})
            entry = items.get(item_key)
            if not entry:
                return AdapterResult(
                    success=True,
                    text=f"'{params.get('item', '')}' not found in pricebook. Add it to C:/AI-Lab/agents/data/pricebook.json",
                    data={},
                    adapter=self.name,
                )
            stores = entry.get("stores", {})
            lines = [f"  {s}: ${v.get('price','?')}{'  [SALE]' if v.get('sale') else ''}" for s, v in stores.items()]
            return AdapterResult(
                success=True,
                text=f"Prices for {item_key}:\n" + "\n".join(lines),
                data=entry,
                adapter=self.name,
            )

        return AdapterResult(
            success=False,
            text=f"Unknown capability '{capability}'. Available: {self.capabilities}",
            adapter=self.name,
        )
