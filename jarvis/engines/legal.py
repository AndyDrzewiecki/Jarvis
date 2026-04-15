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
from jarvis.memory_tiers.types import Insight

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@register_engine
class LegalEngine(BaseKnowledgeEngine):
    """Engine 4 — Legal & Regulatory Intelligence.

    Fetches federal regulations (Federal Register), IRS announcements,
    and state legislation. Generates household impact summaries.
    """

    name = "legal_engine"
    domain = "legal"
    schedule = "0 7 * * *"

    def gather(self) -> list[dict]:
        """Fetch from Federal Register, IRS, and state legislature feeds."""
        items = []
        items.extend(self._fetch_federal_register())
        items.extend(self._fetch_irs_rss())
        return items

    def _fetch_federal_register(self) -> list[dict]:
        """Fetch recent rules from the Federal Register API."""
        url = (
            "https://www.federalregister.gov/api/v1/documents.json"
            "?per_page=20&order=newest&conditions%5Btype%5D=RULE"
        )
        results = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            for doc in data.get("results", [])[:20]:
                agencies = ", ".join(a.get("name", "") for a in doc.get("agencies", [])[:3])
                results.append({
                    "type": "federal_register",
                    "title": doc.get("title", ""),
                    "abstract": (doc.get("abstract") or "")[:500],
                    "publication_date": doc.get("publication_date", ""),
                    "document_number": doc.get("document_number", ""),
                    "document_url": doc.get("html_url", ""),
                    "agencies": agencies,
                    "effective_on": doc.get("effective_on", ""),
                })
        except Exception as exc:
            logger.warning("Federal Register fetch failed: %s", exc)
        return results

    def _fetch_irs_rss(self) -> list[dict]:
        """Fetch IRS tax news via RSS."""
        irs_rss_urls = [
            "https://www.irs.gov/newsroom/news-releases-for-current-month",
        ]
        results = []
        for rss_url in irs_rss_urls:
            try:
                req = urllib.request.Request(rss_url, headers={"User-Agent": "Jarvis/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                root = ET.fromstring(data)
                for item in root.iter("item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    desc = item.findtext("description", "")
                    if title:
                        results.append({
                            "type": "irs",
                            "title": title,
                            "url": link,
                            "description": desc[:400],
                        })
            except Exception as exc:
                logger.warning("IRS RSS fetch failed for %s: %s", rss_url, exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data to RawItems for ingestion."""
        items = []
        now = _now()

        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "federal_register":
                title = raw.get("title", "")
                abstract = raw.get("abstract", "")
                agencies = raw.get("agencies", "")
                effective = raw.get("effective_on", "")
                content = f"Federal regulation: {title}. Agencies: {agencies}. {abstract[:200]}"
                items.append(RawItem(
                    content=content,
                    source="federal_register",
                    source_url=raw.get("document_url"),
                    fact_type="regulatory_change",
                    domain=self.domain,
                    structured_data={
                        "jurisdiction": "federal",
                        "domain": self._classify_domain(title + " " + abstract),
                        "title": title,
                        "description": abstract or title,
                        "effective_date": effective or raw.get("publication_date", now[:10]),
                        "source": "federal_register",
                        "source_url": raw.get("document_url", ""),
                    },
                    quality_hint=0.7,
                    tags=f"legal,regulatory,federal,{self._classify_domain(title)[:30]}",
                ))

            elif data_type == "irs":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                content = f"IRS announcement: {title}. {desc[:200]}"
                items.append(RawItem(
                    content=content,
                    source="irs",
                    source_url=raw.get("url"),
                    fact_type="regulatory_change",
                    domain=self.domain,
                    structured_data={
                        "jurisdiction": "federal",
                        "domain": "tax",
                        "title": title,
                        "description": desc or title,
                        "source": "irs",
                        "source_url": raw.get("url", ""),
                    },
                    quality_hint=0.8,
                    tags="legal,regulatory,federal,tax,irs",
                ))

        return items

    def _classify_domain(self, text: str) -> str:
        """Quick keyword-based domain classification."""
        text_lower = text.lower()
        if any(k in text_lower for k in ("tax", "irs", "income", "deduction", "filing")):
            return "tax"
        if any(k in text_lower for k in ("health", "insurance", "medicare", "medicaid")):
            return "health"
        if any(k in text_lower for k in ("employment", "labor", "wage", "worker")):
            return "employment"
        if any(k in text_lower for k in ("housing", "property", "zoning", "mortgage")):
            return "housing"
        if any(k in text_lower for k in ("consumer", "privacy", "data")):
            return "consumer"
        return "regulatory"

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        """Generate household impact summaries and post alerts for action items."""
        if not gathered:
            return []

        insights = []
        raw_items = self.prepare_items(gathered)

        for raw_item in raw_items[:10]:  # analyze top 10
            try:
                prompt = (
                    "You are analyzing a regulatory change for household impact.\n\n"
                    f"Regulation: {raw_item.content[:500]}\n\n"
                    "Assess:\n"
                    "[IMPACT]: One sentence household impact\n"
                    "[ACTION]: Any required action (or NONE)\n"
                    "[DOMAIN]: tax/health/housing/employment/consumer/general\n"
                    "[ALERT_TYPE]: tax_alert/home_alert/regulatory_alert/none\n"
                )
                from jarvis.core import _ask_ollama
                from jarvis import config
                raw = _ask_ollama(prompt, model=config.FALLBACK_MODEL)

                impact = action = domain_tag = alert_type = ""
                for line in raw.strip().splitlines():
                    line = line.strip()
                    if line.startswith("[IMPACT]:"):
                        impact = line[9:].strip()
                    elif line.startswith("[ACTION]:"):
                        action = line[9:].strip()
                    elif line.startswith("[DOMAIN]:"):
                        domain_tag = line[9:].strip()
                    elif line.startswith("[ALERT_TYPE]:"):
                        alert_type = line[13:].strip()

                if impact:
                    insights.append(Insight(
                        fact_type="knowledge",
                        content=f"Regulatory impact: {impact}",
                        confidence=0.7,
                        tags=f"legal,{domain_tag},impact",
                    ))

                if action and action.upper() != "NONE" and alert_type and alert_type != "none":
                    self.blackboard.post(
                        agent=self.name,
                        topic=alert_type,
                        content=f"{raw_item.content[:200]} → Action: {action}",
                        urgency="high",
                    )

            except Exception as exc:
                logger.warning("LegalEngine.analyze LLM error: %s", exc)

        return insights

    def improve(self) -> list[str]:
        """Check for gaps in regulatory coverage."""
        gaps = []
        try:
            unreviewed = self.engine_store.query("legal", "regulatory_changes", limit=10)
            items_missing_impact = [r for r in unreviewed if not r.get("household_impact")]
            if items_missing_impact:
                gaps.append(f"{len(items_missing_impact)} regulatory changes missing household_impact")
        except Exception:
            pass
        return gaps
