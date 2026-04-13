# Jarvis: 10 Recommendations for a Self-Improving Household Intelligence

**Audience:** Andy Drzewiecki | **Date:** 2026-04-13 | **Perspective:** PhD-level systems architecture + AI engineering

These aren't incremental features. Each one represents a fundamental capability that compounds with the others. Together they transform Jarvis from "a chatbot that knows about your groceries" into something closer to a **cognitive operating system** — a system that reasons about your household the way a brilliant, tireless chief of staff would.

---

## 1. Metacognitive Supervisor — The Specialist That Watches the Specialists

**What it is:** A dedicated meta-agent that observes every specialist's performance — their decision accuracy, confidence calibration, KB contribution quality, execution time, and failure patterns — and continuously tunes the system.

**Why it matters:** Without this, you're managing a zoo of agents by hand. With it, the system manages itself. The metacognitive supervisor can rewrite specialist prompts that are producing low-confidence outputs, adjust schedules based on when data sources actually update, propose entirely new specialists when it detects knowledge gaps that no current specialist owns, and retire or merge specialists that overlap.

**How it works:**

```
┌─────────────────────────────────────────────────────┐
│              METACOGNITIVE SUPERVISOR                │
│                                                     │
│  Inputs:                                            │
│  ├── agent_memory (all 478+ decision records)       │
│  ├── kb_index (freshness, confidence distributions) │
│  ├── specialist execution logs (timing, errors)     │
│  └── user feedback signals (accepted/rejected)      │
│                                                     │
│  Outputs:                                           │
│  ├── Prompt rewrites for underperforming specs      │
│  ├── Schedule adjustments (spec X runs too often)   │
│  ├── New specialist proposals → DevTeam builds it   │
│  ├── Model reassignment (spec Y needs 70B, not 7B) │
│  └── Weekly "system health" report to Andy          │
└─────────────────────────────────────────────────────┘
```

**The key insight:** This creates a closed feedback loop. Most AI agent systems are open-loop — they execute but never learn from their own execution patterns. The metacognitive supervisor closes that loop. It's the difference between a tool and an organism.

**Research grounding:** This draws from metacognition in cognitive science (Flavell, 1979) and the Observe-Orient-Decide-Act (OODA) loop applied at the system level. In multi-agent systems research, this is sometimes called a "controller agent" — but the self-modification of other agents' prompts and schedules goes beyond what most frameworks implement.

---

## 2. Causal Knowledge Graph — Not Just Facts, But Why

**What it is:** Extend the Knowledge Lake with a directed graph layer that captures causal relationships between facts. Not just "chicken is $1.99/lb at Aldi" and "grocery budget is at 72%" — but the causal chain: "If we switch from beef ($6/lb) to chicken ($1.99/lb) for 3 dinners this week, projected monthly spend drops by $48, bringing budget to 66%."

**Why it matters:** Flat facts let you answer "what." Causal graphs let you answer "what if" and "why." This is the difference between a database and an advisor.

**Architecture:**

```sql
-- New table in facts.db
CREATE TABLE causal_edges (
    id              TEXT PRIMARY KEY,
    cause_id        TEXT NOT NULL,      -- kb_index id
    effect_id       TEXT NOT NULL,      -- kb_index id
    relationship    TEXT NOT NULL,      -- 'increases', 'decreases', 'triggers', 'blocks'
    strength        REAL DEFAULT 0.5,   -- 0.0-1.0, learned over time
    observed_count  INTEGER DEFAULT 1,  -- how many times we've seen this pattern
    last_observed   TEXT NOT NULL,
    mechanism       TEXT                -- LLM-generated explanation of WHY
);
```

**Example causal chains the system would discover:**

```
[Aldi sale on chicken] --increases--> [Chicken-based meal plans]
                                          |
                                     --decreases--> [Monthly grocery spend]
                                          |
                                     --increases--> [Budget surplus]
                                          |
                                     --enables--> [Weekend family dinner out]

[Soccer practice on Tuesday] --blocks--> [Cooking complex Tuesday dinners]
                                          |
                                     --triggers--> [Crock-pot/meal-prep suggestions]
```

**How specialists build it:** During the `analyze()` phase, each specialist doesn't just extract facts — it asks the LLM: "Given these new facts and the existing KB, what causal relationships can you identify?" The edges accumulate and strengthen over time as the same patterns are observed repeatedly.

