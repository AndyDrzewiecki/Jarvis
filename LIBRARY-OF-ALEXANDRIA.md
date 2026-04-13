# The Library of Alexandria — Self-Building Local Knowledge System

**Author:** Andy + Claude | **Date:** 2026-04-13 | **Status:** Design

---

## Vision

Every specialist domain in Jarvis operates its own **research institution** — a background agent that continuously builds and curates a deep, local knowledge base. Not just household data, but the *best available knowledge* on its topic: research papers, open-source projects, techniques, historical data, pricing models, best practices. Each specialist maintains its own "library wing" while contributing to a shared catalog.

The system doesn't just answer questions — it **knows the state of the art** in every domain it covers, grades its own decisions, writes its own operating guidelines, and gets better at all of this over time.

```
┌──────────────────────────────────────────────────────────────────────┐
│                  THE LIBRARY OF ALEXANDRIA                            │
│                  Local to Andy's household                            │
│                                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │ GROCERY │  │ FINANCE │  │  HOME   │  │ INVEST  │  │ DEV/ENG │  │
│  │  WING   │  │  WING   │  │  WING   │  │  WING   │  │  WING   │  │
│  │         │  │         │  │         │  │         │  │         │  │
│  │ recipes │  │ historc │  │ repair  │  │ market  │  │ papers  │  │
│  │ pricing │  │ budgets │  │ guides  │  │ models  │  │ repos   │  │
│  │ nutri-  │  │ tax     │  │ maint   │  │ strat-  │  │ frame-  │  │
│  │ tion    │  │ rules   │  │ sched   │  │ egies   │  │ works   │  │
│  │ deals   │  │ savings │  │ costs   │  │ papers  │  │ tools   │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  │
│       │            │            │            │            │          │
│       └────────────┴────────────┴────────────┴────────────┘          │
│                              │                                       │
│                    ┌─────────▼──────────┐                            │
│                    │  SHARED CATALOG    │                            │
│                    │  Cross-referenced  │                            │
│                    │  Searchable        │                            │
│                    │  Versioned         │                            │
│                    └────────────────────┘                            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Part 1: The Research Librarian — Every Specialist Gets One

Each specialist domain has a **Research Librarian** agent that runs alongside the operational specialist. While the operational specialist handles day-to-day tasks (meal planning, budget checking), the Research Librarian builds and curates the domain's knowledge base in the background.

### Research Librarian Architecture

```python
class ResearchLibrarian:
    """
    Background agent that builds a deep local KB for a domain.
    Runs on a longer cycle than operational specialists (daily/weekly).
    """

    domain: str                      # "grocery", "finance", "home", etc.
    research_schedule: str           # cron expression
    depth_level: str                 # "survey", "deep", "exhaustive"

    def survey(self) -> list[ResearchItem]:
        """
        Phase 1: Cast a wide net. Find relevant resources:
        - Academic papers (arXiv, Semantic Scholar API)
        - GitHub repositories (trending + domain-specific)
        - Blog posts and guides (RSS feeds, curated sources)
        - Government data (USDA for food prices, BLS for economics)
        - Open datasets (Kaggle, data.gov)
        
        Returns candidate items for deeper evaluation.
        """
        ...

    def evaluate(self, candidates: list[ResearchItem]) -> list[ResearchItem]:
        """
        Phase 2: LLM reads each candidate and scores:
        - Relevance to household use case (not academic interest)
        - Actionability (can this actually help Andy's family?)
        - Quality (peer-reviewed? well-starred repo? maintained?)
        - Novelty (do we already know this? does it add anything?)
        
        Only items scoring above threshold proceed to cataloging.
        """
        ...

    def catalog(self, items: list[ResearchItem]) -> list[str]:
        """
        Phase 3: Extract key knowledge and store in the domain's wing:
        - Summarize the resource (1 paragraph)
        - Extract actionable insights (bullet points)
        - Tag with metadata (topic, date, source quality)
        - Store full text locally for future reference
        - Link to related items already in the wing (Zettelkasten)
        - Update the domain's "state of knowledge" document
        """
        ...

    def curate(self) -> CurationReport:
        """
        Phase 4: Maintain the wing. Runs weekly:
        - Retire outdated resources (papers superseded, repos archived)
        - Strengthen links between related items
        - Identify knowledge gaps (topics with no coverage)
        - Generate "research requests" for the next survey cycle
        - Update the domain's guidelines document
        """
        ...
