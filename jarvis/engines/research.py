from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from jarvis.engines import register_engine
from jarvis.engines.base_engine import BaseKnowledgeEngine
from jarvis.ingestion import RawItem

logger = logging.getLogger(__name__)

_ARXIV_NS = "http://www.w3.org/2005/Atom"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@register_engine
class ResearchEngine(BaseKnowledgeEngine):
    """Engine 3 — AI/ML Research Sentinel.

    Fetches new AI/ML papers from arXiv, trending repos from GitHub,
    and new model releases from HuggingFace. Evaluates applicability to Jarvis.
    """

    name = "research_engine"
    domain = "research"
    schedule = "0 6,18 * * *"

    def gather(self) -> list[dict]:
        """Fetch papers, repos, and models."""
        items = []
        items.extend(self._fetch_arxiv_papers())
        items.extend(self._fetch_github_repos())
        items.extend(self._fetch_hf_models())
        return items

    def _fetch_arxiv_papers(self) -> list[dict]:
        """Fetch recent AI/ML papers from arXiv Atom feed."""
        url = (
            "http://export.arxiv.org/api/query"
            "?search_query=cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL"
            "&sortBy=submittedDate&sortOrder=descending&max_results=20"
        )
        results = []
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = resp.read()
            root = ET.fromstring(data)
            ns = {"atom": _ARXIV_NS}
            for entry in root.findall("atom:entry", ns):
                arxiv_id_el = entry.find("atom:id", ns)
                title_el = entry.find("atom:title", ns)
                summary_el = entry.find("atom:summary", ns)
                published_el = entry.find("atom:published", ns)

                arxiv_id = arxiv_id_el.text.split("/")[-1] if arxiv_id_el is not None else ""
                title = (title_el.text or "").strip().replace("\n", " ")
                abstract = (summary_el.text or "").strip().replace("\n", " ")
                published = (published_el.text or "")[:10] if published_el is not None else ""

                authors = [
                    (a.find("atom:name", ns).text or "")
                    for a in entry.findall("atom:author", ns)
                    if a.find("atom:name", ns) is not None
                ]
                categories = [
                    t.get("term", "")
                    for t in entry.findall("atom:category", ns)
                ]

                if title:
                    results.append({
                        "type": "paper",
                        "arxiv_id": arxiv_id,
                        "title": title,
                        "authors": ", ".join(authors[:5]),
                        "abstract": abstract[:1000],
                        "published_date": published,
                        "categories": ",".join(categories[:5]),
                    })
        except Exception as exc:
            logger.warning("arXiv fetch failed: %s", exc)
        return results

    def _fetch_github_repos(self) -> list[dict]:
        """Fetch trending AI/ML repos from GitHub search API."""
        from jarvis import config
        url = (
            "https://api.github.com/search/repositories"
            "?q=topic:llm+OR+topic:agents+OR+topic:rag&sort=stars&order=desc&per_page=20"
        )
        headers = {"User-Agent": "Jarvis/1.0", "Accept": "application/vnd.github.v3+json"}
        if config.GITHUB_TOKEN:
            headers["Authorization"] = f"token {config.GITHUB_TOKEN}"
        results = []
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for repo in data.get("items", [])[:20]:
                results.append({
                    "type": "repo",
                    "github_url": repo.get("html_url", ""),
                    "name": repo.get("full_name", ""),
                    "description": (repo.get("description") or "")[:300],
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "topics": ",".join(repo.get("topics", [])[:10]),
                    "last_commit": repo.get("pushed_at", ""),
                })
        except Exception as exc:
            logger.warning("GitHub repos fetch failed: %s", exc)
        return results

    def _fetch_hf_models(self) -> list[dict]:
        """Fetch recent text-generation models from HuggingFace."""
        url = "https://huggingface.co/api/models?sort=lastModified&direction=-1&limit=20&filter=text-generation"
        results = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for model in data[:20]:
                results.append({
                    "type": "model",
                    "hf_model_id": model.get("id", ""),
                    "name": model.get("id", ""),
                    "tags": ",".join(model.get("tags", [])[:10]),
                    "last_modified": model.get("lastModified", ""),
                })
        except Exception as exc:
            logger.warning("HuggingFace models fetch failed: %s", exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data to RawItems for ingestion."""
        items = []
        now = _now()

        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "paper":
                title = raw.get("title", "")
                abstract = raw.get("abstract", "")
                content = f"AI/ML Paper: {title}. {abstract[:300]}"
                items.append(RawItem(
                    content=content,
                    source="arxiv",
                    source_url=f"https://arxiv.org/abs/{raw.get('arxiv_id', '')}",
                    fact_type="research_paper",
                    domain=self.domain,
                    structured_data={
                        "arxiv_id": raw.get("arxiv_id", ""),
                        "title": title,
                        "authors": raw.get("authors", ""),
                        "abstract": raw.get("abstract", ""),
                        "published_date": raw.get("published_date", now[:10]),
                        "categories": raw.get("categories", ""),
                    },
                    quality_hint=0.6,
                    tags=f"research,ai,paper,{raw.get('categories', '')[:50]}",
                ))

            elif data_type == "repo":
                name = raw.get("name", "")
                desc = raw.get("description", "")
                stars = raw.get("stars", 0)
                content = f"AI/ML Repo: {name} ({stars} stars). {desc[:200]}"
                items.append(RawItem(
                    content=content,
                    source="github",
                    source_url=raw.get("github_url"),
                    fact_type="tracked_repo",
                    domain=self.domain,
                    structured_data={
                        "github_url": raw.get("github_url", ""),
                        "name": name,
                        "description": desc,
                        "stars": stars,
                        "language": raw.get("language", ""),
                        "topics": raw.get("topics", ""),
                        "last_commit": raw.get("last_commit", ""),
                        "first_seen": now,
                        "last_checked": now,
                    },
                    quality_hint=min(0.9, 0.4 + stars / 10000),
                    tags=f"research,ai,repo,{raw.get('language','').lower()}",
                ))

            elif data_type == "model":
                hf_id = raw.get("hf_model_id", "")
                content = f"HuggingFace model: {hf_id}. Tags: {raw.get('tags', '')[:100]}"
                items.append(RawItem(
                    content=content,
                    source="huggingface",
                    source_url=f"https://huggingface.co/{hf_id}",
                    fact_type="model_registry",
                    domain=self.domain,
                    structured_data={
                        "hf_model_id": hf_id,
                        "name": raw.get("name", hf_id),
                        "first_seen": now,
                        "notes": f"tags: {raw.get('tags', '')[:200]}",
                    },
                    quality_hint=0.5,
                    tags="research,ai,model,huggingface",
                ))

        return items

    def improve(self) -> list[str]:
        """Check for stale papers and repos needing review."""
        gaps = []
        try:
            unreviewed = self.engine_store.query(
                "research", "research_papers", where="reviewed=0", limit=20
            )
            if unreviewed:
                gaps.append(f"{len(unreviewed)} research papers pending review")
        except Exception:
            pass
        return gaps
