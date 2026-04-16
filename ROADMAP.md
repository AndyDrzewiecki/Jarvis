# Jarvis — Product Roadmap

> **Vision:** Jarvis is a complete household operating system. Custom Android OS on tablets in every room. Voice, vision, touch. Controls lights, appliances, network. Learns continuously. Trains its own models. Replaces Alexa, Google Home, and every other smart home hub — running 100% locally.

---

## Phase 1: Foundation (COMPLETE)
*Commit: v0.1.0 — 2026-04-10*

- LLM routing brain (Ollama + gemma3:27b)
- Adapter framework (grocery, investor, weather, devteam)
- FastAPI server + Rich CLI
- Decision audit logging
- Security hardening (prompt injection, input validation)

---

## Phase 2: Intelligence Layer (COMPLETE)
*Commits: 63a9a72 → 3a8f227 — 554 tests*

### Wave 1: Memory Architecture
- 4-tier memory: working → episodic → semantic → procedural
- MemoryBus (unified I/O), Knowledge Lake, AttentionGate

### Wave 2-3: Specialist Framework + Feedback Loops
- BaseSpecialist (gather/analyze/improve cycle)
- GrocerySpec (first proof-of-concept)
- Decision grading (short-term + long-term)
- Consolidation engine (nightly episodic → semantic)
- Household state machine

### Wave 4: Self-Improvement Infrastructure
- Guideline evolution (monthly LLM-driven rewriting)
- Context engines (weekly domain-specific prompt rebuilds)
- Library catalog + Research Librarian framework

### Wave 5: Specialist Roster
- 6 specialists: grocery, finance, calendar, home, news, investor
- SharedBlackboard (cross-specialist communication)
- Google Calendar/Sheets integration (stub)

### Wave 6: Metacognitive Layer
- Metacognitive supervisor (watches the watchers)
- Active preference learning
- Procedural compilation (fast-paths from repeated patterns)
- Memory introspection API (/api/memory/audit, /api/memory/diff, /api/memory/explain)

---

## Phase 3: Knowledge Accumulation Engines (COMPLETE)
*Target: ~8M+ records/year across all engines*

### Batch 1 (COMPLETE — 600 tests, commit 6aee70c)
- IngestionBuffer (world knowledge pipeline: dedup → score → route)
- EngineStore (per-engine SQLite databases)
- **Engine 1: Financial & Economic** — FRED, Yahoo Finance, SEC EDGAR
- **Engine 3: AI/ML Research Sentinel** — arXiv, GitHub, HuggingFace, improvement proposals

### Batch 2 (COMPLETE — ~630 tests, commit 11f418d)
- **Engine 2: Geopolitical & World Events** — GDELT, Congress.gov, world news RSS
- **Engine 4: Legal & Regulatory** — Federal Register, IRS, MN Legislature

### Batch 3 (COMPLETE — 1626 tests total, 2026-04-14)
- **Engine 5: Health & Wellness** — CDC RSS, OpenFDA drug events, AirNow AQI
- **Engine 6: Local Intelligence** — NWS weather, Eventbrite events, local RSS; cross-wires to Family Engine via blackboard
- **Engine 7: Family & Life Quality** — NPS parks, local event cross-reference, AAP parenting research; proactive activity suggestions
- **Startup Harness** — `start.py`, `.env.example`, health check, Quick Start guide

---

## Phase 4: User Interfaces
*Goal: Make Jarvis accessible from every device in the house*

### 4A: Web Dashboard
- React frontend hitting FastAPI server
- Real-time specialist status, Knowledge Lake browser, decision audit viewer
- Household state controls, preference editor
- Accessible from any device on the home network

### 4B: Android Launcher App
- Kotlin/Jetpack Compose native app
- Voice wake-word detection ("Hey Jarvis")
- Push notifications for blackboard alerts
- Boots as home screen on dedicated tablets

### 4C: Custom Android OS
- Full Android ROM/launcher — tablets boot straight into Jarvis
- Kitchen tablet, garage tablet, office tablet, bedside tablet
- Each tablet = thin client hitting the central FastAPI brain
- Optimized for always-on, low-power operation

---

