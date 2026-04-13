# Jarvis

Local personal AI assistant. Routes natural language to specialized agents via Ollama.

## Quick Start
```bash
pip install -r requirements.txt
python main.py
```

## Adapters
| Adapter  | Status | Capabilities |
|----------|--------|-------------|
| grocery  | Live | meal_plan, shopping_list, inventory, price_check |
| investor | Live | daily_brief, market_check |
| weather  | Stub | current, forecast, alerts |
| calendar | Stub | today, week, add_event, reminders |
| email    | Stub | unread, summary, send |
| finance  | Stub | budget, spending, accounts |
| home     | Stub | status, set_temp, lights |
| music    | Stub | play, pause, next, queue |
| news     | Stub | headlines, summary, search |

## API
```bash
python server.py
curl http://localhost:8000/api/adapters
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message": "meal plan"}'
```
