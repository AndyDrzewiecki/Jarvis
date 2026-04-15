"""
TUTORIAL: server.py is the FastAPI HTTP interface for Jarvis.
Endpoints:
  GET  /                        → Web dashboard (static/index.html)
  GET  /api/status              → LLM reachability + adapter count
  GET  /api/adapters            → list all adapters + capabilities
  POST /api/chat                → send a message, get a response
  GET  /api/chat/stream         → SSE streaming chat (query param: message)
  GET  /api/brief               → generate on-demand morning brief
  POST /api/webhook/summerpuppy → receive SummerPuppy events + push alerts
  GET  /api/history             → last 10 memory messages
  GET  /api/decisions           → query agent decision log
  GET  /api/decisions/recent    → last N decisions
  GET  /api/preferences         → get all user preferences
  POST /api/preferences         → merge-update preferences
  GET  /api/workflows           → list all workflows + status
  POST /api/workflows/{name}/run     → manually trigger a workflow
  POST /api/workflows/{name}/approve → approve a pending workflow action
  POST /api/devteam/promote     → promote DevTeam artifact to target dir

CORS is enabled for all origins so the web dashboard can connect.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
from contextlib import asynccontextmanager
from typing import Optional

import requests as _requests
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import jarvis.memory as memory
import jarvis.agent_memory as agent_memory
import jarvis.preferences as preferences
from jarvis.core import chat, get_adapter_list
from jarvis.notifier import notify
from jarvis.brief import BriefEngine

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
_STATIC_DIR = pathlib.Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start/stop background scheduler around the server lifecycle."""
    from jarvis.scheduler import start as _start, stop as _stop
    _start()
    yield
    _stop()


app = FastAPI(title="Jarvis API", version="0.3.0", lifespan=lifespan)

_dev_mode = os.getenv("JARVIS_DEV_MODE", "false").lower() in ("true", "1", "yes")
_CORS_ORIGINS = ["*"] if _dev_mode else os.getenv("JARVIS_CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Jarvis-Device-Profile", "X-Jarvis-Device-Id"],
)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=0, max_length=4000)


# ── dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def dashboard():
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return index.read_text(encoding="utf-8")
    return "<h1>Jarvis</h1><p>Place <code>static/index.html</code> to enable the dashboard.</p>"


# Mount /static for CSS/JS assets (must come after explicit routes).
if _STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── core API ───────────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    llm_ok = False
    try:
        r = _requests.get(f"{OLLAMA_HOST}/api/tags", timeout=3)
        llm_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok",
        "llm_available": llm_ok,
        "adapter_count": len(get_adapter_list()),
    }


@app.get("/api/adapters")
def adapters():
    return {"adapters": get_adapter_list()}


@app.post("/api/chat")
def chat_endpoint(req: ChatRequest):
    from jarvis.personality import PersonalityLayer
    result = PersonalityLayer().process(req.message)
    return result.to_dict()


# ── SSE streaming chat ─────────────────────────────────────────────────────────

@app.get("/api/chat/stream")
async def chat_stream(message: str = Query(..., min_length=1, max_length=4000)):
    """
    Server-Sent Events endpoint. Emits progress status tokens while adapters
    work, then sends the final result and a 'done' event.

    Event schema:
      {"type": "status",  "text": "..."}
      {"type": "result",  "success": bool, "text": "...", "adapter": "..."}
      {"type": "done"}
    """
    import asyncio

    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data)}\n\n"

    async def event_generator():
        yield _sse({"type": "status", "text": "Routing your request..."})
        loop = asyncio.get_event_loop()
        try:
            yield _sse({"type": "status", "text": "Processing..."})
            from jarvis.personality import PersonalityLayer
            result = await loop.run_in_executor(None, PersonalityLayer().process, message)
            yield _sse({
                "type": "result",
                "success": result.success,
                "text": result.text,
                "adapter": result.adapter,
            })
        except Exception as e:
            yield _sse({"type": "error", "text": str(e)})
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── morning brief ──────────────────────────────────────────────────────────────

@app.get("/api/brief")
async def brief_endpoint():
    """Generate an on-demand morning brief from all live adapters."""
    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, BriefEngine().generate)
    return result


# ── SummerPuppy webhook ────────────────────────────────────────────────────────

