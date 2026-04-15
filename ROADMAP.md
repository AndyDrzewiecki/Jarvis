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

## Phase 5: Computer Vision
*Goal: Jarvis can see and understand the physical world*

- Tablet cameras as vision inputs (kitchen, garage, workbench)
- On-device or local model for object recognition
- Use cases:
  - Show a car part → identify, log to maintenance/inventory
  - Show groceries → update inventory, adjust meal plan
  - Watch cooking → track recipes, suggest timing
  - Monitor workbench → auto-log project progress
- Vision data feeds into Knowledge Lake with full provenance

---

## Phase 6: Smart Home Hub
*Goal: Replace Alexa/Google Home entirely*

### Bluetooth & IoT Integration
- BLE device discovery and pairing
- Device-specific adapters:
  - **Lighting:** HubSpace smart lights, any Zigbee/Z-Wave bulbs
  - **Kitchen:** Instant Pot, Camp Chef (BLE cooking monitors)
  - **Entertainment:** TVs (CEC/IR/BLE), speakers, media players
  - **Climate:** thermostats, fans, humidifiers
  - **General IoT:** any device with BLE, MQTT, or Zigbee protocol

### Voice Control
- Always-listening from any tablet
- Natural language → device commands ("turn off the kitchen lights", "set the Instant Pot to slow cook")
- Contextual awareness (knows which room you're in based on which tablet heard you)

### Automation Engine
- Time-based rules ("dim lights at 9 PM")
- Sensor-triggered rules ("turn on garage lights when motion detected")
- Cross-system rules ("when I say goodnight, lock doors + dim lights + set alarm")
- All rules stored in Knowledge Lake, learnable via preference mining

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

## Phase 8: Project Forge — Autonomous Software Development
*Goal: Jarvis becomes a self-improving software development platform*

This is the crown jewel — Jarvis doesn't just assist with development, it drives it autonomously using local models on the homelab.

### Dev Agent Group
- **Lead Agent:** reads the shared knowledge base, understands all projects in D:/AI-Lab and C:/AI-Lab, decides what needs attention — bug fixes, feature work, refactors, dependency updates
- **Specialist Dev Agents:** code writer, test runner, reviewer, docs writer — each dispatched by the lead based on the task
- **Orchestration:** [unicorn-team](https://github.com/aj-geddes/unicorn-team) as the multi-agent orchestration layer
- **Compute:** all agents powered by local Ollama models on the homelab:
  - EliteBook at 192.168.111.28
  - Mini PC at 192.168.111.27
  - Primary workstation

### Design Session → Build Pipeline
- Interactive design sessions: brainstorm with Andy, produce a full app roadmap with phases and batches
- Autonomous build pipeline: dispatch work to local dev agents, verify output, iterate, write tests
- Runs to completion without human intervention once a design is approved
- Can manage multiple projects simultaneously across the AI-Lab

### Agent Trainer
- Reviews completed work, grades code quality and test coverage
- Writes improved guidelines, prompts, and agent instructions back into shared memory
- Builds up agent skill profiles and domain knowledge over time
- Every development cycle makes the agents measurably better
- Feeds into the decision grading system (same pipeline as specialist grading)

### Shared Memory Layer
- SQLite Knowledge Lake (same architecture as existing engines)
- Stores: project inventories, coding patterns learned, past decisions and outcomes, agent skill levels, refined prompt templates
- Every agent reads before acting, writes back after completing work
- Cross-pollination: patterns learned in one project improve work on all projects

### Goal
- Minimize Claude API token usage over time — Claude handles genuinely novel architectural problems
- Maximize local Ollama agent capability — routine coding, testing, docs handled entirely locally
- Self-improving loop: better agents → better code → better grading data → better agents

---

## Phase 9: Model Training Pipeline
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
| Dev agent node | EliteBook (192.168.111.28) | — | Project Forge dev agents (code, test, review) |
| Dev agent node | Mini PC (192.168.111.27) | — | Project Forge dev agents (parallel builds) |
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
Phase 4  ░░░░░░░░░░░░░░░░░░░░ PLANNED — Web Dashboard + Android OS
Phase 5  ░░░░░░░░░░░░░░░░░░░░ PLANNED — Computer Vision
Phase 6  ░░░░░░░░░░░░░░░░░░░░ PLANNED — Smart Home Hub (BLE/IoT)
Phase 7  ░░░░░░░░░░░░░░░░░░░░ PLANNED — Network Security Agent
Phase 8  ░░░░░░░░░░░░░░░░░░░░ PLANNED — Project Forge (Autonomous Dev)
Phase 9  ░░░░░░░░░░░░░░░░░░░░ PLANNED — Model Training Pipeline
```