**Research grounding:** This is an application of causal inference (Pearl, 2009) to household knowledge management. The graph structure draws from knowledge graph embedding research (TransE, RotatE) but uses LLM reasoning instead of learned embeddings — more appropriate for a low-data, high-domain-diversity household context.

---

## 3. Household Digital Twin — Simulate Before You Act

**What it is:** A forward-simulation engine that models your household's state over time. Given current inventory, schedules, budgets, maintenance timelines, and historical patterns, Jarvis can simulate forward days or weeks to predict problems before they happen.

**Why it matters:** Reactive systems solve problems. Predictive systems prevent them. The digital twin lets Jarvis say "heads up: if nobody goes to the store by Wednesday, you'll be out of milk and eggs, and Thursday is Emma's school lunch day" — not because you asked, but because it ran the simulation overnight.

**How it works:**

```python
class HouseholdSimulator:
    """Monte Carlo forward simulation of household state."""

    def simulate(self, days_ahead: int = 14, runs: int = 100) -> SimulationResult:
        """
        For each run:
        1. Load current state from KB (inventory, schedules, budgets)
        2. Apply daily consumption model (learned from history)
        3. Apply scheduled events (soccer, dentist, school)
        4. Apply probabilistic events (unexpected expense, sick day)
        5. Check for constraint violations (out of stock, over budget, conflict)
        6. Record the day each violation first appears
        
        Returns: probability distribution of future problems.
        """
        ...

    def what_if(self, intervention: str) -> ComparisonResult:
        """
        LLM parses the intervention into state changes, then runs
        two simulations: with and without the intervention.
        
        "What if we switch to Aldi for all shopping?"
        "What if we cancel the gym membership?"
        "What if I take Friday off?"
        """
        ...
```

**Output example (from the daily brief):**

```
HOUSEHOLD FORECAST (next 7 days):
- 92% chance you run out of bread by Thursday
- Soccer schedule conflicts with dentist on Tuesday (both at 4pm)
- Furnace filter hits 90-day mark on Friday — last change was Jan 15
- Budget tracking at 68% with 18 days remaining — on pace
- Weather: rain Wednesday-Thursday → suggest indoor meal prep day
```

**Research grounding:** Agent-based modeling (ABM) applied at household scale. The Monte Carlo approach handles uncertainty naturally — you don't need exact consumption rates, just distributions. The "what-if" capability is counterfactual reasoning (Pearl's Ladder of Causation, rung 3).

---

## 4. Active Preference Learning — Watch What Andy Does, Not Just What He Says

**What it is:** A passive observation layer that tracks which of Jarvis's suggestions you accept, modify, or ignore — and uses that signal to continuously refine your preference model without you ever having to explicitly state preferences.

**Why it matters:** `preferences.json` has 12 fields you manually set. But your real preferences are orders of magnitude more complex: you reject Thai food on weeknights but love it on weekends. You always override the meal plan when company is coming. You never take the cheapest option for kids' shoes. These patterns are in your behavior, not in a config file.

**Architecture:**

```sql
CREATE TABLE preference_signals (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    domain          TEXT NOT NULL,
    suggestion_id   TEXT,               -- what Jarvis suggested
    action          TEXT NOT NULL,       -- 'accepted', 'modified', 'rejected', 'ignored'
    context         TEXT,               -- time of day, day of week, who's home, etc.
    modification    TEXT                -- if modified, what did you change?
);

CREATE TABLE learned_preferences (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    rule            TEXT NOT NULL,       -- "Avoid Thai on weeknights"
    confidence      REAL DEFAULT 0.5,
    evidence_count  INTEGER DEFAULT 1,
    last_updated    TEXT NOT NULL,
    context_conditions TEXT              -- JSON: when does this preference apply?
);
```

**The feedback loop:**

```
Andy rejects suggestion ──▶ Log to preference_signals
                                    │
                           ┌────────▼─────────┐
                           │  Preference Miner │ (runs weekly)
                           │                   │
                           │  LLM analyzes all │
                           │  signals, extracts│
                           │  patterns, writes │
                           │  learned_prefs    │
                           └────────┬──────────┘
                                    │
                           ┌────────▼─────────┐
                           │ Specialists read  │
                           │ learned_prefs to  │
                           │ tailor future     │
                           │ suggestions       │
                           └──────────────────┘
```

**Critical design constraint:** Jarvis never tells you "I noticed you don't like X." It just quietly stops suggesting it. The preference model is implicit and non-creepy. You can query it ("what do you know about my food preferences?") but it never volunteers this meta-information unsolicited.

