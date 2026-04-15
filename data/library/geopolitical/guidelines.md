# Geopolitical Engine Guidelines v1

## Data Sources
- GDELT Project: world event articles (public, no key required)
- Congress.gov: US federal legislation (requires JARVIS_CONGRESS_API_KEY)
- RSS feeds: world news (configure via JARVIS_GEOPOLITICAL_FEEDS)

## Relevance Criteria
- Severity scoring: use GDELT tone score (negative tone = higher severity)
- Market impact: conflicts affecting oil, tech, or major economies → financial alert
- Policy tracking: bills affecting taxes, healthcare, trade → cross-post to finance specialist

## Alert Thresholds
- Event severity > 0.7: post to blackboard with urgency "high"
- US Congress bill with economic impact: post "market_alert" to blackboard
- Sanctions or trade restrictions: post "investor_alert" to blackboard