```

### Domain-Specific Librarian Configurations

| Domain | Key Sources | Research Focus | Update Cadence |
|--------|-----------|---------------|----------------|
| **Grocery** | USDA food prices, recipe APIs, nutrition databases, store APIs, couponing blogs | Price trends, nutrition optimization, seasonal produce, bulk buying strategies, meal prep techniques | Daily (prices), weekly (recipes/strategies) |
| **Finance** | BLS economic data, IRS publications, personal finance research, budgeting frameworks | Tax optimization, savings strategies, household budgeting models, debt payoff algorithms | Weekly (strategies), monthly (tax/regulatory) |
| **Home** | Home repair guides (Family Handyman, This Old House), HVAC manuals, appliance databases, contractor rating APIs | Maintenance schedules by appliance/system, DIY vs. hire decision frameworks, seasonal checklists, energy efficiency research | Weekly (guides), monthly (maintenance models) |
| **Investing** | SEC filings, Federal Reserve data, arXiv quantitative finance, financial modeling repos | Market regime detection, portfolio theory, risk models, tax-loss harvesting algorithms | Daily (market data), weekly (research) |
| **Dev/Engineering** | arXiv CS papers, GitHub trending, HackerNews, framework documentation, AI research | LLM agent architectures, local AI deployment, tool/framework comparisons, Jarvis self-improvement research | Daily (trending), weekly (deep dives) |
| **Health** | NIH/PubMed, CDC guidelines, nutrition research, exercise science | Family health guidelines by age, preventive care schedules, nutrition science, sleep research | Weekly |
| **Kids/Education** | Education research, age-appropriate activity databases, school district APIs | Developmental milestones, enrichment activities, homework help strategies, schedule optimization | Weekly |

### Storage Structure on Disk

```
data/library/
├── catalog.db                    # SQLite: master catalog of all resources
├── grocery/
│   ├── wing_index.json           # domain-specific search index
│   ├── guidelines.md             # self-written operating guidelines
│   ├── state_of_knowledge.md     # current summary of what this wing knows
│   ├── resources/
│   │   ├── usda_price_history/   # downloaded datasets
│   │   ├── papers/               # saved PDFs/summaries
│   │   ├── repos/                # cloned/summarized GitHub repos
│   │   └── guides/               # curated how-to content
│   └── models/
│       ├── price_prediction.json # trained price trend model
│       └── meal_optimization.json# scoring model for meal suggestions
├── finance/
│   ├── wing_index.json
│   ├── guidelines.md
│   ├── state_of_knowledge.md
│   ├── resources/
│   │   ├── historical/           # ← THE HISTORICALS (see Part 2)
│   │   │   ├── spending_2026.db
│   │   │   ├── budgets_archive/
│   │   │   └── tax_records/
│   │   ├── papers/
│   │   └── models/
│   └── models/
│       ├── budget_forecast.json
│       └── savings_optimizer.json
├── home/
│   └── ...
├── investing/
│   └── ...
└── shared/
    ├── cross_references.db       # links between wings
    └── research_queue.json       # pending research requests from any specialist
```

### Catalog Schema

```sql
-- Master catalog: every resource across all wings
CREATE TABLE library_catalog (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    resource_type   TEXT NOT NULL,       -- 'paper', 'repo', 'dataset', 'guide',
                                        -- 'model', 'api', 'tool', 'regulation'
    title           TEXT NOT NULL,
    source_url      TEXT,
    local_path      TEXT,               -- where it's stored on disk
    summary         TEXT NOT NULL,       -- LLM-generated summary
    actionable_insights TEXT,           -- JSON: extracted actionable items
    quality_score   REAL,               -- 0-1, assessed during evaluation
    relevance_score REAL,               -- 0-1, to household use case
    novelty_score   REAL,               -- 0-1, vs existing knowledge
    discovered_at   TEXT NOT NULL,
    last_verified   TEXT,               -- when was this resource still valid?
    status          TEXT DEFAULT 'active', -- 'active', 'outdated', 'superseded', 'archived'
    superseded_by   TEXT,               -- id of newer resource
    tags            TEXT,               -- comma-separated
    embedding_id    TEXT                -- ChromaDB vector for semantic search
);

