from __future__ import annotations
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

_FINANCIAL_DDL = """
CREATE TABLE IF NOT EXISTS economic_indicators (
    id TEXT PRIMARY KEY, series_id TEXT NOT NULL, value REAL NOT NULL,
    period TEXT NOT NULL, frequency TEXT NOT NULL, source TEXT NOT NULL,
    retrieved_at TEXT NOT NULL, revised INTEGER DEFAULT 0, prior_value REAL
);
CREATE TABLE IF NOT EXISTS market_data (
    id TEXT PRIMARY KEY, symbol TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume INTEGER,
    adjusted_close REAL, source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sec_filings (
    id TEXT PRIMARY KEY, cik TEXT NOT NULL, company_name TEXT NOT NULL,
    form_type TEXT NOT NULL, filed_date TEXT NOT NULL, accepted_date TEXT NOT NULL,
    document_url TEXT NOT NULL, summary TEXT, key_metrics TEXT,
    sentiment REAL, relevance REAL
);
CREATE TABLE IF NOT EXISTS tax_changes (
    id TEXT PRIMARY KEY, jurisdiction TEXT NOT NULL, category TEXT NOT NULL,
    effective_date TEXT NOT NULL, description TEXT NOT NULL,
    impact_summary TEXT, source_url TEXT, confidence REAL DEFAULT 0.8
);
"""

_RESEARCH_DDL = """
CREATE TABLE IF NOT EXISTS research_papers (
    id TEXT PRIMARY KEY, arxiv_id TEXT, semantic_scholar_id TEXT,
    title TEXT NOT NULL, authors TEXT NOT NULL, abstract TEXT NOT NULL,
    published_date TEXT NOT NULL, categories TEXT NOT NULL,
    summary TEXT, technique_type TEXT, applicability TEXT,
    quality_score REAL, code_url TEXT,
    reviewed INTEGER DEFAULT 0, actionable INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tracked_repos (
    id TEXT PRIMARY KEY, github_url TEXT NOT NULL, name TEXT NOT NULL,
    description TEXT, stars INTEGER, language TEXT, license TEXT,
    last_commit TEXT, topics TEXT, relevance TEXT, summary TEXT,
    first_seen TEXT NOT NULL, last_checked TEXT NOT NULL,
    status TEXT DEFAULT 'tracking'
);
CREATE TABLE IF NOT EXISTS model_registry (
    id TEXT PRIMARY KEY, hf_model_id TEXT, name TEXT NOT NULL,
    parameter_count TEXT, architecture TEXT, quantizations TEXT,
    benchmarks TEXT, vram_required TEXT, runs_on_our_hw INTEGER DEFAULT 0,
    use_case TEXT, first_seen TEXT NOT NULL, notes TEXT
);
CREATE TABLE IF NOT EXISTS improvement_proposals (
    id TEXT PRIMARY KEY, source_paper_id TEXT, source_repo_id TEXT,
    target_component TEXT NOT NULL, proposal TEXT NOT NULL,
    estimated_impact TEXT, estimated_effort TEXT,
    status TEXT DEFAULT 'proposed', created_at TEXT NOT NULL,
    reviewed_at TEXT, review_notes TEXT
);
"""

# ═══ ENGINE 2: Geopolitical & World Events ═══
_GEOPOLITICAL_DDL = """
CREATE TABLE IF NOT EXISTS geopolitical_events (
    id TEXT PRIMARY KEY, event_type TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL, regions TEXT NOT NULL, started_at TEXT NOT NULL,
    ended_at TEXT, severity REAL, market_impact TEXT,
    source TEXT NOT NULL, source_url TEXT, related_events TEXT
);
CREATE TABLE IF NOT EXISTS policy_tracker (
    id TEXT PRIMARY KEY, jurisdiction TEXT NOT NULL, policy_type TEXT NOT NULL,
    title TEXT NOT NULL, status TEXT NOT NULL, introduced_date TEXT NOT NULL,
    last_action TEXT, impact_domains TEXT, summary TEXT,
    household_impact TEXT, source_url TEXT
);
"""

# ═══ ENGINE 4: Legal & Regulatory ═══
_LEGAL_DDL = """
CREATE TABLE IF NOT EXISTS regulatory_changes (
    id TEXT PRIMARY KEY, jurisdiction TEXT NOT NULL, domain TEXT NOT NULL,
    title TEXT NOT NULL, effective_date TEXT, description TEXT NOT NULL,
    household_impact TEXT, action_required TEXT, source TEXT NOT NULL,
    source_url TEXT, confidence REAL DEFAULT 0.8
);
"""

# ═══ ENGINE 5: Health & Wellness ═══
_HEALTH_DDL = """
CREATE TABLE IF NOT EXISTS health_knowledge (
    id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
    content TEXT NOT NULL, source TEXT NOT NULL, source_url TEXT,
    evidence_level TEXT, relevance REAL, last_verified TEXT,
    seasonal INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS environmental_data (
    id TEXT PRIMARY KEY, metric TEXT NOT NULL, value REAL NOT NULL,
    location TEXT NOT NULL, measured_at TEXT NOT NULL, source TEXT NOT NULL,
    forecast TEXT
);
"""

# ═══ ENGINE 6: Local Intelligence ═══
_LOCAL_DDL = """
CREATE TABLE IF NOT EXISTS local_data (
    id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
    content TEXT NOT NULL, location TEXT, data_date TEXT NOT NULL,
    source TEXT NOT NULL, source_url TEXT, trend TEXT
);
"""