## Phase 5: Computer Vision (COMPLETE)
*Commit: 2026-04-15 — 1855 tests total*

- `jarvis/vision/` module: `models`, `analyzer`, `store`, `router`, `pipeline`
- **VisionAnalyzer** — calls Ollama llava/bakllava via `/api/generate` with base64 images; parses structured JSON scene descriptions; graceful fallback on parse errors or network failures
- **VisionStore** — SQLite backend (`data/vision_events.db`) storing all vision events with full provenance (device_id, session_id, image_hash, timestamp, detected objects, routed adapters, KL IDs)
- **VisionRouter** — keyword-based context routing:
  - Food objects / kitchen context → `grocery` adapter (KL inventory facts)
  - Car parts (battery, tire, filter, etc.) → `car_maintenance` (KL maintenance facts)
  - Tools / workbench context → `project_tracking`
  - Garage context → both `car_maintenance` + `project_tracking`
  - Always writes a base fact to `knowledge_lake`
- **VisionPipeline** — manages named camera sessions; accepts frames via `submit_frame()`; tracks per-session stats
- **API endpoints:**
  - `POST /api/vision/analyze` — single image analysis
  - `POST /api/vision/stream` — start/stop camera sessions
  - `GET /api/vision/events` — query stored events (filterable by device_id, context, limit)
- 117 new tests across 6 test files; all 1855 tests pass
- Vision model controlled by `JARVIS_VISION_MODEL` env var (default: `llava`)

---

## Phase 6: Smart Home Hub (COMPLETE)
*Commit: 2026-04-15 — 2091 tests total*

### Bluetooth & IoT Integration
- `jarvis/smarthome/` module: `models`, `registry`, `ble_scanner`, `mqtt_client`
- **BLEScanner** — async device discovery via bleak (graceful degradation without it); matcher registry for brand detection; classifies discovered devices by adapter type
- **DeviceRegistry** — SQLite-backed device store; CRUD + state updates + status tracking + scenes; room/type filters; state survives restart
- **MQTTClient** — paho-mqtt wrapper with per-topic callbacks, wildcard support, inject_message for testing; graceful degradation without paho
- **Device-specific adapters** (`jarvis/smarthome/adapters/`):
  - `HubSpaceAdapter` — HubSpace BLE lights (Home Depot brand): power, brightness, color_temp, RGB
  - `ApplianceAdapter` — Instant Pot + Camp Chef: mode validation (pressure_cook, slow_cook, sauté, smoke, etc.)
  - `TVAdapter` — TVs via CEC (cec-client), IR (irsend/LIRC), or BLE; graceful fallback when tools absent
  - `GenericMQTTAdapter` / `GenericHTTPAdapter` — any MQTT or REST device following Jarvis topic/endpoint conventions
  - `MockAdapter` — full in-memory adapter for testing; handles all commands

### Voice Control
- **VoiceHandler** — two-tier NL parser: fast regex → LLM fallback path
  - Intents: turn_on/off, set_brightness, set_color_temp, set_volume, set_temperature, set_mode, get_state
  - Room context from tablet (which room heard the command)
  - Device type extraction from utterance ("lights", "TV", "thermostat", "instant pot")
  - Automation voice-trigger integration ("goodnight" → fires goodnight scene)
- `POST /api/smarthome/voice` endpoint — wires into existing Android wake-word + FastAPI pipeline

### Automation Engine
- **AutomationEngine** — SQLite-backed rule store + execution engine
  - TIME triggers: "HH:MM" shorthand + full 5-field cron expressions (no library required)
  - SENSOR triggers: fire on device state attribute changes
  - VOICE triggers: phrase substring matching
  - MANUAL triggers: API/UI-only rules
- `tick()` method called from scheduler every minute for time-based rules
- `check_sensor_triggers()` called on device state changes
- `trigger_by_voice()` / `trigger_manual()` for instant execution
- Post-execution hooks for blackboard integration
- Full execution log in SQLite (run_count, last_triggered, results_json)
- **API endpoints (18 total):** device CRUD + commands, BLE scan, automation CRUD + trigger + log, voice, scenes
- 236 new tests across 7 test files; all 2091 tests pass

---