-- Research requests: what the system wants to learn more about
CREATE TABLE research_queue (
    id              TEXT PRIMARY KEY,
    requesting_agent TEXT NOT NULL,     -- which specialist wants this
    topic           TEXT NOT NULL,
    reason          TEXT NOT NULL,      -- why is this needed?
    priority        TEXT DEFAULT 'normal', -- 'low', 'normal', 'high', 'critical'
    created_at      TEXT NOT NULL,
    assigned_to     TEXT,              -- which librarian picked it up
    completed_at    TEXT,
    result_id       TEXT               -- catalog entry id if fulfilled
);
```

---

## Part 2: The Historical Context Engine

Every domain builds **historicals** — a deep longitudinal record that grows richer over time and serves as the foundation for trend analysis, prediction, and self-evaluation.

### Finance Historicals (Example)

The Finance Librarian doesn't just track this month's budget. It builds a comprehensive financial history of the household:

```sql
-- Historical spending database (finance wing)
CREATE TABLE spending_history (
    id              TEXT PRIMARY KEY,
    date            TEXT NOT NULL,
    category        TEXT NOT NULL,       -- grocery, utilities, gas, dining, etc.
    amount          REAL NOT NULL,
    vendor          TEXT,
    payment_method  TEXT,
    tags            TEXT,               -- 'recurring', 'unexpected', 'discretionary'
    notes           TEXT,
    source          TEXT                -- 'bank_api', 'receipt_scan', 'manual'
);

CREATE TABLE budget_history (
    id              TEXT PRIMARY KEY,
    period          TEXT NOT NULL,       -- '2026-04'
    category        TEXT NOT NULL,
    budgeted        REAL NOT NULL,
    actual          REAL NOT NULL,
    variance        REAL NOT NULL,
    variance_pct    REAL NOT NULL,
    notes           TEXT,               -- LLM-generated variance explanation
    grade           TEXT                -- self-assigned grade (see Part 4)
);

CREATE TABLE price_history (
    id              TEXT PRIMARY KEY,
    item            TEXT NOT NULL,
    store           TEXT NOT NULL,
    price           REAL NOT NULL,
    unit            TEXT,
    observed_at     TEXT NOT NULL,
    source          TEXT                -- 'api', 'receipt', 'manual', 'scrape'
);

-- Indices for time-series queries
CREATE INDEX idx_spending_date ON spending_history(date);
CREATE INDEX idx_spending_category ON spending_history(category, date);
CREATE INDEX idx_prices_item ON price_history(item, observed_at);
```

### How Historicals Get Built

Two complementary processes run simultaneously:

**Background Historical Builder** (builds the past):
```python
class HistoricalBuilder:
    """
    Constructs historical records from available data sources.
    Runs on a daily schedule, backfilling when new data sources connect.
    """

    def build_financial_history(self):
        """
        Sources:
        1. Bank API transactions (if connected)
        2. Receipt scans (receipt_ingest adapter)
        3. Google Sheets budget tracking (Google integration)
        4. Manual entries from conversations
        5. Decision log (agent_memory) for past spending decisions
        
        Process:
        - Pull all available data
        - Deduplicate across sources
        - Categorize (LLM classifies uncategorized transactions)
        - Store in spending_history
        - Compute monthly summaries in budget_history
        """
        ...

    def build_price_history(self):
        """
        Sources:
        1. Store APIs and web scraping
        2. Receipt scans (exact prices paid)
        3. USDA average price data (government baseline)
        
        Process:
        - Pull from all sources
        - Normalize units (per lb, per oz, per each)
        - Store in price_history
        - Compute trend models (moving average, seasonal decomposition)
        """
        ...
