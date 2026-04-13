"""
WeatherAdapter — live weather via OpenWeatherMap free tier.

Env vars:
    OPENWEATHER_API_KEY  — required for live data (free at openweathermap.org)
    OPENWEATHER_CITY     — overrides preferences city (default: Minneapolis,US)

Capabilities:
    current   → {temp_f, feels_like_f, description, humidity, wind_mph, city, icon}
    forecast  → 5-day summary [{date, high_f, low_f, description}]
    alerts    → active weather alerts for the area
"""
from __future__ import annotations
import os
from collections import defaultdict
from typing import Any

import requests

from jarvis.adapters.base import BaseAdapter, AdapterResult

_OWM_BASE = "https://api.openweathermap.org/data/2.5"


def _kelvin_to_f(k: float) -> float:
    return round((k - 273.15) * 9 / 5 + 32, 1)


def _mps_to_mph(mps: float) -> float:
    return round(mps * 2.23694, 1)


class WeatherAdapter(BaseAdapter):
    name = "weather"
    description = "Current weather, forecasts, severe weather alerts (OpenWeatherMap)"
    capabilities = ["current", "forecast", "alerts"]

    def _api_key(self) -> str:
        return os.getenv("OPENWEATHER_API_KEY", "")

    def _city(self, params: dict) -> str:
        city = params.get("city") or os.getenv("OPENWEATHER_CITY", "")
        if not city:
            try:
                from jarvis.preferences import get as prefs_get
                city = prefs_get("city", "Minneapolis,US")
            except Exception:
                city = "Minneapolis,US"
        return city

    def _not_configured(self) -> AdapterResult:
        return AdapterResult(
            success=False,
            text=(
                "Weather adapter not configured. "
                "Set OPENWEATHER_API_KEY (free at openweathermap.org)."
            ),
            adapter=self.name,
        )

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        key = self._api_key()
        if not key:
            return self._not_configured()

        city = self._city(params)

        try:
            if capability == "current":
                return self._current(key, city)
            elif capability == "forecast":
                return self._forecast(key, city)
            elif capability == "alerts":
                return self._alerts(key, city)
            else:
                return AdapterResult(
                    success=False,
                    text=f"[weather] Unknown capability: {capability}",
                    adapter=self.name,
                )
        except requests.exceptions.ConnectionError:
            return AdapterResult(
                success=False,
                text="[weather] Cannot reach OpenWeatherMap API.",
                adapter=self.name,
            )
        except requests.exceptions.HTTPError as e:
            return AdapterResult(
                success=False,
                text=f"[weather] API error: {e}",
                adapter=self.name,
            )

    def _current(self, key: str, city: str) -> AdapterResult:
        r = requests.get(
            f"{_OWM_BASE}/weather",
            params={"q": city, "appid": key},
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        data = {
            "temp_f": _kelvin_to_f(d["main"]["temp"]),
            "feels_like_f": _kelvin_to_f(d["main"]["feels_like"]),
            "description": d["weather"][0]["description"],
            "humidity": d["main"]["humidity"],
            "wind_mph": _mps_to_mph(d["wind"]["speed"]),
            "city": d["name"],
            "icon": d["weather"][0].get("icon", ""),
        }
        text = (
            f"{data['city']}: {data['temp_f']}°F, {data['description']}. "
            f"Feels like {data['feels_like_f']}°F. "
            f"Humidity {data['humidity']}%. Wind {data['wind_mph']} mph."
        )
        return AdapterResult(success=True, text=text, data=data, adapter=self.name)

    def _forecast(self, key: str, city: str) -> AdapterResult:
        r = requests.get(
            f"{_OWM_BASE}/forecast",
            params={"q": city, "appid": key, "cnt": 40},
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()

        # Group by date (OWM returns 3-hour intervals)
        days: dict[str, dict] = defaultdict(
            lambda: {"highs": [], "lows": [], "descriptions": []}
        )
        for item in d.get("list", []):
            date = item["dt_txt"][:10]
            days[date]["highs"].append(_kelvin_to_f(item["main"]["temp_max"]))
            days[date]["lows"].append(_kelvin_to_f(item["main"]["temp_min"]))
            days[date]["descriptions"].append(item["weather"][0]["description"])

        forecast = []
        for date in sorted(days)[:5]:
            day = days[date]
            mid = len(day["descriptions"]) // 2
            forecast.append({
                "date": date,
                "high_f": max(day["highs"]),
                "low_f": min(day["lows"]),
                "description": day["descriptions"][mid],
            })

        lines = [
            f"{f['date']}: {f['high_f']}°F / {f['low_f']}°F, {f['description']}"
            for f in forecast
        ]
        city_name = d.get("city", {}).get("name", city)
        return AdapterResult(
            success=True,
            text=f"5-day forecast for {city_name}:\n" + "\n".join(lines),
            data={"forecast": forecast, "city": city_name},
            adapter=self.name,
        )

    def _alerts(self, key: str, city: str) -> AdapterResult:
        # Get lat/lon from current weather endpoint first
        r = requests.get(
            f"{_OWM_BASE}/weather",
            params={"q": city, "appid": key},
            timeout=10,
        )
        r.raise_for_status()
        coords = r.json().get("coord", {})
        lat, lon = coords.get("lat"), coords.get("lon")
        if lat is None or lon is None:
            return AdapterResult(
                success=True,
                text="No active weather alerts.",
                data={"alerts": []},
                adapter=self.name,
            )

        # Try onecall v3 for alerts (may require subscription); fallback gracefully
        try:
            r2 = requests.get(
                "https://api.openweathermap.org/data/3.0/onecall",
                params={
                    "lat": lat,
                    "lon": lon,
                    "appid": key,
                    "exclude": "minutely,hourly,daily,current",
                },
                timeout=10,
            )
            r2.raise_for_status()
            alerts = r2.json().get("alerts", [])
            if not alerts:
                return AdapterResult(
                    success=True,
                    text="No active weather alerts.",
                    data={"alerts": []},
                    adapter=self.name,
                )
            alert_texts = [
                f"{a.get('event', 'Alert')}: {a.get('description', '')[:200]}"
                for a in alerts
            ]
            return AdapterResult(
                success=True,
                text="\n".join(alert_texts),
                data={"alerts": alerts},
                adapter=self.name,
            )
        except Exception:
            return AdapterResult(
                success=True,
                text="No active weather alerts (alerts endpoint requires subscription).",
                data={"alerts": []},
                adapter=self.name,
            )