# ═══ ENGINE 7: Family & Life Quality ═══
_FAMILY_DDL = """
CREATE TABLE IF NOT EXISTS family_activities (
    id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL,
    description TEXT NOT NULL, location TEXT, distance_miles REAL,
    cost_estimate TEXT, age_appropriate TEXT, duration TEXT,
    season TEXT, weather_req TEXT, source TEXT NOT NULL, source_url TEXT,
    rating REAL, household_rating REAL, last_done TEXT,
    times_done INTEGER DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS vacation_research (
    id TEXT PRIMARY KEY, destination TEXT NOT NULL, trip_type TEXT NOT NULL,
    estimated_cost REAL, duration_days INTEGER, best_season TEXT,
    kid_friendly INTEGER DEFAULT 1, highlights TEXT, logistics TEXT,
    source TEXT NOT NULL, source_url TEXT,
    household_interest REAL DEFAULT 0.5, saved_at TEXT NOT NULL, planned_for TEXT
);
CREATE TABLE IF NOT EXISTS parenting_knowledge (
    id TEXT PRIMARY KEY, category TEXT NOT NULL, age_range TEXT,
    title TEXT NOT NULL, content TEXT NOT NULL, source TEXT NOT NULL,
    evidence_level TEXT, actionable INTEGER DEFAULT 0, seasonal INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS local_events (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT,
    venue TEXT, address TEXT, event_date TEXT NOT NULL, event_time TEXT,
    end_date TEXT, cost TEXT, category TEXT, family_friendly INTEGER DEFAULT 1,
    source TEXT NOT NULL, source_url TEXT, distance_miles REAL, relevance REAL
);
"""

_ENGINE_DDL = {
    "financial": _FINANCIAL_DDL,
    "research": _RESEARCH_DDL,
    "geopolitical": _GEOPOLITICAL_DDL,
    "legal": _LEGAL_DDL,
    "health": _HEALTH_DDL,
    "local": _LOCAL_DDL,
    "family": _FAMILY_DDL,
}

_TABLE_ENGINE = {
    "economic_indicators": "financial",
    "market_data": "financial",
    "sec_filings": "financial",
    "tax_changes": "financial",
    "research_papers": "research",
    "tracked_repos": "research",
    "model_registry": "research",
    "improvement_proposals": "research",
    "geopolitical_events": "geopolitical",
    "policy_tracker": "geopolitical",
    "regulatory_changes": "legal",
    "health_knowledge": "health",
    "environmental_data": "health",
    "local_data": "local",
    "family_activities": "family",
    "vacation_research": "family",
    "parenting_knowledge": "family",
    "local_events": "family",
}

class EngineStore:
    """Manages domain-specific SQLite databases for knowledge engines.

    Each engine gets its own DB file: {engines_dir}/{engine}.db
    """

    def __init__(self, engines_dir: str | None = None):
        from jarvis import config
        self._dir = engines_dir or os.path.join(config.DATA_DIR, "engines")
        self._connections: dict[str, sqlite3.Connection] = {}

    def _open(self, engine: str) -> sqlite3.Connection:
        if engine in self._connections:
            return self._connections[engine]
        os.makedirs(self._dir, exist_ok=True)
        db_path = os.path.join(self._dir, f"{engine}.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        ddl = _ENGINE_DDL.get(engine)
        if ddl:
            conn.executescript(ddl)
            conn.commit()
        self._connections[engine] = conn
        return conn

    def store(self, engine: str, table: str, data: dict) -> str:
        """Store a row in a domain-specific table. Returns row ID."""
        resolved_engine = _TABLE_ENGINE.get(table, engine)
        conn = self._open(resolved_engine)
        row_id = data.get("id") or str(uuid.uuid4())
        data = dict(data)
        data["id"] = row_id
        columns = list(data.keys())
        placeholders = ",".join("?" * len(columns))
        col_names = ",".join(columns)
        try:
            conn.execute(
                f"INSERT OR REPLACE INTO {table} ({col_names}) VALUES ({placeholders})",
                [data[c] for c in columns],
            )
            conn.commit()
        except Exception as exc:
            logger.warning("EngineStore.store failed for %s.%s: %s", resolved_engine, table, exc)
            raise
        return row_id

    def query(self, engine: str, table: str, where: str | None = None,
              params: list | None = None, limit: int = 100) -> list[dict]:
        """Query rows from a domain-specific table."""
        resolved_engine = _TABLE_ENGINE.get(table, engine)
        try:
            conn = self._open(resolved_engine)
            sql = f"SELECT * FROM {table}"
            if where:
                sql += f" WHERE {where}"
            sql += f" LIMIT {limit}"
            rows = conn.execute(sql, params or []).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("EngineStore.query failed for %s.%s: %s", resolved_engine, table, exc)
            return []

    def count(self, engine: str, table: str) -> int:
        """Count rows in a table."""
        resolved_engine = _TABLE_ENGINE.get(table, engine)
        try:
            conn = self._open(resolved_engine)
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            return row["cnt"] if row else 0
        except Exception:
            return 0

    def close_all(self) -> None:
        """Close all open connections."""
        for conn in self._connections.values():
            try:
                conn.close()
            except Exception:
                pass
        self._connections.clear()