@app.post("/api/webhook/summerpuppy")
async def summerpuppy_webhook(payload: dict):
    """
    Receive events from SummerPuppy and push critical alerts via notifier.
    SummerPuppy can be configured to POST events here, making Jarvis the
    unified notification hub.
    """
    severity = str(payload.get("severity", "")).upper()
    if severity == "CRITICAL":
        desc = payload.get("description") or payload.get("event_type", "Unknown event")
        notify(f"\U0001f6a8 CRITICAL: {desc}", title="SummerPuppy Alert")

    pending = payload.get("pending_approvals", 0)
    try:
        if int(pending) > 0:
            notify(
                f"\u26a0\ufe0f {pending} event(s) pending your approval",
                title="SummerPuppy",
            )
    except (TypeError, ValueError):
        pass

    agent_memory.log_decision(
        agent="webhook",
        capability="summerpuppy_event",
        decision=f"Received {severity or 'unknown'} event",
        reasoning=str(payload)[:500],
        outcome="success",
    )
    return {"received": True, "severity": severity}


# ── memory introspection ───────────────────────────────────────────────────────

@app.get("/api/memory/audit")
async def memory_audit(domain: Optional[str] = None):
    """Audit knowledge quality for a domain (or all domains)."""
    from jarvis.introspection import MemoryIntrospector
    inspector = MemoryIntrospector()
    return inspector.knowledge_audit(domain)


@app.get("/api/memory/diff")
async def memory_diff(since: str):
    """Return knowledge changes since a given ISO timestamp."""
    from jarvis.introspection import MemoryIntrospector
    inspector = MemoryIntrospector()
    return inspector.memory_diff(since)


@app.get("/api/memory/explain/{decision_id}")
async def memory_explain(decision_id: str):
    """Trace a decision through its provenance chain."""
    from jarvis.introspection import MemoryIntrospector
    inspector = MemoryIntrospector()
    return inspector.explain_recommendation(decision_id)


# ── history & decisions ────────────────────────────────────────────────────────

@app.get("/api/history")
def history():
    return {"messages": memory.recent(10)}


@app.get("/api/decisions")
def decisions(
    agent: Optional[str] = Query(None),
    capability: Optional[str] = Query(None),
    since: Optional[str] = Query(None, description="ISO-8601 timestamp filter"),
    limit: int = Query(50, ge=1, le=500),
):
    """Query the agent decision log with optional filters."""
    entries = agent_memory.query(
        agent=agent,
        capability=capability,
        since_iso=since,
        limit=limit,
    )
    return {"decisions": entries, "count": len(entries)}


@app.get("/api/decisions/recent")
def recent_decisions(n: int = Query(20, ge=1, le=500)):
    """Return the last N decisions across all agents."""
    entries = agent_memory.recent_decisions(n=n)
    return {"decisions": entries, "count": len(entries)}


# ── preferences ────────────────────────────────────────────────────────────────

@app.get("/api/preferences")
def get_preferences():
    """Return all user preferences."""
    return preferences.load()


@app.post("/api/preferences")
def update_preferences(updates: dict):
    """Merge-update preferences. Body: {key: value, ...}"""
    updated = preferences.update(updates)
    return updated


# ── workflows ───────────────────────────────────────────────────────────────────

@app.get("/api/workflows")
def list_workflows():
    """List all workflows with their current status."""
    from jarvis.workflows import WorkflowEngine
    engine = WorkflowEngine()
    return {"workflows": engine.status()}


@app.post("/api/workflows/{name}/run")
async def run_workflow(name: str):
    """Manually trigger a workflow (bypasses cooldown + trigger check)."""
    import asyncio
    from jarvis.workflows import WorkflowEngine
    loop = asyncio.get_event_loop()
    engine = WorkflowEngine()
    result = await loop.run_in_executor(None, engine.run_now, name)
    return {"workflow": name, "result": result}


@app.post("/api/workflows/{name}/approve")
async def approve_workflow(name: str):
    """Approve and execute a pending workflow action."""
    import asyncio
    from jarvis.workflows import WorkflowEngine
    loop = asyncio.get_event_loop()
    engine = WorkflowEngine()
    result = await loop.run_in_executor(None, engine.approve, name)
    return {"workflow": name, "result": result}


