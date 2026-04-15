"""Engine 6 — Local Intelligence.

Fetches NWS weather forecasts, Eventbrite local events, and configurable
local government/news RSS feeds. Cross-wires weather data to the Family
Engine via the SharedBlackboard for activity suggestions.
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
from jarvis.memory_tiers.types import Insight

logger = logging.getLogger(__name__)

_RSS_NS = "http://www.w3.org/2005/Atom"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@register_engine
class LocalIntelEngine(BaseKnowledgeEngine):
    """Engine 6 — Local Intelligence.

    Data sources:
    - NWS Weather API (public, no key needed)
    - Eventbrite event search (JARVIS_EVENTBRITE_TOKEN optional)
    - Configurable local RSS feeds (JARVIS_LOCAL_FEEDS)

    Schedule: daily at 8 AM for fresh morning briefing.
    """

    name = "local_intel_engine"
    domain = "local"
    schedule = "0 8 * * *"

    def gather(self) -> list[dict]:
        """Fetch weather forecast, local events, and local news."""
        from jarvis import config
        items: list[dict] = []

        # Source 1: NWS weather forecast (no key needed)
        items.extend(self._fetch_nws_forecast(config.HOME_LAT, config.HOME_LON))

        # Source 2: Eventbrite events (token optional)
        if config.EVENTBRITE_TOKEN:
            items.extend(self._fetch_eventbrite(
                config.HOME_LAT, config.HOME_LON, config.EVENTBRITE_TOKEN
            ))
        else:
            logger.debug("LocalIntelEngine: EVENTBRITE_TOKEN not set, skipping events")

        # Source 3: Configured local RSS feeds
        for feed_url in config.LOCAL_FEEDS:
            items.extend(self._fetch_local_rss(feed_url))

        return items

    def _fetch_nws_forecast(self, lat: str, lon: str) -> list[dict]:
        """Fetch 7-day forecast from National Weather Service API."""
        results: list[dict] = []
        try:
            # Step 1: resolve points → forecast URL
            points_url = f"https://api.weather.gov/points/{lat},{lon}"
            req = urllib.request.Request(
                points_url,
                headers={"User-Agent": "Jarvis/1.0 (household-ai)", "Accept": "application/geo+json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                points_data = json.loads(resp.read().decode())
            forecast_url = (
                points_data.get("properties", {}).get("forecast", "")
            )
            if not forecast_url:
                logger.warning("NWS: no forecast URL returned for %s,%s", lat, lon)
                return results

            # Step 2: fetch the actual forecast
            req2 = urllib.request.Request(
                forecast_url,
                headers={"User-Agent": "Jarvis/1.0 (household-ai)", "Accept": "application/geo+json"},
            )
            with urllib.request.urlopen(req2, timeout=15) as resp2:
                forecast_data = json.loads(resp2.read().decode())

            periods = forecast_data.get("properties", {}).get("periods", [])
            for period in periods[:14]:  # up to 14 periods (~7 days)
                results.append({
                    "type": "nws_weather",
                    "name": period.get("name", ""),
                    "temperature": period.get("temperature"),
                    "temperature_unit": period.get("temperatureUnit", "F"),
                    "wind_speed": period.get("windSpeed", ""),
                    "wind_direction": period.get("windDirection", ""),
                    "short_forecast": period.get("shortForecast", ""),
                    "detailed_forecast": period.get("detailedForecast", ""),
                    "is_daytime": period.get("isDaytime", True),
                    "start_time": period.get("startTime", ""),
                    "end_time": period.get("endTime", ""),
                    "location": f"{lat},{lon}",
                    "source_url": forecast_url,
                })
        except Exception as exc:
            logger.warning("NWS forecast fetch failed for %s,%s: %s", lat, lon, exc)
        return results

    def _fetch_eventbrite(self, lat: str, lon: str, token: str) -> list[dict]:
        """Fetch local events from Eventbrite."""
        url = (
            f"https://www.eventbriteapi.com/v3/events/search/"
            f"?location.latitude={lat}&location.longitude={lon}"
            f"&location.within=25mi&expand=venue&token={token}"
        )
        results: list[dict] = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            for event in data.get("events", [])[:20]:
                venue = event.get("venue") or {}
                results.append({
                    "type": "eventbrite",
                    "title": (event.get("name") or {}).get("text", ""),
                    "description": ((event.get("description") or {}).get("text") or "")[:500],
                    "start_time": (event.get("start") or {}).get("local", ""),
                    "end_time": (event.get("end") or {}).get("local", ""),
                    "venue_name": venue.get("name", ""),
                    "address": (venue.get("address") or {}).get("localized_address_display", ""),
                    "is_free": event.get("is_free", False),
                    "url": event.get("url", ""),
                    "category_id": event.get("category_id", ""),
                })
        except Exception as exc:
            logger.warning("Eventbrite fetch failed: %s", exc)
        return results

    def _fetch_local_rss(self, feed_url: str) -> list[dict]:
        """Fetch headlines from a local RSS/Atom feed."""
        results: list[dict] = []
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            root = ET.fromstring(data)
            ns = {"atom": _RSS_NS}
            # RSS 2.0
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                desc = item.findtext("description", "").strip()
                if title:
                    results.append({
                        "type": "local_rss",
                        "title": title,
                        "url": link,
                        "description": desc[:500],
                        "feed": feed_url,
                    })
            # Atom
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                link_el = entry.find("atom:link", ns)
                summary_el = entry.find("atom:summary", ns)
                t = title_el.text.strip() if title_el is not None and title_el.text else ""
                lnk = link_el.get("href", "") if link_el is not None else ""
                s = summary_el.text.strip()[:500] if summary_el is not None and summary_el.text else ""
                if t:
                    results.append({
                        "type": "local_rss",
                        "title": t,
                        "url": lnk,
                        "description": s,
                        "feed": feed_url,
                    })
        except Exception as exc:
            logger.warning("Local RSS fetch failed for %s: %s", feed_url, exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data into RawItems for ingestion."""
        items: list[RawItem] = []
        now = _now()

        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "nws_weather":
                period_name = raw.get("name", "")
                temp = raw.get("temperature")
                unit = raw.get("temperature_unit", "F")
                forecast = raw.get("short_forecast", "")
                detailed = raw.get("detailed_forecast", "")
                location = raw.get("location", "")
                start_time = raw.get("start_time", now[:10])
                content = (
                    f"Weather forecast for {period_name}: {temp}°{unit}, {forecast}. "
                    f"{detailed[:200]}"
                )
                items.append(RawItem(
                    content=content,
                    source="nws",
                    source_url=raw.get("source_url"),
                    fact_type="local_data",
                    domain=self.domain,
                    structured_data={
                        "category": "weather",
                        "title": f"Weather: {period_name}",
                        "content": detailed[:1000] or forecast,
                        "location": location,
                        "data_date": start_time[:10] if start_time else now[:10],
                        "source": "nws",
                        "source_url": raw.get("source_url", ""),
                        "trend": forecast,
                    },
                    quality_hint=0.9,
                    tags=f"local,weather,nws,{period_name.lower().replace(' ', '_')}",
                ))

            elif data_type == "eventbrite":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                start = raw.get("start_time", "")
                venue = raw.get("venue_name", "")
                address = raw.get("address", "")
                is_free = raw.get("is_free", False)
                cost_str = "Free" if is_free else "Paid"
                content = f"Local event: {title} at {venue}. {desc[:200]}"
                items.append(RawItem(
                    content=content,
                    source="eventbrite",
                    source_url=raw.get("url"),
                    fact_type="local_events",
                    domain=self.domain,
                    structured_data={
                        "title": title,
                        "description": desc,
                        "venue": venue,
                        "address": address,
                        "event_date": start[:10] if start else now[:10],
                        "event_time": start[11:16] if len(start) > 10 else "",
                        "cost": cost_str,
                        "category": "community",
                        "family_friendly": 1,
                        "source": "eventbrite",
                        "source_url": raw.get("url", ""),
                    },
                    quality_hint=0.7,
                    tags="local,event,eventbrite,community",
                ))

            elif data_type == "local_rss":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                url = raw.get("url", "")
                category = _classify_local_title(title)
                content = f"Local news: {title}. {desc[:200]}"
                items.append(RawItem(
                    content=content,
                    source="local_rss",
                    source_url=url or None,
                    fact_type="local_data",
                    domain=self.domain,
                    structured_data={
                        "category": category,
                        "title": title,
                        "content": desc[:1000] or title,
                        "location": "",
                        "data_date": now[:10],
                        "source": raw.get("feed", "local_rss"),
                        "source_url": url,
                        "trend": "",
                    },
                    quality_hint=0.5,
                    tags=f"local,news,{category}",
                ))

        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        """Post activity suggestions when nice weekend weather is forecast."""
        insights: list[Insight] = []
        weather_items = [g for g in gathered if g.get("type") == "nws_weather"]
        nice_periods = []
        for w in weather_items:
            name = w.get("name", "").lower()
            temp = w.get("temperature")
            forecast = w.get("short_forecast", "").lower()
            is_weekend = any(d in name for d in ("saturday", "sunday", "sat", "sun"))
            is_nice = (
                temp is not None
                and 60 <= int(temp) <= 85
                and not any(kw in forecast for kw in ("rain", "storm", "snow", "thunder"))
            )
            if is_weekend and is_nice:
                nice_periods.append(w)

        if nice_periods:
            try:
                from jarvis.blackboard import SharedBlackboard
                bb = SharedBlackboard()
                summary = "; ".join(
                    f"{p['name']}: {p['temperature']}°F, {p['short_forecast']}"
                    for p in nice_periods[:3]
                )
                bb.post(
                    topic="activity_suggestion",
                    content=f"Nice weekend weather detected: {summary}. Good time for outdoor activities.",
                    author=self.name,
                )
                logger.info("LocalIntelEngine: posted activity_suggestion to blackboard (%d nice periods)", len(nice_periods))
            except Exception as exc:
                logger.warning("LocalIntelEngine: blackboard post failed: %s", exc)

        return insights

    def improve(self) -> list[str]:
        """Check for stale event data or missing weather forecasts."""
        from jarvis import config
        gaps: list[str] = []

        if not config.EVENTBRITE_TOKEN:
            gaps.append("Eventbrite token not configured — local event data unavailable")

        if not config.LOCAL_FEEDS:
            gaps.append("No local RSS feeds configured — add JARVIS_LOCAL_FEEDS to .env")

        # Check for stale weather data
        try:
            rows = self.engine_store.query(
                "local", "local_data",
                where="category = 'weather' AND data_date < date('now', '-2 days')",
                limit=5,
            )
            if rows:
                gaps.append(f"Stale weather data: {len(rows)} records older than 2 days")
        except Exception:
            pass

        return gaps


def _classify_local_title(title: str) -> str:
    """Heuristically classify a local news headline."""
    t = title.lower()
    # Infrastructure — use word-boundary aware patterns to avoid "broadway" matching "road"
    if any(kw in t for kw in ("road closure", "road closures", "lane closure", "construction",
                               "traffic alert", "bridge repair", "bridge closure",
                               "highway", "freeway", "i-35", "i-94", "water main")):
        return "infrastructure"
    if any(kw in t for kw in ("school", "education", "district", "student", "teacher")):
        return "education"
    if any(kw in t for kw in ("crime", "police", "arrest", "safety", "fire department")):
        return "public_safety"
    if any(kw in t for kw in ("tax", "budget", "council", "city vote", "vote on",
                               "election", "city approves", "city council")):
        return "government"
    if any(kw in t for kw in ("park", "trail", "recreation", "festival", "farmers market")):
        return "recreation"
    if any(kw in t for kw in ("business", "restaurant", "store", "retail", "opens downtown",
                               "grand opening")):
        return "business"
    # Generic fallbacks for road/fire/open that are less specific
    if any(kw in t for kw in (" road ", "road\n", "fire ", " fire")):
        return "infrastructure"
    return "general"
