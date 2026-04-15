# Legal Engine Guidelines v1

## Data Sources
- Federal Register API: federal rules and proposed rules (public, no key)
- IRS news: tax announcements and guidance (public RSS)
- State legislature: MN-focused property and consumer protection

## Priority Areas
- Tax changes affecting filing deadlines or deductions → urgent tax_alert
- Healthcare regulation changes → household_impact required
- Property/housing regulations → home_alert to Home Specialist
- Consumer protection changes affecting finances → tax_alert or regulatory_alert

## Quality Standards
- All regulatory changes should have household_impact within 24h of ingestion
- action_required field must be populated if any filing/response deadline exists
- Federal regulations from Federal Register are highest confidence (0.8+)
