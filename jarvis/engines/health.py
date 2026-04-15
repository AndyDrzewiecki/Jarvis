"""Engine 5 — Health & Wellness Intelligence.

Fetches air quality (AirNow), CDC health alerts, and OpenFDA drug safety data.
All API keys are optional — engine gracefully degrades when keys are absent.
"""
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
class HealthEngine(BaseKnowledgeEngine):
    """Engine 5 — Health & Wellness Intelligence.

    Data sources:
    - AirNow AQI (requires JARVIS_AIRNOW_API_KEY, free from airnow.gov)
    - CDC RSS newsroom (public, no key)
    - OpenFDA drug event API (public, no key)

    Schedule: twice daily at 7 AM and 7 PM to catch morning and evening conditions.
    """

    name = "health_engine"
    domain = "health"
    schedule = "0 7,19 * * *"

    def gather(self) -> list[dict]:
        """Fetch AQI readings, CDC health alerts, and FDA drug safety notices."""
        from jarvis import config
        items: list[dict] = []

        # Source 1: AirNow AQI (requires API key)
        if config.AIRNOW_API_KEY:
            items.extend(self._fetch_airnow_aqi(config.AIRNOW_API_KEY, config.HOME_ZIP_CODE))
        else:
            logger.debug("HealthEngine: AIRNOW_API_KEY not set, skipping AQI data")

        # Source 2: CDC RSS newsroom (public)
        items.extend(self._fetch_cdc_rss())

        # Source 3: OpenFDA drug events (public)
        items.extend(self._fetch_openfda_events())

        return items

    def _fetch_airnow_aqi(self, api_key: str, zip_code: str) -> list[dict]:
        """Fetch current AQI observations from AirNow API."""
        url = (
            f"https://www.airnowapi.org/aq/observation/zipCode/current/"
            f"?format=application/json&zipCode={zip_code}&API_KEY={api_key}"
        )
        results: list[dict] = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for obs in data:
                results.append({
                    "type": "airnow",
                    "aqi": obs.get("AQI", 0),
                    "category": obs.get("Category", {}).get("Name", ""),
                    "pollutant": obs.get("ParameterName", ""),
                    "location": obs.get("ReportingArea", zip_code),
                    "date_observed": obs.get("DateObserved", _now()[:10]),
                    "hour_observed": obs.get("HourObserved", 0),
                    "source_url": url,
                })
        except Exception as exc:
            logger.warning("AirNow AQI fetch failed for zip %s: %s", zip_code, exc)
        return results

    def _fetch_cdc_rss(self) -> list[dict]:
        """Fetch health alerts from CDC RSS feeds."""
        feed_urls = [
            "https://tools.cdc.gov/api/v2/resources/media/rss",
            "https://www.cdc.gov/media/rss/rss-features.xml",
        ]
        results: list[dict] = []
        for feed_url in feed_urls:
            try:
                req = urllib.request.Request(feed_url, headers={"User-Agent": "Jarvis/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                root = ET.fromstring(data)
                # RSS 2.0
                for item in root.iter("item"):
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    desc = item.findtext("description", "").strip()
                    pub_date = item.findtext("pubDate", "").strip()
                    if title:
                        results.append({
                            "type": "cdc_rss",
                            "title": title,
                            "description": desc[:500],
                            "url": link,
                            "pub_date": pub_date,
                            "feed": feed_url,
                        })
                # Atom
                ns = {"atom": _RSS_NS}
                for entry in root.findall("atom:entry", ns):
                    title_el = entry.find("atom:title", ns)
                    link_el = entry.find("atom:link", ns)
                    summary_el = entry.find("atom:summary", ns)
                    t = title_el.text.strip() if title_el is not None and title_el.text else ""
                    lnk = link_el.get("href", "") if link_el is not None else ""
                    s = summary_el.text.strip()[:500] if summary_el is not None and summary_el.text else ""
                    if t:
                        results.append({
                            "type": "cdc_rss",
                            "title": t,
                            "description": s,
                            "url": lnk,
                            "pub_date": "",
                            "feed": feed_url,
                        })
            except Exception as exc:
                logger.warning("CDC RSS fetch failed for %s: %s", feed_url, exc)
        return results

    def _fetch_openfda_events(self) -> list[dict]:
        """Fetch recent drug adverse event reports from OpenFDA (no key needed)."""
        url = "https://api.fda.gov/drug/event.json?limit=10&sort=receivedate:desc"
        results: list[dict] = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for event in data.get("results", [])[:10]:
                patient = event.get("patient", {})
                drugs = patient.get("drug", [])
                reactions = patient.get("reaction", [])
                drug_names = ", ".join(
                    d.get("medicinalproduct", "") for d in drugs[:3] if d.get("medicinalproduct")
                )
                reaction_names = ", ".join(
                    r.get("reactionmeddrapt", "") for r in reactions[:3] if r.get("reactionmeddrapt")
                )
                serious = event.get("serious", 0)
                receive_date = event.get("receivedate", "")
                if drug_names:
                    results.append({
                        "type": "openfda",
                        "drug_names": drug_names,
                        "reactions": reaction_names,
                        "serious": int(serious or 0),
                        "receive_date": receive_date,
                        "source_url": url,
                    })
        except Exception as exc:
            logger.warning("OpenFDA drug events fetch failed: %s", exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data into RawItems for ingestion."""
        items: list[RawItem] = []
        now = _now()

        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "airnow":
                aqi = raw.get("aqi", 0)
                pollutant = raw.get("pollutant", "PM2.5")
                category = raw.get("category", "")
                location = raw.get("location", "")
                date_obs = raw.get("date_observed", now[:10])
                hour_obs = raw.get("hour_observed", 0)
                measured_at = f"{date_obs}T{int(hour_obs):02d}:00:00+00:00"
                content = (
                    f"Air quality at {location}: AQI {aqi} ({category}) "
                    f"for {pollutant} on {date_obs}"
                )
                items.append(RawItem(
                    content=content,
                    source="airnow",
                    source_url=raw.get("source_url"),
                    fact_type="environmental_data",
                    domain=self.domain,
                    structured_data={
                        "metric": f"AQI_{pollutant.replace(' ', '_')}",
                        "value": float(aqi),
                        "location": location,
                        "measured_at": measured_at,
                        "source": "airnow",
                        "forecast": category,
                    },
                    quality_hint=0.8,
                    tags=f"health,air_quality,aqi,{pollutant.lower().replace(' ', '_')}",
                ))

            elif data_type == "cdc_rss":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                url = raw.get("url", "")
                category = _classify_cdc_title(title)
                content = f"CDC health alert: {title}. {desc[:300]}"
                is_seasonal = int(any(
                    kw in title.lower()
                    for kw in ("flu", "influenza", "seasonal", "winter", "summer", "pollen", "allerg")
                ))
                items.append(RawItem(
                    content=content,
                    source="cdc",
                    source_url=url or None,
                    fact_type="health_knowledge",
                    domain=self.domain,
                    structured_data={
                        "category": category,
                        "title": title,
                        "content": desc[:1000] or title,
                        "source": "cdc",
                        "source_url": url,
                        "evidence_level": "official",
                        "relevance": 0.7,
                        "last_verified": now[:10],
                        "seasonal": is_seasonal,
                    },
                    quality_hint=0.7,
                    tags=f"health,cdc,{category}",
                ))

            elif data_type == "openfda":
                drug_names = raw.get("drug_names", "")
                reactions = raw.get("reactions", "")
                serious = raw.get("serious", 0)
                receive_date = raw.get("receive_date", now[:8])
                title = f"Drug safety event: {drug_names}"
                severity_label = "serious" if serious else "non-serious"
                content = (
                    f"FDA adverse event report ({severity_label}): {drug_names}. "
                    f"Reactions: {reactions}. Received: {receive_date}"
                )
                items.append(RawItem(
                    content=content,
                    source="openfda",
                    source_url=raw.get("source_url"),
                    fact_type="health_knowledge",
                    domain=self.domain,
                    structured_data={
                        "category": "drug_interaction",
                        "title": title,
                        "content": content,
                        "source": "openfda",
                        "source_url": raw.get("source_url", ""),
                        "evidence_level": "case_report",
                        "relevance": 0.5 + 0.3 * serious,
                        "last_verified": now[:10],
                        "seasonal": 0,
                    },
                    quality_hint=0.5 + 0.2 * serious,
                    tags=f"health,fda,drug_safety,{severity_label}",
                ))

        return items

    def improve(self) -> list[str]:
        """Check for data gaps and stale environmental readings."""
        from jarvis import config
        gaps: list[str] = []

        if not config.AIRNOW_API_KEY:
            gaps.append("AirNow API key not configured — real-time AQI unavailable")

        # Check for stale environmental data (>24h old)
        try:
            rows = self.engine_store.query(
                "health", "environmental_data",
                where="measured_at < datetime('now', '-1 day')",
                limit=5,
            )
            if rows:
                gaps.append(f"Stale AQI data: {len(rows)} records older than 24h")
        except Exception:
            pass

        return gaps


def _classify_cdc_title(title: str) -> str:
    """Heuristically classify a CDC headline into a health category."""
    t = title.lower()
    if any(kw in t for kw in ("flu", "influenza", "cold", "respiratory", "covid")):
        return "respiratory"
    if any(kw in t for kw in ("vaccine", "vaccination", "immuniz")):
        return "vaccination"
    if any(kw in t for kw in ("food", "outbreak", "salmonella", "e. coli", "listeria")):
        return "food_safety"
    if any(kw in t for kw in ("cancer", "tumor", "oncol")):
        return "chronic_disease"
    if any(kw in t for kw in ("mental", "depression", "anxiety", "suicide")):
        return "mental_health"
    if any(kw in t for kw in ("allerg", "pollen", "asthma")):
        return "seasonal_health"
    return "general_health"
