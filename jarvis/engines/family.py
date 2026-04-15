"""Engine 7 — Family & Life Quality.

Aggregates outdoor activity options (NPS parks), cross-references local events
from the Knowledge Lake, and fetches evidence-based parenting research (AAP RSS).
Runs the proactive analyze() cycle that generates concrete weekend/activity
suggestions and posts them to the SharedBlackboard.
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
class FamilyEngine(BaseKnowledgeEngine):
    """Engine 7 — Family & Life Quality.

    Data sources:
    - NPS (National Park Service) API — parks near home (JARVIS_NPS_API_KEY, free)
    - Knowledge Lake cross-reference — family_friendly local events from Engine 6
    - AAP / parenting research RSS (public)

    Schedule: Monday and Thursday at 6 AM — pre-weekend and mid-week refresh.
    """

    name = "family_engine"
    domain = "family"
    schedule = "0 6 * * 1,4"

    def gather(self) -> list[dict]:
        """Fetch parks, cross-reference local events, and pull parenting research."""
        from jarvis import config
        items: list[dict] = []

        # Source 1: NPS parks near home state (key optional)
        items.extend(self._fetch_nps_parks(config.NPS_API_KEY))

        # Source 2: Cross-reference family-friendly events already in Knowledge Lake
        items.extend(self._crossref_local_events())

        # Source 3: Parenting/child development research (public RSS)
        items.extend(self._fetch_parenting_rss())

        return items

    def _fetch_nps_parks(self, api_key: str) -> list[dict]:
        """Fetch national and state parks from NPS API (MN by default)."""
        if not api_key:
            logger.debug("FamilyEngine: NPS_API_KEY not set, skipping park data")
            return []

        # Derive state from lat/lon via simple zone check
        from jarvis import config
        state_code = _lat_lon_to_state(config.HOME_LAT, config.HOME_LON)
        url = (
            f"https://developer.nps.gov/api/v1/parks"
            f"?stateCode={state_code}&limit=20&api_key={api_key}"
        )
        results: list[dict] = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode())
            for park in data.get("data", [])[:20]:
                activities = [a.get("name", "") for a in park.get("activities", [])[:5]]
                results.append({
                    "type": "nps_park",
                    "name": park.get("fullName", park.get("name", "")),
                    "description": (park.get("description") or "")[:500],
                    "url": park.get("url", ""),
                    "state": state_code,
                    "designation": park.get("designation", ""),
                    "activities": activities,
                    "topics": [t.get("name", "") for t in park.get("topics", [])[:5]],
                    "latitude": park.get("latitude", ""),
                    "longitude": park.get("longitude", ""),
                })
        except Exception as exc:
            logger.warning("NPS park fetch failed: %s", exc)
        return results

    def _crossref_local_events(self) -> list[dict]:
        """Pull family-friendly events already stored in the Knowledge Lake."""
        results: list[dict] = []
        try:
            rows = self.engine_store.query(
                "family", "local_events",
                where="family_friendly = 1",
                limit=20,
            )
            for row in rows:
                results.append({
                    "type": "crossref_event",
                    "title": row.get("title", ""),
                    "description": row.get("description", ""),
                    "event_date": row.get("event_date", ""),
                    "venue": row.get("venue", ""),
                    "cost": row.get("cost", ""),
                    "source_url": row.get("source_url", ""),
                })
        except Exception as exc:
            logger.warning("FamilyEngine: event cross-reference failed: %s", exc)
        return results

    def _fetch_parenting_rss(self) -> list[dict]:
        """Fetch evidence-based parenting content from public RSS feeds."""
        feed_urls = [
            "https://www.aap.org/en/news-room/aap-news/rss/",
            "https://healthychildren.org/SiteCollectionDocuments/AAP_News_RSS.xml",
        ]
        results: list[dict] = []
        for feed_url in feed_urls:
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
                            "type": "parenting_rss",
                            "title": title,
                            "description": desc[:500],
                            "url": link,
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
                            "type": "parenting_rss",
                            "title": t,
                            "description": s,
                            "url": lnk,
                            "feed": feed_url,
                        })
            except Exception as exc:
                logger.warning("Parenting RSS fetch failed for %s: %s", feed_url, exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data into RawItems for ingestion."""
        items: list[RawItem] = []
        now = _now()

        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "nps_park":
                name = raw.get("name", "")
                desc = raw.get("description", "")
                designation = raw.get("designation", "")
                activities = raw.get("activities", [])
                activity_str = ", ".join(activities[:5])
                content = f"Outdoor activity: {name} ({designation}). {desc[:300]}"
                if activity_str:
                    content += f" Activities: {activity_str}."
                items.append(RawItem(
                    content=content,
                    source="nps",
                    source_url=raw.get("url") or None,
                    fact_type="family_activities",
                    domain=self.domain,
                    structured_data={
                        "category": "outdoor",
                        "title": name,
                        "description": desc[:1000],
                        "location": raw.get("state", ""),
                        "distance_miles": None,
                        "cost_estimate": "Free" if "national" in designation.lower() else "Varies",
                        "age_appropriate": "all_ages",
                        "duration": "half_day_to_full_day",
                        "season": "spring,summer,fall",
                        "weather_req": "clear_preferred",
                        "source": "nps",
                        "source_url": raw.get("url", ""),
                        "rating": 0.8,
                    },
                    quality_hint=0.8,
                    tags=f"family,outdoor,park,nps,{raw.get('state', '').lower()}",
                ))

            elif data_type == "crossref_event":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                event_date = raw.get("event_date", now[:10])
                venue = raw.get("venue", "")
                cost = raw.get("cost", "")
                content = f"Family event: {title} at {venue} on {event_date}. {desc[:200]}"
                items.append(RawItem(
                    content=content,
                    source="local_intel_crossref",
                    source_url=raw.get("source_url") or None,
                    fact_type="family_activities",
                    domain=self.domain,
                    structured_data={
                        "category": "event",
                        "title": title,
                        "description": desc[:1000],
                        "location": venue,
                        "distance_miles": None,
                        "cost_estimate": cost or "Check venue",
                        "age_appropriate": "all_ages",
                        "duration": "varies",
                        "season": "all",
                        "weather_req": "indoor",
                        "source": "local_intel_crossref",
                        "source_url": raw.get("source_url", ""),
                        "rating": 0.6,
                    },
                    quality_hint=0.6,
                    tags="family,event,local,community",
                ))

            elif data_type == "parenting_rss":
                title = raw.get("title", "")
                desc = raw.get("description", "")
                url = raw.get("url", "")
                category = _classify_parenting_title(title)
                age_range = _infer_age_range(title + " " + desc)
                is_actionable = int(any(
                    kw in (title + desc).lower()
                    for kw in ("tip", "how to", "guide", "strategy", "step", "recommend", "should")
                ))
                is_seasonal = int(any(
                    kw in (title + desc).lower()
                    for kw in ("summer", "winter", "spring", "fall", "back to school", "holiday")
                ))
                content = f"Parenting research: {title}. {desc[:300]}"
                items.append(RawItem(
                    content=content,
                    source="aap",
                    source_url=url or None,
                    fact_type="parenting_knowledge",
                    domain=self.domain,
                    structured_data={
                        "category": category,
                        "age_range": age_range,
                        "title": title,
                        "content": desc[:2000] or title,
                        "source": raw.get("feed", "aap"),
                        "evidence_level": "professional_guidance",
                        "actionable": is_actionable,
                        "seasonal": is_seasonal,
                    },
                    quality_hint=0.75,
                    tags=f"family,parenting,{category},{age_range.replace('-', '_')}",
                ))

        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        """Proactive quality-of-life engine: generate weekend activity suggestions.

        Cross-references:
        - Weather forecast from Local Intel (via blackboard or engine_store)
        - Finance status (via knowledge lake if available)
        - Available parks and events from this cycle's gather()
        """
        insights: list[Insight] = []

        # Collect candidate activities from this cycle
        park_items = [g for g in gathered if g.get("type") == "nps_park"]
        event_items = [g for g in gathered if g.get("type") == "crossref_event"]

        # Get weather context from Local Intel's blackboard posts
        weather_context = _get_weather_context()

        if not park_items and not event_items:
            return insights

        # Build suggestion content
        suggestions: list[str] = []

        for park in park_items[:2]:
            name = park.get("name", "")
            activities = ", ".join(park.get("activities", [])[:3])
            suggestions.append(f"Outdoor: {name}" + (f" ({activities})" if activities else ""))

        for event in event_items[:1]:
            title = event.get("title", "")
            date = event.get("event_date", "")
            venue = event.get("venue", "")
            suggestions.append(f"Event: {title}" + (f" at {venue} on {date}" if venue else ""))

        if suggestions:
            suggestion_text = "Family activity suggestions: " + " | ".join(suggestions)
            if weather_context:
                suggestion_text = f"{weather_context} — {suggestion_text}"

            try:
                from jarvis.blackboard import SharedBlackboard
                bb = SharedBlackboard()
                bb.post(
                    topic="family_suggestion",
                    content=suggestion_text,
                    author=self.name,
                )
                logger.info("FamilyEngine: posted %d family suggestions to blackboard", len(suggestions))
            except Exception as exc:
                logger.warning("FamilyEngine: blackboard post failed: %s", exc)

        return insights

    def improve(self) -> list[str]:
        """Track data freshness and queue seasonal research."""
        from jarvis import config
        gaps: list[str] = []

        if not config.NPS_API_KEY:
            gaps.append("NPS API key not configured — park/trail data unavailable")

        # Check for stale activity data
        try:
            count = self.engine_store.count("family", "family_activities")
            if count == 0:
                gaps.append("No family activities in store — NPS key may be needed")
        except Exception:
            pass

        return gaps


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _lat_lon_to_state(lat: str, lon: str) -> str:
    """Coarse lat/lon to US state code for NPS query."""
    try:
        la = float(lat)
        lo = float(lon)
    except (ValueError, TypeError):
        return "MN"

    # Minnesota bounding box: lat 43.5–49.4, lon -97.2 to -89.5
    if 43.5 <= la <= 49.4 and -97.2 <= lo <= -89.5:
        return "MN"
    # Wisconsin
    if 42.5 <= la <= 47.1 and -92.9 <= lo <= -86.2:
        return "WI"
    # Colorado
    if 37.0 <= la <= 41.1 and -109.1 <= lo <= -102.0:
        return "CO"
    # California
    if 32.5 <= la <= 42.0 and -124.5 <= lo <= -114.1:
        return "CA"
    return "MN"


