# Local Intelligence Guidelines

## Purpose
Jarvis monitors the local environment daily (8 AM) to surface relevant conditions,
events, and opportunities for the household.

## Weather Integration
- Uses NWS (National Weather Service) — no API key required, highly reliable
- Fetches 7-day forecast for configured home coordinates
- Posts "activity_suggestion" to blackboard when nice weekend weather detected
  (conditions: 60–85°F, no rain/storm in forecast, Saturday or Sunday)
- Configure home coordinates: `JARVIS_HOME_LAT` and `JARVIS_HOME_LON`

## Local Events
- Eventbrite integration requires `JARVIS_EVENTBRITE_TOKEN` (free tier available)
- Events within 25 miles of home are captured and marked family_friendly=1 by default
- Events feed into Family Engine's activity suggestions automatically

## Local News Feeds
- Add RSS/Atom feeds via `JARVIS_LOCAL_FEEDS` (comma-separated URLs)
- Useful sources: city government RSS, local newspaper feeds, school district updates
- Headlines are classified automatically: infrastructure, education, public_safety,
  government, business, recreation, general

## Default Location: Minneapolis, MN
- Override with JARVIS_HOME_LAT and JARVIS_HOME_LON environment variables
- All weather forecasts and event searches use these coordinates

## Data Retention
- Weather forecasts refresh daily — stale data (>2 days) is flagged in improve()
- Events are stored persistently and cross-referenced by Family Engine
