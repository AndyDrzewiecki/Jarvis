# Family & Life Quality Guidelines

## Purpose
Jarvis is your household's quality-of-life co-pilot. This engine runs Monday and Thursday
to keep family activity suggestions fresh and aligned with current weather, budget, and schedule.

## Proactive Suggestions
The Family Engine's analyze() cycle cross-references:
1. **Weather** from Local Intel Engine (via SharedBlackboard "activity_suggestion" posts)
2. **Local events** already stored by Local Intel Engine
3. **Parks and trails** from NPS API
4. Suggestions are posted to SharedBlackboard under topic "family_suggestion"

Example suggestion format:
> "This Saturday looks clear, 72°F. Free hiking at Fort Snelling State Park (3 miles from home).
> Also: Minneapolis Farmers Market is open 6 AM–1 PM."

## Data Sources
- **NPS API** (free key from nps.gov → developer.nps.gov): Parks, trails, visitor centers
- **Local events cross-reference**: Pulls family_friendly events from Engine 6's data store
- **AAP RSS** (American Academy of Pediatrics): Evidence-based parenting guidance

## Configuration
- `JARVIS_NPS_API_KEY`: Free registration at https://www.nps.gov/subjects/developer/get-started.htm
- Location is derived from `JARVIS_HOME_LAT`/`JARVIS_HOME_LON` (same as Local Intel)

## Parenting Knowledge Categories
- screen_time, sleep, nutrition, vaccination, mental_health, development,
  physical_activity, safety, general_parenting

## Activity Categories
- outdoor (parks, trails, nature)
- event (community events, festivals, markets)
- indoor (museums, libraries, entertainment venues)
- travel (day trips, weekend getaways, vacation planning)

## Vacation Research
The `vacation_research` table accumulates trip ideas over time.
Each destination is tagged with: trip_type, estimated_cost, best_season,
kid_friendly flag, and household_interest score (0.0–1.0).