# ── DevTeam promote ─────────────────────────────────────────────────────────────

# Target dirs that may receive promoted artifacts (security whitelist)
_PROMOTE_WHITELIST = [
    "C:/AI-Lab/agents",
    "C:\\AI-Lab\\agents",
]


class PromoteRequest(BaseModel):
    artifact_slug: str
    target_dir: str


@app.post("/api/devteam/promote")
def promote_artifact(req: PromoteRequest):
    """
    Copy a DevTeam artifact directory to a whitelisted target directory.
    Body: {"artifact_slug": "sales_scrapers", "target_dir": "C:/AI-Lab/agents/"}
    """
    import shutil

    from jarvis.adapters.devteam.config import ARTIFACTS_DIR

    # Validate slug (alphanumeric + underscores only)
    import re
    if not re.fullmatch(r"[\w\-]+", req.artifact_slug):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Invalid artifact_slug")

    artifact_path = pathlib.Path(ARTIFACTS_DIR) / req.artifact_slug
    if not artifact_path.exists():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Artifact '{req.artifact_slug}' not found in artifacts dir",
        )

    # Validate target dir against whitelist
    target = pathlib.Path(req.target_dir).resolve()
    allowed = any(
        str(target) == str(pathlib.Path(w).resolve()) or
        str(target).startswith(str(pathlib.Path(w).resolve()))
        for w in _PROMOTE_WHITELIST
    )
    if not allowed:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail=f"Target dir not in whitelist: {req.target_dir}",
        )

    promoted = []
    for src_file in artifact_path.iterdir():
        if src_file.is_file():
            dest = target / src_file.name
            shutil.copy2(src_file, dest)
            promoted.append(str(dest))

    agent_memory.log_decision(
        agent="server",
        capability="promote_artifact",
        decision=f"Promoted '{req.artifact_slug}' → {req.target_dir}",
        reasoning=f"Files: {promoted}",
        outcome="success",
    )
    return {"promoted": promoted, "artifact_slug": req.artifact_slug, "target_dir": str(target)}


# ── TTS endpoint ──────────────────────────────────────────────────────────────

@app.get("/api/tts")
async def tts_endpoint(text: str = Query(..., min_length=1, max_length=1000)):
    """Synthesize text to speech. Returns audio/mpeg stream."""
    from jarvis.tts import synthesize
    audio_bytes = await synthesize(text)
    if not audio_bytes:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="TTS synthesis failed")
    import io
    return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")


# ── Device registry ───────────────────────────────────────────────────────────

class DeviceRegisterRequest(BaseModel):
    device_id: str
    profile: str = "default"
    display_name: str = ""


@app.get("/api/devices")
def get_devices():
    """List all registered JarvisOS nodes."""
    from jarvis.devices import list_devices
    return {"devices": list_devices()}


@app.post("/api/devices/register")
def register_device(req: DeviceRegisterRequest):
    """Register a JarvisOS device node."""
    from jarvis.devices import register
    record = register(req.device_id, req.profile, req.display_name)
    return record


# ── OTA endpoints ─────────────────────────────────────────────────────────────

_OS_VERSION_FILE = pathlib.Path(__file__).parent / "data" / "os_version.json"
_APK_PATH = pathlib.Path(__file__).parent / "dist" / "jarvis-os-latest.apk"


@app.get("/api/os/version")
def os_version():
    """Return current JarvisOS APK version info."""
    if _OS_VERSION_FILE.exists():
        import json as _json
        data = _json.loads(_OS_VERSION_FILE.read_text(encoding="utf-8"))
        return data
    return {"version_code": 1, "version_name": "1.0.0", "release_notes": "Initial release"}


@app.get("/api/os/apk")
def os_apk():
    """Stream the latest JarvisOS APK for OTA updates."""
    if not _APK_PATH.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="APK not available")
    return StreamingResponse(
        open(_APK_PATH, "rb"),
        media_type="application/vnd.android.package-archive",
        headers={"Content-Disposition": "attachment; filename=jarvis-os-latest.apk"},
    )


# ── STT endpoint (faster-whisper backend) ─────────────────────────────────────

