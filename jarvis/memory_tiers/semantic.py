from __future__ import annotations
import os, sqlite3, uuid
from datetime import datetime, timezone

SEMANTIC_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "semantic.db")
CHROMADB_PATH = os.getenv("JARVIS_CHROMADB_PATH", "data/chromadb")

_DDL = """
CREATE TABLE IF NOT EXISTS kb_index (
    id TEXT PRIMARY KEY, domain TEXT NOT NULL, fact_type TEXT NOT NULL,
    summary TEXT NOT NULL, source_agent TEXT NOT NULL, confidence REAL DEFAULT 0.8,
    storage TEXT NOT NULL, storage_ref TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    expires_at TEXT, superseded_by TEXT, tags TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS knowledge_links (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    relationship TEXT NOT NULL, strength REAL DEFAULT 0.5, created_at TEXT NOT NULL, evidence TEXT
);
CREATE TABLE IF NOT EXISTS provenance (
    id TEXT PRIMARY KEY, fact_id TEXT NOT NULL, event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL, source_type TEXT NOT NULL, source_detail TEXT,
    model_used TEXT, prompt_hash TEXT, input_summary TEXT, confidence_at_event REAL, agent TEXT
);
CREATE TABLE IF NOT EXISTS prices (
    id TEXT PRIMARY KEY, item_name TEXT NOT NULL, store TEXT,
    price REAL NOT NULL, unit TEXT DEFAULT 'each', observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, who TEXT, start_time TEXT NOT NULL,
    end_time TEXT, recurrence TEXT, location TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY, category TEXT NOT NULL, period TEXT NOT NULL,
    budgeted REAL NOT NULL, spent REAL DEFAULT 0, notes TEXT
);
CREATE TABLE IF NOT EXISTS inventory (
    id TEXT PRIMARY KEY, item_name TEXT NOT NULL, category TEXT,
    quantity REAL DEFAULT 1, unit TEXT DEFAULT 'each', expires_at TEXT, location TEXT
);
CREATE TABLE IF NOT EXISTS maintenance (
    id TEXT PRIMARY KEY, item TEXT NOT NULL, last_done TEXT, next_due TEXT,
    interval_days INTEGER, notes TEXT, cost_estimate REAL
);
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, relation TEXT, phone TEXT, email TEXT, notes TEXT
);
"""

_inited: set[str] = set()