```

**Current Data Agents** (builds the present):
```python
class CurrentDataAgent:
    """
    Agentic process that continuously captures current data
    and feeds it into the historicals as it happens.
    """

    def on_receipt_scanned(self, receipt_data: dict):
        """Receipt ingest adapter triggers this. Immediate write to historicals."""
        for item in receipt_data["items"]:
            price_history.add(item.name, receipt_data.store, item.price, ...)
            spending_history.add(receipt_data.date, item.category, item.price, ...)

    def on_budget_check(self, period: str, category: str, spent: float):
        """Budget adapter triggers this. Keeps budget_history current."""
        ...

    def on_price_observed(self, item: str, store: str, price: float):
        """Any adapter that observes a price writes to historicals."""
        ...
```

**The historical data feeds the predictive models.** With 6 months of price history, the system can predict next month's grocery spending. With a year of budget data, it can identify seasonal spending patterns and pre-adjust budgets.

---

## Part 3: Self-Growing Context Engines

Each specialist maintains a **context engine** — a structured document that captures everything the specialist needs to know to do its job well. The context engine is injected into the specialist's LLM prompts, making it smarter over time.

### What a Context Engine Contains

```markdown
# GrocerySpec Context Engine
# Auto-generated and continuously improved
# Last updated: 2026-04-13T08:00:00Z
# Improvement iteration: 47

## Household Profile
- Family size: 4 (2 adults, 2 kids ages 8 and 11)
- Dietary restrictions: none
- Strong dislikes: Brussels sprouts (Andy), olives (Emma)
- Preferred cuisine rotation: Italian, Mexican, Asian, American
- Budget: $800/month, currently at 68%

## Current State
- Inventory critical: milk (expires tomorrow), bread (2 slices left)
- Upcoming events: birthday party Saturday (need cake ingredients)
- Household state: normal + school_year
- Last shopping trip: April 10 at Aldi ($142.50)

## Learned Patterns
- Mondays: simple dinners (everyone is tired)
- Fridays: pizza night (family tradition, 92% adherence)
- Bulk purchases: chicken, rice, pasta from Costco monthly
- Produce: Aldi > Walmart for price, Lunds for quality when guests

## Price Intelligence
- Chicken breast: $2.49/lb Aldi (up from $1.99), $3.29 Walmart, $4.99 Lunds
- Ground beef: $3.99/lb Aldi, $4.49 Walmart (Costco $3.49 bulk)
- Milk: $2.89/gal Aldi, $3.29 Walmart

## Performance Self-Assessment
- Meal plan acceptance rate: 78% (target: 85%)
- Budget accuracy: ±$45/month (target: ±$30)
- Top rejection reason: "too complex for weeknight" (23% of rejections)
- Improvement action: weight simplicity score higher on weeknights

