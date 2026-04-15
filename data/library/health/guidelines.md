# Health & Wellness Guidelines

## Purpose
Jarvis monitors environmental and health conditions to proactively protect household wellbeing.
This engine runs twice daily (7 AM / 7 PM) to capture morning and evening changes.

## Air Quality
- AQI 0–50: Good — safe for all outdoor activities
- AQI 51–100: Moderate — sensitive groups should limit prolonged outdoor exertion
- AQI 101–150: Unhealthy for Sensitive Groups — children and elderly should reduce outdoor time
- AQI 151–200: Unhealthy — everyone should limit outdoor exertion
- AQI 201–300: Very Unhealthy — avoid all outdoor activity
- AQI 301+: Hazardous — stay indoors, use air purifiers

## Seasonal Health Priorities
- **Spring (Mar–May):** Allergy season — pollen alerts, antihistamine readiness
- **Summer (Jun–Aug):** Heat safety, UV index, hydration reminders
- **Fall (Sep–Nov):** Flu vaccination reminders (September), respiratory illness uptick
- **Winter (Dec–Feb):** Cold/flu peak, Vitamin D supplementation, indoor air quality

## Data Sources
- AirNow: Real-time AQI by zip code (free API key required from airnow.gov)
- CDC: Official health alerts and seasonal guidance
- OpenFDA: Drug adverse event monitoring (no key required)

## Household Configuration
- Set `JARVIS_HOME_ZIP` for accurate local AQI readings
- Set `JARVIS_AIRNOW_API_KEY` to enable real-time air quality monitoring
- AQI threshold alerts post to blackboard at level 100+
