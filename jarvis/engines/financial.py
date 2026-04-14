from __future__ import annotations
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone

from jarvis.engines import register_engine
from jarvis.engines.base_engine import BaseKnowledgeEngine
from jarvis.ingestion import RawItem

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

@register_engine
class FinancialEngine(BaseKnowledgeEngine):
    """Engine 1 — Financial & Economic Intelligence.

    Fetches economic indicators (FRED), market data (Yahoo Finance),
    and SEC filings (EDGAR). Requires JARVIS_FRED_API_KEY for FRED.
    """

    name = "financial_engine"
    domain = "financial"
    schedule = "0 */4 * * *"

    def gather(self) -> list[dict]:
        """Fetch economic indicators, market data, and SEC filings."""
        from jarvis import config
        items = []

        # FRED economic indicators (requires API key)
        if config.FRED_API_KEY:
            items.extend(self._fetch_fred_indicators(config.FRED_API_KEY))
        else:
            logger.debug("FinancialEngine: FRED_API_KEY not set, skipping economic indicators")

        # Market data via Yahoo Finance (public)
        items.extend(self._fetch_market_data(config.TRACKED_SYMBOLS))

        return items

    def _fetch_fred_indicators(self, api_key: str) -> list[dict]:
        """Fetch key economic series from FRED API."""
        series_ids = ["GDP", "UNRATE", "CPIAUCSL", "FEDFUNDS"]
        results = []
        for series_id in series_ids:
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={api_key}&file_type=json&limit=1&sort_order=desc"
            )
            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                observations = data.get("observations", [])
                if observations:
                    obs = observations[0]
                    results.append({
                        "type": "fred",
                        "series_id": series_id,
                        "value": obs.get("value", ""),
                        "period": obs.get("date", ""),
                        "source_url": url,
                    })
            except Exception as exc:
                logger.warning("FRED fetch failed for %s: %s", series_id, exc)
        return results

    def _fetch_market_data(self, symbols: list[str]) -> list[dict]:
        """Fetch latest market data from Yahoo Finance."""
        results = []
        for symbol in symbols:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Jarvis/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
                result = data.get("chart", {}).get("result", [])
                if result:
                    meta = result[0].get("meta", {})
                    price = meta.get("regularMarketPrice")
                    prev = meta.get("previousClose")
                    if price:
                        results.append({
                            "type": "market",
                            "symbol": symbol,
                            "price": price,
                            "prev_close": prev,
                            "date": _now()[:10],
                            "source_url": url,
                        })
            except Exception as exc:
                logger.warning("Market data fetch failed for %s: %s", symbol, exc)
        return results

    def prepare_items(self, raw_data: list[dict]) -> list[RawItem]:
        """Convert gathered data to RawItems for ingestion."""
        items = []
        for raw in raw_data:
            data_type = raw.get("type", "")

            if data_type == "fred":
                series_id = raw.get("series_id", "")
                value = raw.get("value", "")
                period = raw.get("period", "")
                content = f"Economic indicator {series_id}: {value} for period {period}"
                items.append(RawItem(
                    content=content,
                    source="fred",
                    source_url=raw.get("source_url"),
                    fact_type="economic_indicator",
                    domain=self.domain,
                    structured_data={
                        "series_id": series_id,
                        "value": float(value) if value and value != "." else 0.0,
                        "period": period,
                        "frequency": "monthly",
                        "source": "FRED",
                        "retrieved_at": _now(),
                    },
                    quality_hint=0.6,
                    tags=f"financial,economic,{series_id.lower()}",
                ))

            elif data_type == "market":
                symbol = raw.get("symbol", "")
                price = raw.get("price", 0)
                prev = raw.get("prev_close")
                date = raw.get("date", _now()[:10])
                pct_chg = ""
                if prev and prev > 0:
                    chg = (price - prev) / prev * 100
                    pct_chg = f" ({chg:+.2f}%)"
                content = f"Market data {symbol}: ${price:.2f}{pct_chg} on {date}"
                items.append(RawItem(
                    content=content,
                    source="yahoo_finance",
                    source_url=raw.get("source_url"),
                    fact_type="market_data",
                    domain=self.domain,
                    structured_data={
                        "symbol": symbol,
                        "date": date,
                        "close": price,
                        "source": "yahoo_finance",
                    },
                    quality_hint=0.5,
                    tags=f"financial,market,{symbol.lower().replace('-','_')}",
                ))

        return items

    def improve(self) -> list[str]:
        """Identify data gaps and post alerts for significant market moves."""
        gaps = []
        from jarvis import config

        if not config.FRED_API_KEY:
            gaps.append("FRED API key not configured — economic indicators unavailable")

        if not config.TRACKED_SYMBOLS:
            gaps.append("No tracked symbols configured")

        return gaps