## Operating Guidelines (self-written, version 12)
1. ALWAYS check inventory before suggesting meals
2. ALWAYS check calendar for time-constrained days
3. Prefer meals with <30 min prep on school nights
4. Default to Aldi prices unless user specifies store
5. When budget is >75%, switch to "budget mode" guidelines
6. DO NOT suggest Thai on weeknights (learned preference, 5 observations)
7. Friday is pizza night — only override for special occasions
8. When guests are coming, increase portions by 1.5x and upgrade ingredients
```

### How Context Engines Self-Improve

```python
class ContextEngine:
    """
    Self-improving prompt context for a specialist.
    Reads from the knowledge lake, historicals, and decision grades
    to continuously refine the context document.
    """

    domain: str
    context_path: str       # data/library/{domain}/context_engine.md

    def rebuild(self) -> str:
        """
        Full rebuild of the context engine. Runs weekly or on-demand.
        Reads from every available source and produces a fresh context doc.
        """
        sections = []

        # 1. Household profile (from semantic memory + preferences)
        sections.append(self._build_household_profile())

        # 2. Current state (from KB facts, inventory, calendar)
        sections.append(self._build_current_state())

        # 3. Learned patterns (from episodic analysis + preference signals)
        sections.append(self._build_learned_patterns())

        # 4. Domain intelligence (from historicals + librarian research)
        sections.append(self._build_domain_intelligence())

        # 5. Performance self-assessment (from decision grades — see Part 4)
        sections.append(self._build_self_assessment())

        # 6. Operating guidelines (from guideline evolution — see Part 4)
        sections.append(self._build_guidelines())

        context_doc = "\n\n".join(sections)
        self._save(context_doc)
        return context_doc

    def patch(self, section: str, update: str):
        """
        Incremental update to a single section.
        More efficient than full rebuild for real-time changes.
        """
        ...

    def inject(self, base_prompt: str) -> str:
        """
        Inject the context engine into an LLM prompt.
        The attention gate (Rec 6 from Memory Architecture) handles
        token budgeting — not everything is injected every time.
        """
        context = self._load()
        gated_context = attention_gate.gate(
            query=base_prompt,
            context=context,
            budget=3000  # tokens
        )
        return f"{base_prompt}\n\n<specialist_context>\n{gated_context}\n</specialist_context>"
```

---

## Part 4: Self-Grading & Guideline Evolution

This is the core self-improvement mechanism. Every decision the system makes gets graded — both immediately (short-term) and over time (long-term). Grades feed into guideline rewrites that make the system better at its job.

### Decision Grading System

```sql
-- Extension to agent_memory decisions table
CREATE TABLE decision_grades (
    id              TEXT PRIMARY KEY,
    decision_id     TEXT NOT NULL,       -- references decisions.id
    
    -- Short-term grade (assigned within 24 hours)
    short_term_grade    TEXT,            -- 'A', 'B', 'C', 'D', 'F'
    short_term_score    REAL,            -- 0.0 - 1.0
    short_term_reason   TEXT,
    short_term_graded_at TEXT,
    
    -- Long-term grade (assigned after 7-30 days)
    long_term_grade     TEXT,
    long_term_score     REAL,
    long_term_reason    TEXT,
    long_term_graded_at TEXT,
    
    -- Meta
    grading_model       TEXT,            -- which LLM graded this
    revised             INTEGER DEFAULT 0 -- has this grade been revised?
);

CREATE INDEX idx_grades_decision ON decision_grades(decision_id);
```

### How Grading Works

```python
class DecisionGrader:
    """
    Grades every decision the system makes, both short-term and long-term.
    Runs on two schedules:
    - Short-term grading: daily (grades yesterday's decisions)
    - Long-term grading: weekly (re-grades decisions from 7-30 days ago)
    """

    def grade_short_term(self, decision: Decision) -> Grade:
        """
        Short-term grade: Was this decision immediately useful?
        
        Signals:
        - User acceptance: Did Andy use/accept the suggestion?
        - Error signal: Did the adapter fail or return low quality?
        - Consistency: Did this align with known preferences?
        - Efficiency: How long did it take? Could it have been faster?
        """
        signals = {
            "accepted": self._check_acceptance(decision),
            "no_error": not decision.outcome == "failure",
            "consistent": self._check_consistency(decision),
            "efficient": decision.duration_ms < self._expected_duration(decision),
        }
        
        score = sum(signals.values()) / len(signals)
        grade = self._score_to_grade(score)
        
        reason = self._explain_grade(decision, signals, grade)
        return Grade(short_term_grade=grade, short_term_score=score,
                     short_term_reason=reason)

    def grade_long_term(self, decision: Decision) -> Grade:
        """
        Long-term grade: Did this decision lead to good outcomes over time?
        
        Signals:
        - Downstream effect: Did subsequent decisions benefit from this one?
        - Pattern formation: Did this contribute to a useful learned pattern?
        - Budget impact: Did spending decisions keep budget on track?
        - Preference alignment: With hindsight, was this what Andy wanted?
        - Regret test: Would the system make the same decision again?
        """
        signals = {
            "downstream_positive": self._check_downstream(decision),
            "pattern_formed": self._check_pattern_contribution(decision),
            "budget_on_track": self._check_budget_impact(decision),
            "no_regret": self._regret_test(decision),
        }
        
        score = sum(v for v in signals.values() if v is not None) / len([v for v in signals.values() if v is not None])
        grade = self._score_to_grade(score)
        
        reason = self._explain_grade(decision, signals, grade)
        return Grade(long_term_grade=grade, long_term_score=score,
                     long_term_reason=reason)