@app.post("/api/stt")
async def stt_endpoint(audio: Optional["UploadFile"] = None):
    """Transcribe uploaded audio to text using faster-whisper (local, private)."""
    from fastapi import UploadFile
    from jarvis.stt import transcribe
    if audio is None:
        return {"text": "STT not configured", "confidence": 0.0, "language": "en"}
    audio_bytes = await audio.read()
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, transcribe, audio_bytes)
    return result


# ── Notebook (ChromaDB-backed) ─────────────────────────────────────────────────

def _get_kb():
    from jarvis.knowledge_base import KnowledgeBase
    return KnowledgeBase()


class NotebookItem(BaseModel):
    title: str = ""
    content: str
    category: str = "notes"
    tags: list[str] = []
    source_url: str = ""
    device_id: str = ""


@app.get("/api/notebook")
def notebook_list(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    """Browse/search saved notebook items via ChromaDB."""
    kb = _get_kb()
    if q:
        items = kb.search(q, n=50, category=category or None)
    else:
        items = kb.browse(category=category or None, limit=50)
    return {"items": items, "count": len(items)}


@app.post("/api/notebook")
def notebook_save(item: NotebookItem):
    """Save an item to the ChromaDB knowledge base."""
    from datetime import datetime
    kb = _get_kb()
    item_id = kb.add_document(
        content=item.content,
        category=item.category,
        tags=item.tags,
        source_url=item.source_url,
        device_id=item.device_id,
    )
    return {
        "id": item_id,
        "title": item.title,
        "content": item.content,
        "category": item.category,
        "tags": item.tags,
        "source_url": item.source_url,
        "device_id": item.device_id,
        "created_at": datetime.utcnow().isoformat(),
    }


@app.get("/api/notebook/{item_id}")
def notebook_get(item_id: str):
    """Fetch a single notebook item by ID."""
    kb = _get_kb()
    doc = kb.get(item_id)
    if doc is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Item not found")
    return doc


@app.delete("/api/notebook/{item_id}")
def notebook_delete(item_id: str):
    """Delete a notebook item by ID."""
    kb = _get_kb()
    deleted = kb.delete(item_id)
    return {"deleted": deleted}


@app.post("/api/notebook/{item_id}/summarize")
def notebook_summarize(item_id: str):
    """LLM synthesis of the specified item and related knowledge."""
    kb = _get_kb()
    doc = kb.get(item_id)
    if doc is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Item not found")
    summary = kb.summarize(tag_filter=doc.get("tags") or None)
    return {"item_id": item_id, "summary": summary}


# ── Phase 4A: Specialists status ──────────────────────────────────────────────

_SPECIALIST_REGISTRY = [
    {"name": "grocery_specialist",  "domain": "grocery",  "schedule": "0 */4 * * *"},
    {"name": "finance_specialist",  "domain": "finance",  "schedule": "0 */6 * * *"},
    {"name": "calendar_specialist", "domain": "calendar", "schedule": "0 */2 * * *"},
    {"name": "home_specialist",     "domain": "home",     "schedule": "0 8 * * *"},
    {"name": "news_specialist",     "domain": "news",     "schedule": "0 */3 * * *"},
    {"name": "investor_specialist", "domain": "investor", "schedule": "0 9,16 * * 1-5"},
]


@app.get("/api/specialists")
def get_specialists():
    """Return status of all 6 specialists with last-run info from decision log."""
    results = []
    for spec in _SPECIALIST_REGISTRY:
        recent = agent_memory.query(agent=spec["name"], limit=1)
        last = recent[0] if recent else None
        results.append({
            "name": spec["name"],
            "domain": spec["domain"],
            "schedule": spec["schedule"],
            "last_run": last["timestamp"] if last else None,
            "last_outcome": last["outcome"] if last else None,
            "last_decision": last["decision"] if last else None,
        })
    return {"specialists": results, "count": len(results)}


# ── Phase 4A: Knowledge Lake browser ─────────────────────────────────────────

@app.get("/api/knowledge-lake")
def knowledge_lake_browser(
    domain: Optional[str] = Query(None),
    fact_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None),
):
    """Browse Knowledge Lake facts with optional domain/type/search filters."""
    from jarvis.knowledge_lake import KnowledgeLake
    lake = KnowledgeLake()
    if q:
        facts = lake.search(q, n=limit, domain=domain or None)
    elif domain:
        facts = lake.query_facts(domain=domain, fact_type=fact_type or None, limit=limit)
    else:
        grouped = lake.recent_by_domain(limit_per_domain=min(limit // 7 + 1, 20))
        flat: list = []
        for domain_facts in grouped.values():
            flat.extend(domain_facts)
        return {"facts": flat, "count": len(flat)}
    return {"facts": facts, "count": len(facts)}


# ── Phase 4A: Household State controls ───────────────────────────────────────

_VALID_PRIMARIES = [
    "normal", "summer", "winter", "holiday", "budget_tight",
    "guests_coming", "vacation", "sick_day", "spring_cleaning",
]
_VALID_MODIFIERS = [
    "grocery_day", "payday", "date_night", "meal_prep", "leftovers",
    "school_night", "weekend", "long_weekend", "outdoor_dining",
    "guests_arriving_soon", "cooking_ahead", "low_pantry",
]


class HouseholdStateUpdate(BaseModel):
    action: str = Field(..., pattern=r"^(transition|add_modifier|remove_modifier)$")
    value: str = Field(..., min_length=1, max_length=64)
    reason: str = Field("dashboard update", max_length=256)


@app.get("/api/household-state")
def get_household_state():
    """Get current household state and recent transition history."""
    from jarvis.household_state import HouseholdState
    state = HouseholdState()
    return {
        "current": state.current(),
        "history": state.get_history(20),
        "valid_primaries": _VALID_PRIMARIES,
        "valid_modifiers": _VALID_MODIFIERS,
    }


@app.put("/api/household-state")
def update_household_state(update: HouseholdStateUpdate):
    """Update household state (transition primary or add/remove modifier)."""
    from fastapi import HTTPException
    from jarvis.household_state import HouseholdState
    state = HouseholdState()
    if update.action == "transition":
        if update.value not in _VALID_PRIMARIES:
            raise HTTPException(status_code=400, detail=f"Invalid primary: {update.value!r}")
        state.transition(update.value, update.reason)
    elif update.action == "add_modifier":
        if update.value not in _VALID_MODIFIERS:
            raise HTTPException(status_code=400, detail=f"Invalid modifier: {update.value!r}")
        state.add_modifier(update.value, update.reason)
    elif update.action == "remove_modifier":
        state.remove_modifier(update.value, update.reason)
    return {"current": state.current(), "action": update.action, "value": update.value}


# ── Phase 4A: Engine status dashboard ────────────────────────────────────────

_ENGINE_TABLES: dict[str, list[str]] = {
    "financial":   ["economic_indicators", "market_data", "sec_filings", "tax_changes"],
    "research":    ["research_papers", "tracked_repos", "model_registry", "improvement_proposals"],
    "geopolitical": ["geopolitical_events", "policy_tracker"],
    "legal":       ["regulatory_changes"],
    "health":      ["health_knowledge", "environmental_data"],
    "local":       ["local_data"],
    "family":      ["family_activities", "vacation_research", "parenting_knowledge", "local_events"],
}


@app.get("/api/engines/status")
def get_engines_status():
    """Return record counts and last-ingestion info for all 7 knowledge engines."""
    from jarvis.engine_store import EngineStore
    store = EngineStore()
    engines = []
    for engine_name, tables in _ENGINE_TABLES.items():
        table_counts: dict[str, int] = {}
        for table in tables:
            table_counts[table] = store.count(engine_name, table)
        total = sum(table_counts.values())
        recent = agent_memory.query(agent=f"{engine_name}_engine", limit=1)
        last_run = recent[0]["timestamp"] if recent else None
        engines.append({
            "name": engine_name,
            "tables": table_counts,
            "total_records": total,
            "last_run": last_run,
        })
    return {"engines": engines, "total_records": sum(e["total_records"] for e in engines)}


# ── Phase 4A: Blackboard viewer ───────────────────────────────────────────────

@app.get("/api/blackboard")
def get_blackboard(
    topic: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Return recent cross-specialist blackboard posts."""
    from jarvis.blackboard import SharedBlackboard
    bb = SharedBlackboard()
    topics = [topic] if topic else None
    posts = bb.read(topics=topics, limit=limit)
    return {"posts": posts, "count": len(posts)}


# ── Phase 5: Computer Vision endpoints ───────────────────────────────────────

_vision_pipeline: "VisionPipeline | None" = None
_vision_store: "VisionStore | None" = None


def _get_vision_pipeline():
    global _vision_pipeline
    if _vision_pipeline is None:
        from jarvis.vision.pipeline import VisionPipeline
        _vision_pipeline = VisionPipeline()
    return _vision_pipeline


def _get_vision_store():
    global _vision_store
    if _vision_store is None:
        from jarvis.vision.store import VisionStore
        _vision_store = VisionStore()
    return _vision_store


class VisionAnalyzeRequest(BaseModel):
    image_b64: str
    context_hint: str = "unknown"
    device_id: str = "unknown"


class VisionStreamRequest(BaseModel):
    action: str
    session_id: str
    device_id: str = "unknown"
    context: str = "unknown"


@app.post("/api/vision/analyze")
def vision_analyze(req: VisionAnalyzeRequest):
    """Analyze a single image frame and return scene analysis + routing info."""
    from fastapi import HTTPException
    pipeline = _get_vision_pipeline()
    store = _get_vision_store()

    # Use pipeline with a transient (no-session) frame
    # Create a temporary session for this one-shot analysis
    tmp_session = f"oneshot-{req.device_id}"
    pipeline.start_session(tmp_session, req.device_id, context=req.context_hint)
    try:
        event = pipeline.submit_frame(tmp_session, req.image_b64)
    finally:
        pipeline.stop_session(tmp_session)

    # Also persist to standalone store
    store.save_event(event)

    analysis = event.analysis
    return {
        "event_id": event.event_id,
        "scene_description": analysis.scene_description,
        "detected_objects": [obj.to_dict() for obj in analysis.detected_objects],
        "context": analysis.context,
        "confidence": analysis.confidence,
        "model_used": analysis.model_used,
        "routed_to": event.routed_to,
        "knowledge_lake_ids": event.knowledge_lake_ids,
        "device_id": event.device_id,
        "created_at": event.created_at,
    }


@app.post("/api/vision/stream")
def vision_stream(req: VisionStreamRequest):
    """Start or stop a camera streaming session."""
    from fastapi import HTTPException
    pipeline = _get_vision_pipeline()

    if req.action == "start":
        result = pipeline.start_session(req.session_id, req.device_id, context=req.context)
        return {"status": "started", "session_id": req.session_id, "stats": result}
    elif req.action == "stop":
        result = pipeline.stop_session(req.session_id)
        return {"status": "stopped", "session_id": req.session_id, "stats": result.get("stats", {})}
    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {req.action!r}. Must be 'start' or 'stop'.")


@app.get("/api/vision/events")
def vision_events(
    limit: int = Query(20, ge=1, le=200),
    device_id: Optional[str] = Query(None),
    context: Optional[str] = Query(None),
):
    """Return recent vision events with optional filters."""
    store = _get_vision_store()
    events = store.recent_events(limit=limit, device_id=device_id, context=context)
    return {
        "events": [e.to_dict() for e in events],
        "total": len(events),
    }


# ── WebSocket push endpoint ────────────────────────────────────────────────────

_active_connections: dict[str, WebSocket] = {}  # device_id → socket


@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket, device_id: str = "unknown"):
    """
    Persistent WebSocket for push notifications (spoken briefs, alerts).
    Clients send ping text to keep connection alive.
    Push message format: {"type": "speak", "text": "..."}
    """
    await ws.accept()
    _active_connections[device_id] = ws
    try:
        while True:
            await ws.receive_text()  # client pings keep-alive
    except WebSocketDisconnect:
        _active_connections.pop(device_id, None)


async def push_to_all(message: dict) -> None:
    """Push a JSON message to all connected WebSocket clients. Cleans up dead sockets."""
    dead = []
    for did, ws in list(_active_connections.items()):
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(did)
    for d in dead:
        _active_connections.pop(d, None)


if __name__ == "__main__":
    import uvicorn
    _host = os.getenv("JARVIS_HOST", "0.0.0.0")
    _port = int(os.getenv("JARVIS_PORT", "8000"))
    uvicorn.run(app, host=_host, port=_port)