def _open(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.commit()
    _inited.add(db_path)
    return conn

class SemanticStore:
    def __init__(self, data_dir: str | None = None, chromadb_path: str = CHROMADB_PATH):
        if data_dir:
            self._db_path = os.path.join(data_dir, "semantic.db")
            self._chromadb_path = os.path.join(data_dir, "chromadb")
        else:
            self._db_path = SEMANTIC_DB_PATH
            self._chromadb_path = chromadb_path
        self._chroma_client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            import chromadb  # lazy
            if self._chromadb_path == ":memory:":
                self._chroma_client = chromadb.Client()
            else:
                self._chroma_client = chromadb.PersistentClient(path=self._chromadb_path)
            self._collection = self._chroma_client.get_or_create_collection("jarvis_knowledge")
        return self._collection

    def add_fact(self, domain: str, fact_type: str, summary: str,
                 source_agent: str, confidence: float = 0.8,
                 tags: str = "", expires_at: str | None = None) -> str:
        fact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn = _open(self._db_path)
            conn.execute(
                "INSERT INTO kb_index (id,domain,fact_type,summary,source_agent,confidence,storage,created_at,updated_at,expires_at,tags) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (fact_id, domain, fact_type, summary, source_agent, confidence, "chromadb", now, now, expires_at, tags))
            conn.commit(); conn.close()
        except Exception: pass
        try:
            col = self._get_collection()
            col.add(ids=[fact_id], documents=[summary],
                    metadatas=[{"domain": domain, "fact_type": fact_type,
                                "source_agent": source_agent, "confidence": confidence,
                                "tags": tags, "created_at": now}])
        except Exception: pass
        self._add_provenance(fact_id, "created", source_agent, confidence)
        return fact_id

    def _add_provenance(self, fact_id: str, event_type: str, agent: str, confidence: float) -> None:
        try:
            conn = _open(self._db_path)
            conn.execute(
                "INSERT INTO provenance (id,fact_id,event_type,timestamp,source_type,agent,confidence_at_event) VALUES (?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), fact_id, event_type, datetime.now(timezone.utc).isoformat(), "agent", agent, confidence))
            conn.commit(); conn.close()
        except Exception: pass

    def search(self, query: str, n: int = 10, domain: str | None = None,
               min_confidence: float = 0.0) -> list[dict]:
        try:
            col = self._get_collection()
            kwargs: dict = {"query_texts": [query], "n_results": n}
            if domain:
                kwargs["where"] = {"domain": domain}
            results = col.query(**kwargs)
            items = []
            ids = results.get("ids", [[]])[0]
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            for item_id, doc, meta in zip(ids, docs, metas):
                if meta.get("confidence", 0) >= min_confidence:
                    items.append({"id": item_id, "content": doc, **meta})
            return items
        except Exception: return []

    def query_facts(self, domain: str | None = None, fact_type: str | None = None,
                    min_confidence: float = 0.0, limit: int = 20) -> list[dict]:
        try:
            conn = _open(self._db_path)
            sql = "SELECT * FROM kb_index WHERE confidence >= ? AND superseded_by IS NULL"
            params: list = [min_confidence]
            if domain:
                sql += " AND domain = ?"; params.append(domain)
            if fact_type:
                sql += " AND fact_type = ?"; params.append(fact_type)
            sql += " ORDER BY updated_at DESC LIMIT ?"; params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []

    def get_provenance(self, fact_id: str) -> list[dict]:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("SELECT * FROM provenance WHERE fact_id=? ORDER BY timestamp", (fact_id,)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []

    def add_link(self, source_id: str, target_id: str, relationship: str,
                 strength: float = 0.5, evidence: str = "") -> str:
        lid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute(
                "INSERT INTO knowledge_links (id,source_id,target_id,relationship,strength,created_at,evidence) VALUES (?,?,?,?,?,?,?)",
                (lid, source_id, target_id, relationship, strength, datetime.now(timezone.utc).isoformat(), evidence))
            conn.commit(); conn.close()
        except Exception: pass
        return lid

    def get_links(self, fact_id: str) -> list[dict]:
        try:
            conn = _open(self._db_path)
            rows = conn.execute("SELECT * FROM knowledge_links WHERE source_id=? OR target_id=?", (fact_id, fact_id)).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception: return []

    def store_price(self, item_name: str, store: str, price: float, unit: str = "each", observed_at: str | None = None) -> str:
        pid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO prices (id,item_name,store,price,unit,observed_at) VALUES (?,?,?,?,?,?)",
                         (pid, item_name, store, price, unit, observed_at or datetime.now(timezone.utc).isoformat()))
            conn.commit(); conn.close()
        except Exception: pass
        return pid

    def store_schedule(self, title: str, who: str | None, start_time: str,
                       end_time: str | None = None, recurrence: str | None = None,
                       location: str | None = None, source: str | None = None) -> str:
        sid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO schedules (id,title,who,start_time,end_time,recurrence,location,source) VALUES (?,?,?,?,?,?,?,?)",
                         (sid, title, who, start_time, end_time, recurrence, location, source))
            conn.commit(); conn.close()
        except Exception: pass
        return sid

    def store_budget(self, category: str, period: str, budgeted: float, spent: float = 0, notes: str = "") -> str:
        bid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO budgets (id,category,period,budgeted,spent,notes) VALUES (?,?,?,?,?,?)",
                         (bid, category, period, budgeted, spent, notes))
            conn.commit(); conn.close()
        except Exception: pass
        return bid

    def store_inventory(self, item_name: str, category: str | None = None, quantity: float = 1,
                        unit: str = "each", expires_at: str | None = None, location: str | None = None) -> str:
        iid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO inventory (id,item_name,category,quantity,unit,expires_at,location) VALUES (?,?,?,?,?,?,?)",
                         (iid, item_name, category, quantity, unit, expires_at, location))
            conn.commit(); conn.close()
        except Exception: pass
        return iid

    def store_maintenance(self, item: str, last_done: str | None = None, next_due: str | None = None,
                           interval_days: int | None = None, notes: str = "", cost_estimate: float | None = None) -> str:
        mid = str(uuid.uuid4())
        try:
            conn = _open(self._db_path)
            conn.execute("INSERT INTO maintenance (id,item,last_done,next_due,interval_days,notes,cost_estimate) VALUES (?,?,?,?,?,?,?)",
                         (mid, item, last_done, next_due, interval_days, notes, cost_estimate))
            conn.commit(); conn.close()
        except Exception: pass
        return mid

    def recent_by_domain(self, limit_per_domain: int = 3) -> dict[str, list]:
        try:
            conn = _open(self._db_path)
            domains = [r[0] for r in conn.execute("SELECT DISTINCT domain FROM kb_index WHERE superseded_by IS NULL").fetchall()]
            result = {}
            for domain in domains:
                rows = conn.execute("SELECT * FROM kb_index WHERE domain=? AND superseded_by IS NULL ORDER BY updated_at DESC LIMIT ?",
                                    (domain, limit_per_domain)).fetchall()
                result[domain] = [dict(r) for r in rows]
            conn.close()
            return result
        except Exception: return {}