```

### Guideline Evolution

The most powerful part: grades feed into automatic guideline rewrites.

```python
class GuidelineEvolver:
    """
    Reads decision grades and rewrites specialist operating guidelines.
    This is how the system literally writes better instructions for itself.
    """

    def evolve(self, domain: str) -> GuidelineUpdate:
        """
        Runs monthly. Analyzes all graded decisions for a domain
        and produces updated operating guidelines.
        """
        # 1. Pull all decisions with grades for this domain
        decisions = self._get_graded_decisions(domain, lookback_days=30)

        # 2. Cluster by outcome pattern
        patterns = self._cluster_decisions(decisions)
        #   e.g., "weeknight meal suggestions scored low when complex"
        #         "budget warnings scored high when specific"
        #         "Aldi price checks always accurate"

        # 3. Identify guideline candidates
        candidates = []
        for pattern in patterns:
            if pattern.avg_grade < "C" and pattern.count > 3:
                # This is a repeated failure pattern → needs a NEW guideline
                candidates.append(self._draft_corrective_guideline(pattern))
            elif pattern.avg_grade > "A-" and pattern.count > 5:
                # This is a validated success pattern → REINFORCE it
                candidates.append(self._draft_reinforcement_guideline(pattern))

        # 4. Load current guidelines
        current = self._load_guidelines(domain)

        # 5. Ask LLM to merge candidates into current guidelines
        prompt = f"""
        You are updating the operating guidelines for the {domain} specialist.
        
        Current guidelines (version {current.version}):
        {current.text}
        
        Based on analyzing {len(decisions)} decisions over the last 30 days,
        here are proposed changes:
        
        NEW GUIDELINES TO ADD:
        {self._format_new(candidates)}
        
        GUIDELINES TO REINFORCE (working well):
        {self._format_reinforcements(candidates)}
        
        GUIDELINES TO MODIFY OR RETIRE (not working):
        {self._format_modifications(candidates)}
        
        Produce updated guidelines. Keep them concise (max 20 rules).
        Number them. Include a brief reason for each new/changed rule.
        Increment the version number.
        """

        updated = _ask_ollama(prompt)
        
        # 6. Save with provenance
        self._save_guidelines(domain, updated, candidates, decisions)
        
        return GuidelineUpdate(
            domain=domain,
            old_version=current.version,
            new_version=current.version + 1,
            added=len([c for c in candidates if c.type == "new"]),
            modified=len([c for c in candidates if c.type == "modify"]),
            reinforced=len([c for c in candidates if c.type == "reinforce"]),
        )
