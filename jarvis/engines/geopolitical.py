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

_RSS_NS = "http://www.w3.org/2005/Atom"

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@register_engine
class GeopoliticalEngine(BaseKnowledgeEngine):
    """Engine 2 — Geopolitical & World Events.

    Fetches world events from GDELT Project, tracks legislation via Congress.gov,
    and monitors world news RSS feeds. Cross-wires market impact to Financial Engine.
    """

    name = "geopolitical_engine"
    domain = "geopolitical"
    schedule = "0 */6 * * *"

    def gather(self) -> list[dict]:
        """Fetch events from GDELT, Congress.gov, and RSS feeds."""
        from jarvis import config
        items = []

        # Source 1: GDELT Project (public, no key)
        items.extend(self._fetch_gdelt())

        # Source 2: Congress.gov (optional API key)
        if config.CONGRESS_API_KEY:
            items.extend(self._fetch_congress(config.CONGRESS_API_KEY))
        else:
            logger.debug("GeopoliticalEngine: CONGRESS_API_KEY not set, skipping")

        # Source 3: RSS feeds
        for feed_url in config.GEOPOLITICAL_FEEDS:
            items.extend(self._fetch_rss(feed_url))

        return items

    def _fetch_gdelt(self) -> list[dict]:
        """Fetch recent event articles from GDELT DOC API."""
        url = (
            "https://api.gdeltproject.org/api/v2/doc/doc"
            "?query=conflict+OR+sanctions+OR+election+OR+trade"
            "&mode=ArtList&maxrecords=20&format=json"
        )
        results = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for article in data.get("articles", [])[:20]:
                results.append({
                    "type": "gdelt",
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "seendate": article.get("seendate", ""),
                    "domain": article.get("domain", ""),
                    "tone": article.get("tone", 0.0),
                })
        except Exception as exc:
            logger.warning("GDELT fetch failed: %s", exc)
        return results

    def _fetch_congress(self, api_key: str) -> list[dict]:
        """Fetch recent bills from Congress.gov API."""
        url = f"https://api.congress.gov/v3/bill?limit=10&sort=updateDate+desc&api_key={api_key}&format=json"
        results = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for bill in data.get("bills", [])[:10]:
                results.append({
                    "type": "congress",
                    "title": bill.get("title", ""),
                    "number": bill.get("number", ""),
                    "congress": bill.get("congress", ""),
                    "origin": bill.get("originChamber", ""),
                    "latest_action": bill.get("latestAction", {}).get("text", ""),
                    "update_date": bill.get("updateDate", ""),
                    "url": f"https://www.congress.gov/bill/{bill.get('congress','')}/{bill.get('type','').lower()}-bill/{bill.get('number','')}",
                })
        except Exception as exc:
            logger.warning("Congress.gov fetch failed: %s", exc)
        return results

    def _fetch_rss(self, feed_url: str) -> list[dict]:
        """Fetch headlines from an RSS/Atom feed."""
        results = []
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            root = ET.fromstring(data)
            ns = {"atom": _RSS_NS}
            # RSS 2.0
            for item in root.iter("item"):
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                desc = item.findtext("description", "")
                if title:
                    results.append({"type": "rss", "title": title, "url": link, "description": desc[:300], "feed": feed_url})
            # Atom
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                link_el = entry.find("atom:link", ns)
                title = title_el.text if title_el is not None else ""
                link = link_el.get("href", "") if link_el is not None else ""
                if title:
                    results.append({"type": "rss", "title": title, "url": link, "description": "", "feed": feed_url})
        except Exception as exc:
            logger.warning("RSS fetch failed for %s: %s", feed_url, exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data to RawItems for ingestion."""
        items = []
        now = _now()

        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "gdelt":
                title = raw.get("title", "")
                tone = raw.get("tone", 0.0)
                severity = max(0.0, min(1.0, abs(float(tone or 0)) / 10.0))
                content = f"World event: {title}"
                items.append(RawItem(
                    content=content,
                    source="gdelt",
                    source_url=raw.get("url"),
                    fact_type="geopolitical_event",
                    domain=self.domain,
                    structured_data={
                        "title": title,
                        "event_type": "news",
                        "description": title,
                        "regions": "[]",
                        "started_at": raw.get("seendate", now)[:10] or now[:10],
                        "severity": severity,
                        "source": "gdelt",
                        "source_url": raw.get("url", ""),
                    },
                    quality_hint=0.5,
                    tags="geopolitical,gdelt,world",
                ))

            elif data_type == "congress":
                title = raw.get("title", "")
                action = raw.get("latest_action", "")
                content = f"US Congress bill: {title}. Latest action: {action}"
                items.append(RawItem(
                    content=content,
                    source="congress_gov",
                    source_url=raw.get("url"),
                    fact_type="policy_tracker",
                    domain=self.domain,
                    structured_data={
                        "jurisdiction": "US Federal",
                        "policy_type": "legislation",
                        "title": title,
                        "status": action[:200] if action else "introduced",
                        "introduced_date": raw.get("update_date", now)[:10] or now[:10],
                        "last_action": action[:300] if action else "",
                        "source_url": raw.get("url", ""),
                    },
                    quality_hint=0.7,
                    tags="geopolitical,policy,us_congress",
                ))

            elif data_type == "rss":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                content = f"World news: {title}. {desc[:200]}"
                items.append(RawItem(
                    content=content,
                    source="rss",
                    source_url=raw.get("url"),
                    fact_type="geopolitical_event",
                    domain=self.domain,
                    structured_data={
                        "title": title,
                        "event_type": "news",
                        "description": desc[:500] or title,
                        "regions": "[]",
                        "started_at": now[:10],
                        "source": raw.get("feed", "rss"),
                        "source_url": raw.get("url", ""),
                    },
                    quality_hint=0.4,
                    tags="geopolitical,news,rss",
                ))

        return items

    def improve(self) -> list[str]:
        """Identify coverage gaps."""
        gaps = []
        from jarvis import config
        if not config.CONGRESS_API_KEY:
            gaps.append("Congress.gov API key not configured")
        if not config.GEOPOLITICAL_FEEDS:
            gaps.append("No geopolitical RSS feeds configured")
        return gaps
