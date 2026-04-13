"""
ReceiptIngestAdapter — wraps C:/AI-Lab/agents/receipt_ingest.py.

Capabilities:
  ingest_text      — write receipt text to receipts dir, call ingest(store)
  update_pricebook — directly update pricebook with {item, price, store} tuples
  list_recent      — list the most recent receipt .txt files

The underlying module is imported lazily so the adapter loads even when
the external file is unavailable (it will return an error at call time).
"""
from __future__ import annotations
import os
from datetime import datetime
from typing import Any

from jarvis.adapters.base import BaseAdapter, AdapterResult

_SOURCE_PATH = "C:/AI-Lab/agents/receipt_ingest.py"


class ReceiptIngestAdapter(BaseAdapter):
    name = "receipt_ingest"
    description = (
        "Ingest text receipts to update pricebook and inventory; list recent receipts"
    )
    capabilities = ["ingest_text", "update_pricebook", "list_recent"]

    def _import_module(self):
        """Lazy import of receipt_ingest.py from C:/AI-Lab/agents/."""
        import importlib.util
        if not os.path.exists(_SOURCE_PATH):
            raise FileNotFoundError(
                f"receipt_ingest.py not found at {_SOURCE_PATH}"
            )
        spec = importlib.util.spec_from_file_location("receipt_ingest_ext", _SOURCE_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        if capability == "ingest_text":
            return self._ingest_text(params)
        elif capability == "update_pricebook":
            return self._update_pricebook(params)
        elif capability == "list_recent":
            return self._list_recent(params)
        return AdapterResult(
            success=False,
            text=f"[receipt_ingest] Unknown capability: {capability}",
            adapter=self.name,
        )

    def _ingest_text(self, params: dict) -> AdapterResult:
        text = params.get("text", "").strip()
        store = params.get("store", "unknown")
        if not text:
            return AdapterResult(
                success=False,
                text="[receipt_ingest] 'text' param is required",
                adapter=self.name,
            )
        try:
            mod = self._import_module()
            receipts_dir = mod.RECEIPTS_DIR
            os.makedirs(receipts_dir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fpath = os.path.join(receipts_dir, f"jarvis_{stamp}.txt")
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(text)
            mod.ingest(store)
            return AdapterResult(
                success=True,
                text=f"Receipt ingested for store '{store}'. Pricebook and inventory updated.",
                adapter=self.name,
                data={"store": store, "file": os.path.basename(fpath)},
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text=f"[receipt_ingest] Error ingesting receipt: {e}",
                adapter=self.name,
            )

    def _update_pricebook(self, params: dict) -> AdapterResult:
        items = params.get("items", [])
        if not items:
            return AdapterResult(
                success=False,
                text="[receipt_ingest] 'items' list is required",
                adapter=self.name,
            )
        try:
            mod = self._import_module()
            pricebook = mod.load_json(mod.PRICEBOOK_PATH)
            if "items" not in pricebook:
                pricebook["items"] = {}
            updated = 0
            for entry in items:
                raw_item = entry.get("item", "")
                if not raw_item:
                    continue
                key = mod.normalize_item_key(raw_item)
                store = entry.get("store", "unknown")
                price = entry.get("price")
                if price is None:
                    continue
                pb_item = pricebook["items"].setdefault(key, {"stores": {}})
                pb_item.setdefault("stores", {})[store] = {"price": float(price)}
                updated += 1
            mod.save_json(pricebook, mod.PRICEBOOK_PATH)
            return AdapterResult(
                success=True,
                text=f"Updated {updated} pricebook entries.",
                adapter=self.name,
                data={"updated": updated},
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text=f"[receipt_ingest] Error updating pricebook: {e}",
                adapter=self.name,
            )

    def _list_recent(self, params: dict) -> AdapterResult:
        n = int(params.get("n", 10))
        try:
            mod = self._import_module()
            receipts_dir = mod.RECEIPTS_DIR
            if not os.path.exists(receipts_dir):
                return AdapterResult(
                    success=True,
                    text="No receipts directory found.",
                    adapter=self.name,
                    data={"receipts": []},
                )
            files = sorted(
                [f for f in os.listdir(receipts_dir) if f.endswith(".txt")],
                reverse=True,
            )[:n]
            return AdapterResult(
                success=True,
                text=f"Recent receipts ({len(files)}): {', '.join(files) or 'none'}",
                adapter=self.name,
                data={"receipts": files},
            )
        except Exception as e:
            return AdapterResult(
                success=False,
                text=f"[receipt_ingest] Error listing receipts: {e}",
                adapter=self.name,
            )