```

### Example Guideline Evolution Over Time

**Month 1 (v1) — Initial guidelines (human-written):**
```
1. Check inventory before suggesting meals
2. Respect dietary restrictions
3. Stay within monthly budget
```

**Month 2 (v4) — After 120 graded decisions:**
```
1. ALWAYS check inventory before suggesting meals [original, reinforced: 95% acceptance when followed]
2. Respect dietary restrictions [original, reinforced]
3. Stay within monthly budget [original, reinforced]
4. Prefer meals with <30 min prep on weeknights [NEW: weeknight complex meals rejected 67% of the time]
5. Do not suggest Thai cuisine on weeknights [NEW: 5 rejections observed, 0 acceptances]
6. Friday is pizza night unless guests or special occasion [NEW: learned from 8/8 Fridays]
7. When budget >75%, activate budget mode: prioritize Aldi, suggest leftover-based meals [NEW: budget overruns correlated with late-month non-budget-conscious suggestions]
```

**Month 6 (v12) — After 600+ graded decisions:**
```
1. ALWAYS check inventory before suggesting meals [v1, grade: A+, 450 observations]
2. Respect dietary restrictions [v1, grade: A+]
3. Stay within monthly budget [v1, grade: A, modified: monthly budget now dynamically adjusted based on 6-month rolling average]
4. Weeknight meals: <30 min prep, max 8 ingredients [v4, refined: added ingredient count from v7 data]
5. No Thai on weeknights, no Brussels sprouts ever [v4, consolidated: merged two preference rules]
6. Friday = pizza night (override threshold: 2+ guests or holiday) [v4, refined: added holiday exception from December data]
7. Budget mode triggers at 75%: Aldi-first, leftover-priority, bulk protein [v4, refined: added bulk protein from v8 savings analysis]
8. Summer meal plans: +25% snacks, +lunch items, relax complexity rules [NEW v9: summer 2026 data showed weeknight rules too restrictive when kids home]
9. When Costco trip is planned, build meal plan around bulk purchases [NEW v10: Costco-aligned plans saved avg $47/month]
10. Birthday weeks: auto-add cake ingredients, increase "special meal" budget by $30 [NEW v11: calendar integration caught this pattern]
11. Publish weekly meal plan by Sunday 6 PM (Andy reviews during Sunday planning) [NEW v11: acceptance rate +15% when Andy has time to review and modify]
12. Cross-reference allergen warnings with kids' school lunch policies [NEW v12: school notification triggered this safety rule]
```

**This is the system writing its own manual.** Each guideline traces back to specific decisions, specific grades, and specific observations. Nothing is arbitrary. The system can explain why every rule exists and how well it's working.

---

## Part 5: The Decision Lifecycle — Full Tracking From Birth to Grade

Every decision flows through a complete lifecycle:

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌───────────┐
│ DECIDE  │────▶│ EXECUTE  │────▶│ OBSERVE  │────▶│ GRADE     │
│         │     │          │     │          │     │ (short)   │
│ Router  │     │ Adapter  │     │ Track    │     │           │
│ picks   │     │ runs the │     │ outcome  │     │ Within    │
│ adapter │     │ action   │     │ signals  │     │ 24 hours  │
└─────────┘     └──────────┘     └──────────┘     └─────┬─────┘
                                                        │
                                                        ▼
                                               ┌───────────────┐
                                               │ GRADE (long)  │
                                               │               │
                                               │ After 7-30    │
                                               │ days: was     │
                                               │ this the      │
                                               │ right call?   │
                                               └───────┬───────┘
                                                       │
                                               ┌───────▼───────┐
                                               │  AGGREGATE    │
                                               │               │
                                               │ Monthly:      │
                                               │ cluster by    │
                                               │ pattern,      │
                                               │ identify      │
                                               │ trends        │
                                               └───────┬───────┘
                                                       │
                                               ┌───────▼───────┐
                                               │  EVOLVE       │
                                               │               │
                                               │ Rewrite       │
                                               │ guidelines    │
                                               │ Update        │
                                               │ context       │
                                               │ engine        │
                                               └───────────────┘
```

### Grading Metrics by Domain

| Domain | Short-Term Signals | Long-Term Signals |
|--------|-------------------|-------------------|
| **Grocery** | Meal plan accepted? Recipe used? Items purchased? | Monthly budget variance, family satisfaction (inferred), waste reduction |
| **Finance** | Budget warning acted on? Spending adjusted? | Month-end accuracy, savings rate trend, budget adherence over quarter |
| **Home** | Maintenance done on time? Repair cost accurate? | Equipment failure rate, annual maintenance cost trend, emergency repairs avoided |
| **Investing** | Market call directionally correct? Risk assessment valid? | Portfolio performance vs. benchmark over 30/90/365 days |
| **Calendar** | Conflict detected in time? Reminder useful? | Schedule adherence, double-booking rate, family time protected |

---

## Part 6: The Cross-Wing Research Network

Wings don't operate in isolation. The shared catalog enables cross-pollination:

