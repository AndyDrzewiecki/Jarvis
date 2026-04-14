# Financial Engine Guidelines v1

## Data Sources
- FRED API: GDP, UNRATE, CPIAUCSL, FEDFUNDS (requires JARVIS_FRED_API_KEY)
- Yahoo Finance: SPY, QQQ, BTC-USD by default (configure via JARVIS_TRACKED_SYMBOLS)
- SEC EDGAR: watched company filings (configure watched companies in preferences)

## Quality Standards
- Economic data: fresh if < 24 hours old for daily series, < 7 days for monthly
- Market data: always fetch latest close price, flag moves > 3% as high urgency
- SEC filings: filter for 10-K, 10-Q, 8-K form types only

## Alert Thresholds
- Single-day price move > 3%: post blackboard alert (high urgency)
- Fed funds rate change: post blackboard alert (urgent)
- CPI above 4%: post budget-sensitive signal to household state
