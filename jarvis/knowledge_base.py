"""
ChromaDB-backed knowledge base for Jarvis.
Single collection 'jarvis_knowledge' with category metadata filter.

Design: one collection, category-filtered queries, simpler than multi-collection.
Path: data/chromadb/ (overridable via JARVIS_CHROMADB_PATH env var).

Categories: conversations | saved_items | research | recipes | how_to | notes
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

CHROMADB_PATH = os.getenv("JARVIS_CHROMADB_PATH", "data/chromadb")

VALID_CATEGORIES = frozenset(
    {"conversations", "saved_items", "research", "recipes", "how_to", "notes"}
)


class KnowledgeBase:
    def __init__(self, persist_dir: str = CHROMADB_PATH):
        self._persist_dir = persist_dir
        self._client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            import chromadb  # lazy — avoids 500MB import at startup if disabled
            if self._persist_dir == ":memory:":
                self._client = chromadb.Client()
            else:
                self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._collection = self._client.get_or_create_collection("jarvis_knowledge")
        return self._collection

    def add_document(
        self,
        content: str,
        category: str = "notes",
        tags: list[str] | None = None,
        source_url: str = "",
        device_id: str = "",
    ) -> str:
        """Add a document. Returns the generated id."""
        item_id = str(uuid.uuid4())
        col = self._get_collection()
        col.add(
            ids=[item_id],
            documents=[content],
            metadatas=[{
                "category": category,
                "tags": ",".join(tags or []),
                "source_url": source_url,
                "device_id": device_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }],
        )
        return item_id

    def search(self, query: str, n: int = 10, category: Optional[str] = None) -> list[dict]:
        """Semantic search. Optionally filter by category."""
        col = self._get_collection()
        kwargs: dict = {"query_texts": [query], "n_results": n}
        if category:
            kwargs["where"] = {"category": category}
        try:
            results = col.query(**kwargs)
        except Exception:
            return []
        return _unpack_query_results(results)

    def browse(
        self, category: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        """Return items (no semantic search), optionally filtered by category."""
        col = self._get_collection()
        kwargs: dict = {"limit": limit, "offset": offset}
        if category:
            kwargs["where"] = {"category": category}
        try:
            results = col.get(**kwargs)
        except Exception:
            return []
        return _unpack_get_results(results)

    def get(self, item_id: str) -> dict | None:
        """Fetch a single item by id. Returns None if not found."""
        col = self._get_collection()
        try:
            result = col.get(ids=[item_id])
        except Exception:
            return None
        if not result.get("ids"):
            return None
        meta = result["metadatas"][0]
        return {
            "id": result["ids"][0],
            "content": result["documents"][0],
            **meta,
            "tags": _split_tags(meta.get("tags", "")),
        }

    def delete(self, item_id: str) -> bool:
        """Delete an item by id. Returns True on success."""
        col = self._get_collection()
        try:
            col.delete(ids=[item_id])
            return True
        except Exception:
            return False

    def summarize(self, tag_filter: list[str] | None = None) -> str:
        """LLM synthesis of matching documents via _ask_ollama (uses fallback model)."""
        from jarvis.core import _ask_ollama, FALLBACK_MODEL  # lazy to avoid circular at top

        items = self.browse(limit=20)
        if tag_filter:
            items = [
                i for i in items
                if any(t in i.get("tags", []) for t in tag_filter)
            ]
        if not items:
            return "No items found in knowledge base."
        context = "\n".join(f"- {i['content']}" for i in items[:10])
        prompt = (
            "Summarize the following saved knowledge items concisely:\n"
            f"{context}\n\nSummary:"
        )
        try:
            return _ask_ollama(prompt, model=FALLBACK_MODEL)
        except Exception as exc:
            return f"Summary unavailable: {exc}"


# ── helpers ────────────────────────────────────────────────────────────────────

def _split_tags(tag_str: str) -> list[str]:
    return [t for t in tag_str.split(",") if t]


def _unpack_query_results(results: dict) -> list[dict]:
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    items = []
    for item_id, doc, meta in zip(ids, docs, metas):
        items.append({
            "id": item_id,
            "content": doc,
            **meta,
            "tags": _split_tags(meta.get("tags", "")),
        })
    return items


def _unpack_get_results(results: dict) -> list[dict]:
    ids = results.get("ids", [])
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    items = []
    for item_id, doc, meta in zip(ids, docs, metas):
        items.append({
            "id": item_id,
            "content": doc,
            **meta,
            "tags": _split_tags(meta.get("tags", "")),
        })
    return items
