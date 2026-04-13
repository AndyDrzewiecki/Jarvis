from jarvis.adapters.grocery import GroceryAdapter
from jarvis.adapters.investor import InvestorAdapter
from jarvis.adapters.homeops_grocery import HomeopsGroceryAdapter
from jarvis.adapters.summerpuppy import SummerPuppyAdapter
from jarvis.adapters.devteam import DevTeamAdapter
from jarvis.adapters.receipt_ingest import ReceiptIngestAdapter
from jarvis.adapters.weather import WeatherAdapter
from jarvis.adapters.stubs import (
    CalendarAdapter, EmailAdapter,
    FinanceAdapter, HomeAdapter, MusicAdapter, NewsAdapter,
    SalesAgentAdapter,
)

ALL_ADAPTERS = [
    GroceryAdapter(),
    InvestorAdapter(),
    HomeopsGroceryAdapter(),
    SummerPuppyAdapter(),
    DevTeamAdapter(),
    ReceiptIngestAdapter(),
    WeatherAdapter(),
    CalendarAdapter(),
    EmailAdapter(),
    FinanceAdapter(),
    HomeAdapter(),
    MusicAdapter(),
    NewsAdapter(),
    SalesAgentAdapter(),
]