**Research grounding:** This is reward modeling from RLHF (Christiano et al., 2017) applied at the application layer. Instead of training model weights, you're training a preference database. The contextual aspect (preferences change based on day/time/situation) draws from contextual bandits research.

---

## 5. Autonomous Code Evolution — Jarvis Improves Its Own Codebase

**What it is:** Connect the metacognitive supervisor (#1) to the DevTeam adapter to create a system that writes code to improve itself. When the metacognitive layer identifies a pattern — "the grocery specialist fails 30% of the time because it can't parse Aldi's new HTML format" — it can generate a ticket, have DevTeam write a fix, run the tests, and (with your approval) deploy the patch.

**Why it matters:** This is the holy grail of self-improving systems. Most AI agent frameworks require a human developer to fix bugs and add features. Jarvis could theoretically maintain and extend itself, with you as the approving authority.

**The pipeline:**

```
Metacognitive Supervisor
  detects: "GrocerySpec fails on price_check 30% of the time"
  diagnoses: "Aldi website changed their DOM structure"
      │
      ▼
Generates improvement ticket:
  {
    "type": "bug_fix",
    "target": "jarvis/adapters/grocery.py",
    "description": "Aldi price scraper broken — new HTML layout",
    "evidence": [decision_ids...],
    "priority": "high"
  }
      │
      ▼
DevTeam Adapter (Architect → Developer → QA)
  writes: patch to grocery.py
  tests: pytest passes
  artifacts: jarvis/adapters/devteam/artifacts/fix-aldi-scraper/
      │
      ▼
HUMAN APPROVAL GATE (critical safety boundary)
  Andy reviews diff → approves → hot-reload or next restart
      │
      ▼
Metacognitive Supervisor
  monitors: "GrocerySpec price_check success rate now 95%"
  records: improvement validated
```

**Safety constraints (non-negotiable):**

1. **No self-modification without human approval.** Ever. The system proposes, Andy disposes.
2. **All changes go through the existing QA pipeline** with tests.
3. **Rollback is always available** — git history preserves every state.
4. **The approval gate cannot be removed or bypassed by any agent.** This is a hard architectural constraint, not a prompt instruction.

**What this enables over time:** Jarvis accumulates a growing library of self-written tools, parsers, integrations, and utilities. Each improvement feeds back into the system's capability. After a year, the codebase could be 50% human-written (your foundation) and 50% machine-written (specialized tooling).

**Research grounding:** This draws from program synthesis research (Gulwani et al., 2017) and self-play in software engineering (SWE-Bench). The critical addition is the metacognitive trigger — the system identifies what code needs to change based on operational telemetry, not just a human ticket. The hard approval gate is informed by AI safety research on corrigibility (Soares et al., 2015).

---

## 6. Household State Machine — Context Changes Everything

**What it is:** Model your household as a finite state machine with explicit states and transitions. Every specialist adjusts its behavior based on the current household state.

**Why this is different from just having schedules:** A schedule says "it's Tuesday." A state machine says "it's the first week of summer break, one kid is sick, we have guests arriving Friday, and the budget is tight this month." All of those conditions compose into a state that should change how every specialist behaves.

**States and transitions:**

```python
HOUSEHOLD_STATES = {
    "normal":       {"description": "Regular routine, no special conditions"},
    "school_year":  {"description": "Kids in school, structured weekday schedule"},
    "summer":       {"description": "Kids home, flexible schedule, higher food budget"},
    "holiday":      {"description": "Holiday period — special meals, gifts, events"},
    "travel":       {"description": "Family is traveling — pause home monitoring"},
    "sick_house":   {"description": "Someone is ill — adjust meals, cancel events"},
    "guests":       {"description": "Hosting visitors — extra food, clean house"},
    "crunch":       {"description": "Andy in work crunch — minimize interruptions"},
    "budget_tight": {"description": "Over budget — maximize savings across all domains"},
}

# Transitions detected automatically from KB signals:
# - CalendarSpec detects "last day of school" → transition to 'summer'
# - HealthSpec detects sick-day patterns → transition to 'sick_house'
# - FinanceSpec detects spend > 90% budget → add 'budget_tight' modifier
# - Andy says "guests arriving Friday" → transition to 'guests'
```

**How specialists use state:**

```python
class GrocerySpec(BaseSpecialist):
    def analyze(self, raw_data):
        state = household_state.current()
        
        if "guests" in state.modifiers:
            # Scale up quantities, suggest crowd-pleasing meals
            ...
        if "budget_tight" in state.modifiers:
            # Prioritize store-brand, sale items, cheaper proteins
            ...
        if state.primary == "summer":
            # More snacks, lunch ingredients (kids home all day)
            ...
```

**The composability is key.** States aren't mutually exclusive — you can be in "summer" + "budget_tight" + "guests" simultaneously. Each specialist reads the full state vector and adjusts its behavior accordingly. This is how you get emergent intelligence: the system responds to complex life situations without anyone explicitly programming each combination.

**Research grounding:** Hierarchical state machines (Harel statecharts) combined with context-aware computing (Dey, 2001). The compositional state vector (multiple simultaneous states) draws from the blackboard architecture pattern in AI.

---

## 7. Temporal Reasoning Engine — Track What You Believed and When

**What it is:** A bitemporal knowledge system that tracks not just "what is true now" but "what did we believe at any point in time, and when did that belief change." Every fact in the KB gets two timestamps: when it became true in the world (valid_time) and when Jarvis learned it (transaction_time).

**Why it matters:** This enables three powerful capabilities:

1. **Surprise detection:** "We budgeted $800 for groceries but spent $950 — when did the overspend start?" Jarvis can replay the belief timeline and pinpoint the moment things diverged.

2. **Trend analysis that actually works:** Instead of just comparing this month to last month, Jarvis can track the evolution of its own confidence in a prediction. "On April 1 I was 90% confident the budget would hold. By April 10, confidence dropped to 60%. What changed?"

3. **Counterfactual debugging:** "If I had known on Tuesday that soccer was cancelled, I would have suggested a more complex dinner instead of a quick meal." This lets the system learn from information-timing failures.

**Schema addition:**

```sql
ALTER TABLE kb_index ADD COLUMN valid_from TEXT;     -- when the fact became true in reality
ALTER TABLE kb_index ADD COLUMN valid_until TEXT;     -- when it stopped being true (null = still true)
ALTER TABLE kb_index ADD COLUMN transaction_at TEXT;  -- when Jarvis learned this fact

-- Belief revision log
CREATE TABLE belief_revisions (
    id              TEXT PRIMARY KEY,
    fact_id         TEXT NOT NULL,       -- kb_index id
    revision_type   TEXT NOT NULL,       -- 'created', 'updated', 'superseded', 'invalidated'
    old_value       TEXT,
    new_value       TEXT,
    reason          TEXT,               -- why the belief changed
    revised_at      TEXT NOT NULL
);
```

**Example query the system can now answer:**

"Why did we go over budget in March?"

```
Jarvis replays March belief timeline:
- Mar 1: Budget set at $800. Projected spend: $780. Confidence: 0.92
- Mar 8: Unexpected car repair ($400). FinanceSpec revised projected spend to $920.
         Surprise detection fired. Budget_tight state activated.
- Mar 12: GrocerySpec shifted to budget-conscious meals. Projected grocery: $680 → $620.
- Mar 15: School announced bake sale. GrocerySpec added $40 in baking supplies.
- Mar 31: Actual spend: $850. Overshoot driven by car repair, partially offset by grocery savings.

Recommendation: Add a $200 emergency buffer to monthly budget, or create a 
separate 'unexpected maintenance' category.
```

**Research grounding:** Bitemporal databases (Snodgrass, 2000) are well-established in enterprise systems but almost never applied to personal AI. The belief revision aspect draws from AGM theory (Alchourrón, Gärdenfors, Makinson, 1985) — a formal framework for how rational agents should update beliefs.

---

## 8. Multi-Modal Memory — See, Hear, and Read

**What it is:** Extend the KB beyond text to handle images, audio, and structured documents natively. Your EVO-X2 nodes can run vision models (LLaVA, Qwen-VL) and speech models (Whisper) locally.

**Why it matters:** Half of household knowledge isn't text. It's the photo of the leak under the sink. It's the voice memo you recorded while driving about the thing you need from Home Depot. It's the screenshot of the price you saw online. Right now all of that is trapped in your phone's camera roll, inaccessible to Jarvis.

**Architecture:**

```python
class MultiModalIngest:
    """Processes non-text inputs into KB entries."""

    def process_image(self, image_path: str, context: str = "") -> list[KBEntry]:
        """
        Uses local vision model (LLaVA/Qwen-VL via Ollama) to:
        1. Describe what's in the image
        2. Extract structured data (receipts → prices, labels → inventory)
        3. Identify actionable items (leak photo → maintenance entry)
        4. Store original image + extracted text in KB
        """
        ...

    def process_voice_memo(self, audio_path: str) -> list[KBEntry]:
        """
        Uses local Whisper to transcribe, then LLM to:
        1. Extract action items ("need to pick up drywall screws")
        2. Identify domain (home, grocery, kids, etc.)
        3. Create KB entries with source_type='voice_memo'
        """
        ...

    def process_document(self, doc_path: str) -> list[KBEntry]:
        """
        Handle PDFs, spreadsheets, etc:
        1. Extract text/tables
        2. LLM identifies what it is (insurance doc, school schedule, recipe)
        3. Route to appropriate specialist for deeper processing
        """
        ...
```

**Integration with Google ecosystem:**
- Google Photos API → auto-ingest receipt photos, home repair photos
- Google Drive → sync shared family documents into KB
- Google Keep → pull voice memos and notes

**Killer use case:** You take a photo of a shelf at Costco. Jarvis vision model reads the price tags, compares to its KB prices, and texts you: "The Kirkland olive oil is $2/L cheaper than your usual Aldi brand. Also, you're running low on olive oil — last bottle opened March 28."

**Research grounding:** Multi-modal RAG systems (retrieval-augmented generation) are a hot research area, but deploying them fully local with on-device vision+speech is cutting-edge. The automated ingest pipeline draws from document understanding research (LayoutLM, Donut models).

---

## 9. Collaborative Family Interface — Not Just Andy's Tool

**What it is:** A family-accessible interface layer where each family member has a profile, and Jarvis tailors its interactions (complexity, tone, domains) per person. Kids can ask Jarvis about their schedule. Your partner can ask about the meal plan. But only you can approve budget changes or modify system settings.

**Why it matters:** A household intelligence system that only one person can use is half as useful. But access control matters — you don't want your 8-year-old accidentally telling Jarvis to order $500 worth of Lego.

**Architecture:**

```python
class FamilyMember:
    name: str
    role: str                   # 'admin', 'adult', 'child'
    voice_profile: bytes        # for voice recognition (local Whisper embeddings)
    allowed_domains: list[str]  # kids can read schedule, not modify budget
    personality_mode: str       # 'fun' for kids, 'professional' for Andy
    notification_channel: str   # Discord, SMS, Android push, etc.

class PermissionMatrix:
    """Role-based access control for KB operations."""
    PERMISSIONS = {
        'admin':  {'read': '*', 'write': '*', 'approve': '*', 'configure': '*'},
        'adult':  {'read': '*', 'write': ['grocery', 'schedule', 'home'],
                   'approve': ['grocery_purchase'], 'configure': []},
        'child':  {'read': ['schedule', 'grocery.meal_plan'], 'write': [],
                   'approve': [], 'configure': []},
    }
```

**Interface options:**
- **Android app** (you already have `jarvis-android/` scaffolded) with per-user login
- **Voice interface** — Whisper + speaker diarization to identify who's talking
- **Shared family dashboard** — wall-mounted tablet showing today's schedule, meal plan, to-do's
- **SMS/Discord** — each family member has their own channel with Jarvis

**The personality layer you already built (`personality.py`) becomes per-user.** When your kid asks "what's for dinner?", Jarvis responds differently than when you ask about monthly spend projections.

**Research grounding:** Multi-user personalization in conversational AI (Li et al., 2016), role-based access control (RBAC) applied to AI agent systems. The voice identification aspect uses speaker embedding research (d-vectors, x-vectors) running on-device.

---

## 10. Emergent Capability Discovery — Let the System Surprise You

**What it is:** A meta-level process where Jarvis periodically asks itself: "Given everything I know across all domains, what useful capabilities could I offer that nobody has asked for yet?" It then proposes new workflows, automations, or insights that emerge from cross-domain knowledge.

**Why it matters:** This is the difference between a tool (does what you ask) and an intelligence (offers what you haven't thought to ask). The most valuable insights are the ones you didn't know you needed.

**How it works:**

```python
class CapabilityDiscovery:
    """Runs weekly. Looks for emergent patterns across the full KB."""

    def discover(self) -> list[Proposal]:
        # 1. Pull cross-domain knowledge graph
        all_facts = kb.recent_by_domain(limit_per_domain=50)
        causal_graph = kb.get_causal_edges(min_strength=0.3)
        
        # 2. Ask LLM to identify non-obvious connections
        prompt = f"""
        You are analyzing a household knowledge base spanning these domains:
        {domains}
        
        Here are recent facts and their causal relationships:
        {formatted_kb_context}
        
        Identify 3-5 non-obvious connections, optimizations, or automations
        that would benefit this household. Focus on cross-domain insights
        that no single specialist would discover alone.
        
        For each, provide:
        - The insight
        - Which domains it connects
        - A concrete action or automation
        - Estimated impact (time saved, money saved, quality of life)
        """
        
        # 3. Filter through feasibility check
        # 4. Present to Andy as "Jarvis has a suggestion..."
```

**Example discoveries the system might surface:**

- "I noticed you always order takeout on days when both kids have activities after school. I could pre-stage crock-pot meals on those days — saves ~$40/week and the family eats better."

- "Your electricity bill spikes in months when the furnace filter is overdue. The $3 filter change saves approximately $25/month in HVAC efficiency. I've added automatic 60-day reminders."

- "You've been researching standing desks for 3 weeks but haven't bought one. The Uplift V2 you bookmarked just dropped 20% on Amazon. Your fun budget has $180 remaining this month — enough to cover it."

- "Emma's piano teacher cancelled 3 of the last 8 lessons. At $45/lesson, you've paid for 8 but received 5. I've drafted a polite email requesting either makeup lessons or a credit."

**The critical distinction:** These aren't pre-programmed rules. They're emergent from the cross-domain knowledge graph. No one told the system to correlate furnace filters with electricity bills — it discovered the pattern from its own data.

**Research grounding:** This draws from computational creativity research (Boden, 2004) — specifically "exploratory creativity" where novel discoveries emerge from combining existing knowledge in unexpected ways. The cross-domain pattern detection is related to analogical reasoning research (Gentner, 1983) applied at the system level.

---

## How These Compound

The real power isn't any single recommendation — it's how they interact:

```
Metacognitive Supervisor (#1) monitors all specialists
    │
    ├── Detects that GrocerySpec suggestions are frequently rejected
    │   └── Active Preference Learning (#4) identifies: "Andy rejects 
    │       suggestions that conflict with the household state"
    │       └── Household State Machine (#6) wasn't accounting for 
    │           'crunch' mode (Andy ignores complex cooking when busy)
    │           └── Metacognitive supervisor rewrites GrocerySpec prompt
    │               to respect crunch mode → acceptance rate improves
    │
    ├── Causal Knowledge Graph (#2) discovers furnace→electricity link
    │   └── Household Digital Twin (#3) simulates the savings
    │       └── Emergent Capability Discovery (#10) surfaces it to Andy
    │           └── Andy approves → Autonomous Code Evolution (#5) 
    │               creates the maintenance-reminder workflow
    │
    └── Temporal Reasoning (#7) detects belief revision pattern:
        "We keep underestimating summer grocery costs"
        └── Digital Twin (#3) runs summer simulation with corrected model
            └── FinanceSpec adjusts summer budget recommendation
                └── Preference Learning (#4) notes Andy accepted this time
```

Each capability amplifies the others. The system gets smarter not linearly, but combinatorially.

---

## Implementation Order (What to Build First)

| Priority | Recommendation | Reason |
|----------|---------------|--------|
| 1st | #6 Household State Machine | Lightweight, immediately useful, changes specialist behavior |
| 2nd | #4 Active Preference Learning | Just logging at first — start collecting signal now |
| 3rd | #2 Causal Knowledge Graph | Extends the KB schema you're already building |
| 4th | #1 Metacognitive Supervisor | Requires other specialists running to have something to supervise |
| 5th | #3 Household Digital Twin | Requires causal graph + state machine as inputs |
| 6th | #7 Temporal Reasoning | Schema extension, can be retrofitted |
| 7th | #8 Multi-Modal Memory | Requires EVO-X2 for vision model VRAM |
| 8th | #10 Emergent Discovery | Requires rich KB to have something to discover from |
| 9th | #9 Family Interface | Requires the system to be useful first, then share it |
| 10th | #5 Code Self-Evolution | Requires everything else working reliably first |

---

## The North Star

A year from now, Jarvis shouldn't feel like software. It should feel like a household member who happens to have perfect memory, infinite patience, and the ability to think about 8 things at once. Not because any single component is magical, but because the feedback loops between components create emergent intelligence that no individual piece could produce alone.

The system that watches itself, learns from its mistakes, predicts your needs, and occasionally surprises you with insights you never asked for — that's not a chatbot. That's a cognitive operating system for your life.