def _get_weather_context() -> str:
    """Attempt to fetch upcoming weekend weather summary from blackboard."""
    try:
        from jarvis.blackboard import SharedBlackboard
        bb = SharedBlackboard()
        posts = bb.get_recent(topic="activity_suggestion", limit=1)
        if posts:
            return posts[0].get("content", "")[:200]
    except Exception:
        pass
    return ""


def _classify_parenting_title(title: str) -> str:
    """Classify a parenting article headline."""
    t = title.lower()
    if any(kw in t for kw in ("screen", "technology", "device", "digital", "phone", "tablet")):
        return "screen_time"
    if any(kw in t for kw in ("sleep", "nap", "bedtime", "night")):
        return "sleep"
    if any(kw in t for kw in ("nutrition", "food", "eat", "diet", "obesity", "weight")):
        return "nutrition"
    if any(kw in t for kw in ("vaccine", "vaccination", "immuniz", "shot")):
        return "vaccination"
    if any(kw in t for kw in ("mental", "anxiety", "depression", "emotional", "stress")):
        return "mental_health"
    if any(kw in t for kw in ("learning", "school", "reading", "education", "development")):
        return "development"
    if any(kw in t for kw in ("exercise", "sport", "physical", "active", "play")):
        return "physical_activity"
    if any(kw in t for kw in ("safety", "injury", "accident", "car seat", "helmet")):
        return "safety"
    return "general_parenting"


def _infer_age_range(text: str) -> str:
    """Infer target age range from article text."""
    t = text.lower()
    if any(kw in t for kw in ("infant", "newborn", "baby", "0-12 month", "under 1")):
        return "0-1"
    if any(kw in t for kw in ("toddler", "1-3", "1 to 3", "age 2", "age 3")):
        return "1-3"
    if any(kw in t for kw in ("preschool", "3-5", "age 4", "age 5", "kindergarten")):
        return "3-5"
    if any(kw in t for kw in ("school-age", "6-12", "elementary", "grade school")):
        return "6-12"
    if any(kw in t for kw in ("teen", "adolescent", "13-18", "high school", "middle school")):
        return "13-18"
    return "all_ages"
