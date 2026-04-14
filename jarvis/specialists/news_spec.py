from __future__ import annotations
import logging
from jarvis.specialists import register
from jarvis.specialists.base import BaseSpecialist, Insight

logger = logging.getLogger(__name__)


@register
class NewsSpec(BaseSpecialist):
    name = "news_specialist"
    domain = "news"
    schedule = "0 */3 * * *"

    def gather(self) -> list[dict]:
        """Fetch headlines from configured RSS feeds."""
        from jarvis import config
        feed_urls = config.NEWS_FEED_URLS
        items = []
        if not feed_urls:
            return items

        import urllib.request
        import xml.etree.ElementTree as ET

        for url in feed_urls[:5]:  # cap at 5 feeds
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = resp.read()
                root = ET.fromstring(data)
                # Support RSS 2.0 and Atom
                for item in root.iter("item"):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "")
                    desc = item.findtext("description", "")
                    if title:
                        items.append({"title": title, "link": link, "description": desc[:300]})
                for entry in root.iter("{http://www.w3.org/2005/Atom}entry"):
                    title_el = entry.find("{http://www.w3.org/2005/Atom}title")
                    link_el = entry.find("{http://www.w3.org/2005/Atom}link")
                    title = title_el.text if title_el is not None else ""
                    link = link_el.get("href", "") if link_el is not None else ""
                    if title:
                        items.append({"title": title, "link": link, "description": ""})
            except Exception as exc:
                logger.warning("NewsSpec feed fetch failed for %s: %s", url, exc)
        return items

    def analyze(self, gathered: list[dict], cross_context: dict | None = None) -> list[Insight]:
        if not gathered:
            return []

        headlines = "\n".join(
            f"- {item.get('title', '')} {item.get('description', '')[:100]}"
            for item in gathered[:20]
        )
        prompt = (
            "You are analyzing news headlines for household relevance.\n\n"
            f"Headlines:\n{headlines}\n\n"
            "Classify each relevant headline by type:\n"
            "[FINANCE]: market/economy news\n"
            "[LOCAL]: local/community news\n"
            "[WEATHER]: weather alerts\n"
            "[TECH]: technology news\n"
            "[ALERT]: urgent news requiring immediate attention\n"
            "Only output lines in format [TYPE]: <summary>. Skip irrelevant headlines.\n"
        )

        insights = []
        try:
            from jarvis.core import _ask_ollama
            injected = self.context_engine.inject(self.domain, prompt)
            raw = _ask_ollama(injected, model=self.model)
            for line in raw.strip().splitlines():
                line = line.strip()
                for tag in ("[FINANCE]", "[LOCAL]", "[WEATHER]", "[TECH]", "[ALERT]"):
                    if line.startswith(tag):
                        content = line[len(tag):].strip().lstrip(":").strip()
                        insights.append(Insight(
                            fact_type="knowledge",
                            content=content,
                            confidence=0.6,
                            tags=f"news,{tag.strip('[]').lower()}",
                        ))
                        if tag == "[ALERT]":
                            self.blackboard.post(
                                agent=self.name, topic="news_alert",
                                content=content, urgency="urgent",
                            )
        except Exception as exc:
            logger.warning("NewsSpec.analyze LLM error: %s", exc)
        return insights

    def improve(self, insights: list[Insight] | None = None) -> list[str]:
        gaps: list[str] = []
        from jarvis import config
        if not config.NEWS_FEED_URLS:
            self.blackboard.post(
                agent=self.name, topic="news",
                content="No RSS feeds configured. Set JARVIS_NEWS_FEEDS env var.",
                urgency="low",
            )
            gaps.append("No RSS feeds configured.")
        return gaps