## Phase 7: Network Security Agent
*Goal: Jarvis guards the house digitally*

### Network Monitoring
- Firewalla API integration — traffic analysis, threat detection, rule management
- Aruba wireless AP API — client tracking, VLAN management, rogue AP detection
- Real-time dashboard showing all network devices, traffic patterns, alerts

### Active Defense
- Auto-block suspicious IPs/domains
- Isolate compromised IoT devices to quarantine VLAN
- Guest network management (auto-expire, bandwidth limits)
- Alert Andy on anomalies via blackboard + push notification

### Database Protection
- Encrypt Jarvis databases at rest
- Network-level access control for the FastAPI server
- Audit logging of all API access
- Intrusion detection for the Jarvis host machine

---

## Phase 8: Project Forge — Autonomous Software Development (COMPLETE)
*Commit: 2026-04-15 — 2439 tests total*

**Production modules:**
- `jarvis/forge/ollama_gateway.py` — OllamaGateway: per-agent model selection, health checks, fallback chains (FORGE_MODEL_LARGE/MEDIUM/SMALL env vars)
- `jarvis/forge/pattern_analyst.py` — Brain 2: reads interaction history, clusters failures by flag type, stages fix proposals to prompt_versions
- `jarvis/forge/tester.py` — Brain 3: A/B tests staged fixes (FORGE_PROMOTION_THRESHOLD=0.05), promotes or discards
- `jarvis/forge/code_auditor.py` — Brain 4: static security scan (eval/exec/pickle/shell=True) + LLM audit; escalates critical flags
- `jarvis/forge/design_session.py` — DesignSession CLI: brainstorm → ProjectSpec → phased Roadmap → autonomous execute; `python -m jarvis.forge.design_session`
- `jarvis/forge/project_inventory.py` — ProjectInventory: scans D:/AI-Lab + C:/AI-Lab, detects language/framework, counts tests, extracts ROADMAP tasks, generates cross-project insights
- 16 new `/api/forge/*` endpoints: status, memory, skills, critic/evaluate, analyst/analyze, tester/run, auditor/audit, trainer/review+export, projects/list+scan+insights, design/brainstorm, gateway/health

*Goal: Jarvis becomes a self-improving software development platform*

This is the crown jewel — Jarvis doesn't just assist with development, it drives it autonomously using local models on the homelab.

### Dev Agent Group (runs on homelab Ollama)
- **Brain 0: Jarvis user-facing (Gemma 4 27B)** — routes requests, responds to users
- **Brain 1: The Critic (12B)** — continuously monitors output quality, catches hallucinations, writes verdicts
- **Brain 2: The Pattern Analyst (12B)** — reads feedback + Critic's verdicts, identifies trends, proposes fixes to staging table
- **Brain 3: The Tester (27B)** — picks up proposed fixes, runs sandboxed A/B tests, promotes or discards
- **Brain 4: The Code Auditor (12B)** — reviews proposed code/prompt changes for bugs, security, regressions

### 7-Layer Introspection Memory
- **Layer 1:** Raw interaction logs
- **Layer 2:** Decision audit trail (what was routed where, why)
- **Layer 3:** User correction pairs (bad_output → good_output) — these become LoRA training data
- **Layer 4:** Hallucination registry
- **Layer 5:** Routing accuracy tracking
- **Layer 6:** Prompt evolution history (what system prompts changed, when, why, what improved)
- **Layer 7:** Meta-patterns (cross-layer insights, systemic failure modes)

### 3-Tier Self-Modification
- **Tier 1 (auto-apply):** Prompt tweaks, retry logic, adapter description rewording
- **Tier 2 (weekly review):** Code modifications, new capabilities — queued for human approval
- **Tier 3 (manual trigger):** LoRA fine-tuning batches — prepared, waits for green light