### Research Requests Across Wings

```python
# GrocerySpec realizes it doesn't understand food price inflation well
research_queue.add(
    requesting_agent="grocery_specialist",
    topic="food price inflation drivers and household mitigation strategies",
    reason="Price predictions consistently off by >15%. Need better economic model.",
    priority="high"
)

# FinanceSpec's librarian picks this up because it overlaps economics
# → researches CPI food components, USDA projections, hedging strategies
# → adds findings to both finance and grocery wings
# → grocery specialist's context engine absorbs the new knowledge
# → price predictions improve

# Similarly:
# HomeSpec asks DevSpec librarian: "best open-source home automation frameworks?"
# InvestorSpec asks NewsSpec librarian: "reliable sources for market sentiment data?"
# HealthSpec asks GrocerySpec librarian: "nutritional profiles for budget-friendly proteins?"
```

### Weekly Library Report

Added to the daily brief system:

```
LIBRARY OF ALEXANDRIA — WEEKLY REPORT

New resources cataloged: 23
  Grocery: 8 (3 recipes, 2 price datasets, 3 couponing guides)
  Finance: 5 (2 tax guides, 1 budgeting paper, 2 savings strategies)
  Home: 4 (2 HVAC guides, 1 plumbing tutorial, 1 energy audit tool)
  Investing: 4 (2 portfolio papers, 1 risk model repo, 1 Fed analysis)
  Dev/Engineering: 2 (1 LLM agent paper, 1 Ollama optimization guide)

Research requests fulfilled: 3/5
  ✓ Food price inflation model (requested by GrocerySpec)
  ✓ Home insulation ROI calculator (requested by HomeSpec)
  ✓ React component testing patterns (requested by DevTeamSpec)
  ⏳ Tax-loss harvesting for retirement accounts (assigned to FinanceSpec librarian)
  ⏳ Sleep quality research for school-age children (assigned to HealthSpec librarian)

Guideline evolutions this week: 2
  Grocery guidelines v12 → v13 (added rule: cross-ref school lunch allergens)
  Finance guidelines v8 → v9 (modified: budget buffer increased to 10%)

Total library size: 847 resources across 7 wings
Oldest unverified resource: "USDA seasonal produce guide 2025" (142 days)
```

---

## Part 7: Implementation Order

| Priority | Component | Why First |
|----------|-----------|-----------|
| 1st | Decision grading table + short-term grader | Start collecting grade data NOW — everything else needs it |
| 2nd | Library catalog schema + disk structure | Foundation for all wing storage |
| 3rd | GrocerySpec Research Librarian | Most data, most decisions, fastest feedback loop |
| 4th | Context engine for GrocerySpec | Proof of concept: self-improving context |
| 5th | Guideline Evolver (grocery domain) | Close the loop: grades → guidelines → better decisions |
| 6th | Financial Historical Builder | Start backfilling — the longer the history, the better the predictions |
| 7th | Current Data Agents (receipt + price capture) | Feed the historicals from live data |
| 8th | Long-term grading system | Requires 30+ days of short-term grades to work |
| 9th | Cross-wing research requests | Requires 2+ wings operational |
| 10th | Weekly library report | Polish — needs all wings contributing |

---

## The Compounding Effect

After 6 months of operation:
- The library has thousands of curated resources, each domain deeply informed
- The historicals have 6 months of spending, prices, schedules, and maintenance data
- The context engines have been rebuilt 24+ times, each iteration sharper
- The guidelines have evolved through 6+ versions per specialist
- The grading system has evaluated thousands of decisions
- The system knows what works, what doesn't, and why

After a year:
- Price prediction models are calibrated on 365 days of local data
- Budget forecasts account for seasonal patterns (holidays, summer, school year)
- Maintenance predictions are based on actual usage, not manufacturer estimates
- Meal planning reflects learned family preferences across all four seasons
- Investment analysis draws on a curated library of financial research
- The guidelines are battle-tested through hundreds of self-improvement cycles

**This is not a static system. It's a system that gets measurably better every single day, and it can prove it with data.**