### Design-to-Build Pipeline
- Interactive design sessions produce full app roadmaps with phases
- Autonomous build pipeline dispatches work to local Ollama dev agents
- Agents check output, iterate, write tests, run to completion without human intervention
- Can manage multiple projects simultaneously (not just Jarvis — all of Andy's projects)

### Agent Trainer
- Reviews completed work, grades quality
- Writes improved guidelines, prompts, instructions back into shared memory
- Builds agent skills and knowledge bases over time
- Every cycle makes agents better

### Shared Memory (SQLite Knowledge Lake)
- Project inventories, coding patterns, past decisions and outcomes
- Agent skill levels, refined prompt templates
- Every agent reads before acting, writes after completing
- Goal: minimize Claude API token usage, maximize local agent capability

---

## Phase 9: Model Training Pipeline (COMPLETE)
*Commit: 2026-04-15 — 2439 tests total*

**Production modules:**
- `jarvis/forge/training_exporter.py` — TrainingExporter: exports correction pairs + high-quality interactions in ShareGPT / DPO / Alpaca formats; bitemporal metadata (`valid_from`/`known_from`) on every record
- `jarvis/forge/lora_runner.py` — LoraRunner: create/configure/launch/monitor QLoRA jobs; supports axolotl, llama.cpp, unsloth, mlx-lm backends; publishes adapters to Ollama via Modelfile; job state in `data/lora_jobs.db`
- `jarvis/forge/bitemporal_store.py` — BitemporalStore: full two-axis temporal store (`valid_from/valid_to` + `known_from/known_to`); `query_as_of()` enables exact-point backtesting; `supersede()` atomically expires old facts and records new ones
- `jarvis/forge/federation.py` — FederationManager: generates Litestream YAML config, restore script, systemd unit, and env file for all 9 Jarvis SQLite databases across the homelab (EliteBook .28, Mini PC .27, EVO-X2 .20/.21)
- `jarvis/forge/improvement_scheduler.py` — ImprovementScheduler: daily (trainer+analyst+tester), weekly (export+threshold check), monthly (LoRA launch) self-improvement cycles; persists schedule state; `run_due()` called by Jarvis scheduler

*Goal: Jarvis trains its own household-specific models*

- 12-18 months of engine data accumulation
- Training data export: ShareGPT format, DPO pairs from decision grading, knowledge corpus
- LoRA fine-tuning on EVO-X2 cluster (AMD Ryzen AI Max+ 395, 96GB GPU-allocatable)
- Bitemporal knowledge for backtesting (valid_from/valid_to + known_from/known_to)
- Multi-node federation via Litestream SQLite replication
- Continuous improvement: retrain monthly as data grows
- Project Forge development data feeds directly into training — code review grades, successful patterns, agent improvement trajectories

---

## Hardware Plan

| Role | Hardware | Memory | Purpose |
|------|----------|--------|---------|
| Primary brain | Current machine | 64GB RAM, 16-24GB VRAM | FastAPI server, Ollama, all engines |
| Dev agent node | EliteBook (192.168.111.28) | 16GB RAM | Initial Jarvis brain — Project Forge dev agents (code, test, review) |
| Dev agent node | Mini PC (192.168.111.27) | 8GB RAM | Worker node — parallel build agents |
| Compute node 1 | GMKtec EVO-X2 | 128GB unified (96GB GPU) | Model training, heavy inference |
| Compute node 2 | GMKtec EVO-X2 | 128GB unified (96GB GPU) | Redundancy, parallel engines |
| Tablets | Old Android tablets | Varies | Thin clients, cameras, BLE hubs |
| Network | Firewalla + Aruba APs | — | Security + wireless management |

---

## Current Status

```
Phase 1  ████████████████████ COMPLETE
Phase 2  ████████████████████ COMPLETE (554 tests)
Phase 3  ████████████████████ COMPLETE (1626 tests — all 7 engines + startup harness)
Phase 4  ████████████████████ COMPLETE (4A Web Dashboard + 4B Android Launcher)
Phase 5  ████████████████████ COMPLETE (1855 tests — Computer Vision)
Phase 6  ████████████████████ COMPLETE (2091 tests — Smart Home Hub)
Phase 7  ████████████████████ COMPLETE (2312 tests — Network Security Agent)
Phase 8  ████████████████████ COMPLETE (2439 tests — Project Forge: 5 brains, design CLI, project inventory)
Phase 9  ████████████████████ COMPLETE (2439 tests — Model Training Pipeline: LoRA runner, bitemporal store, federation, scheduler)
```
