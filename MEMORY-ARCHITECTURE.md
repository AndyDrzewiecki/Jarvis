# Jarvis Memory Architecture — Brain-Inspired Redesign

**Author:** Andy + Claude | **Date:** 2026-04-13 | **Status:** Design
**Research basis:** CLS theory, A-MEM (NeurIPS 2025), MemoryOS (EMNLP 2025), HEMA, MAGMA

---

## Diagnosis: Where the Current Memory System Falls Short

Jarvis today has **six independent memory stores** that don't talk to each other:

```
┌──────────────────────────────────────────────────────────────────────┐
│                    CURRENT STATE: MEMORY SILOS                       │
│                                                                      │
│  memory.py          agent_memory.py      knowledge_base.py          │
│  ┌────────────┐     ┌──────────────┐     ┌───────────────┐         │
│  │ 100 msgs   │     │ 478 decisions│     │ ChromaDB      │         │
│  │ JSON file  │     │ SQLite       │     │ (barely used) │         │
│  │ FIFO drop  │     │ append-only  │     │ 6 categories  │         │
│  └──────┬─────┘     └──────┬───────┘     └───────┬───────┘         │
│         │                  │                     │                   │
│    reads: core.py     reads: ??? (nobody)   reads: ??? (nobody)    │
│    writes: core.py    writes: every route   writes: nothing yet    │
│                                                                      │
│  preferences.py       ambient.py            entities.json           │
│  ┌────────────┐     ┌──────────────┐     ┌───────────────┐         │
│  │ 18 fields  │     │ time+weather │     │ last 100      │         │
│  │ JSON file  │     │ JSON cache   │     │ JSON file     │         │
│  │ static     │     │ 1hr TTL      │     │ flat list     │         │
│  └──────┬─────┘     └──────┬───────┘     └───────┬───────┘         │
│         │                  │                     │                   │
│    reads: adapters    reads: core.py        reads: core.py          │
│    writes: manual     writes: weather       writes: every chat      │
│                                                                      │
│  PROBLEMS:                                                           │
│  1. No cross-store communication                                     │
│  2. agent_memory is write-only — 478 decisions, zero learning        │
│  3. Conversations are dropped after 100 messages — no consolidation  │
│  4. ChromaDB is built but nothing feeds it                           │
│  5. Entities are extracted but never structured or deduplicated       │
│  6. No feedback loops anywhere                                       │
│  7. No memory hierarchy (everything is flat)                         │
│  8. Each store has different I/O patterns — no unified bus            │
└──────────────────────────────────────────────────────────────────────┘
```

The human brain solves this with three interacting systems: fast episodic encoding (hippocampus), slow semantic generalization (neocortex), and procedural automation (basal ganglia/cerebellum). Recent AI research has formalized these ideas into implementable architectures. Here are 10 recommendations to rebuild Jarvis's memory system on these principles.

---

## Recommendation 1: Three-Tier Memory Hierarchy (Inspired by MemoryOS + CLS Theory)

**The brain analogy:** Sensory input → working memory (prefrontal cortex, seconds) → episodic memory (hippocampus, hours-days) → semantic memory (neocortex, permanent). Information flows down this hierarchy through a process of consolidation and compression.

**What to build:**

```
┌─────────────────────────────────────────────────────────────────────┐
│                    THREE-TIER MEMORY HIERARCHY                       │
│                                                                      │
│  TIER 1: WORKING MEMORY (replaces memory.py)                        │
│  ┌─────────────────────────────────────────────┐                    │
│  │ Current conversation + active task context    │                    │
│  │ In-memory (Python dict), no persistence       │                    │
│  │ Capacity: last ~20 messages + current adapter │                    │
│  │ Lifetime: single session                      │                    │
│  │ I/O: synchronous, sub-millisecond             │                    │
│  └──────────────────────┬──────────────────────┘                    │
│                         │ consolidation (every N messages)           │
│                         ▼                                            │
│  TIER 2: EPISODIC MEMORY (new — replaces memory.json + entities)    │
│  ┌─────────────────────────────────────────────┐                    │
│  │ Complete interaction episodes with metadata   │                    │
│  │ SQLite (data/episodes.db)                     │                    │
│  │ Each episode: messages + entities + decisions  │                    │
│  │ Lifetime: weeks-months, subject to decay       │                    │
│  │ I/O: SQLite read/write, ~1ms                  │                    │
│  └──────────────────────┬──────────────────────┘                    │
│                         │ consolidation ("sleep" cycle, nightly)     │
│                         ▼                                            │
│  TIER 3: SEMANTIC MEMORY (enhanced knowledge_base.py + facts.db)    │
│  ┌─────────────────────────────────────────────┐                    │
│  │ Generalized knowledge, patterns, preferences  │                    │
│  │ ChromaDB + SQLite (data/semantic.db)          │                    │
│  │ Domain-structured, deduplicated, high-confidence│                   │
│  │ Lifetime: permanent (with confidence decay)    │                    │
│  │ I/O: vector search ~10ms, SQL ~1ms            │                    │
│  └─────────────────────────────────────────────┘                    │
│                                                                      │
│  BONUS: PROCEDURAL MEMORY (new layer)                                │
│  ┌─────────────────────────────────────────────┐                    │
│  │ Learned action sequences, prompt templates    │                    │
│  │ "When X happens, do Y" — compiled from        │                    │
│  │ repeated episodic patterns                    │                    │
│  │ Used to bypass LLM routing for known patterns │                    │
│  └─────────────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
```

**Why three tiers instead of two:** MemoryOS (EMNLP 2025) showed that a three-tier system with explicit mid-term memory achieves 49% better F1 on long-context tasks than flat memory. The episodic tier is the key innovation — it's where raw experiences are stored before being generalized. Without it, you either lose detail (no raw storage) or never generalize (keep everything raw forever).

**Schema for Tier 2 (episodes.db):**

```sql
CREATE TABLE episodes (
    id              TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    summary         TEXT,               -- LLM-generated one-line summary
    domain          TEXT,               -- primary domain (grocery, finance, etc.)
    satisfaction    REAL,               -- inferred: did this episode end well?
    consolidated    INTEGER DEFAULT 0   -- 0=raw, 1=consolidated into semantic
);

CREATE TABLE episode_messages (
    id              TEXT PRIMARY KEY,
    episode_id      TEXT NOT NULL REFERENCES episodes(id),
    role            TEXT NOT NULL,       -- user, assistant, system
    content         TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    adapter         TEXT,
    entities        TEXT                 -- JSON: extracted entities for this message
);

CREATE TABLE episode_decisions (
    id              TEXT PRIMARY KEY,
    episode_id      TEXT NOT NULL REFERENCES episodes(id),
    decision_id     TEXT NOT NULL        -- references agent_memory decisions table
);
```

**I/O pattern:**
- Write: Every message → working memory (instant) + episode_messages (async)
- Read (hot path): Working memory only (last 20 messages)
- Read (recall): Semantic search over episode summaries → pull full episode if relevant
- Consolidation: Nightly batch → extract patterns → write to semantic tier → mark consolidated

---

## Recommendation 2: Memory Consolidation Engine ("Sleep Cycle")

**The brain analogy:** During sleep, the hippocampus "replays" the day's experiences to the neocortex in compressed, time-accelerated form. The neocortex extracts statistical patterns and integrates them into its existing knowledge structure. This is why you sometimes solve problems in your sleep — the consolidation process finds connections you missed while awake.

**What to build:** A scheduled process (runs nightly or during low-activity periods) that:

1. **Replays** recent episodes from Tier 2
2. **Extracts** recurring patterns, preferences, and facts
3. **Writes** generalized knowledge to Tier 3 (semantic memory)
4. **Marks** consolidated episodes as processed
5. **Prunes** low-value episodes that contributed nothing new

```python
class ConsolidationEngine:
    """Nightly 'sleep cycle' that consolidates episodic → semantic memory."""

    def run(self) -> ConsolidationReport:
        # Phase 1: Gather unconsolidated episodes
        episodes = episodic_store.get_unconsolidated(limit=50)

        # Phase 2: Replay & extract (LLM-powered)
        for episode in episodes:
            messages = episodic_store.get_messages(episode.id)
            decisions = episodic_store.get_decisions(episode.id)

            # Ask LLM to extract generalizable knowledge
            extractions = self._extract_knowledge(messages, decisions)
            # extractions might include:
            #   - New fact: "Andy prefers Aldi for bulk items"
            #   - Updated preference: "Reject Thai on weeknights" (3rd observation)
            #   - Causal link: "Budget queries spike after Costco trips"
            #   - Procedural pattern: "When asked about dinner, check inventory first"

            # Phase 3: Merge into semantic memory
            for extraction in extractions:
                existing = semantic_store.find_similar(extraction, threshold=0.85)
                if existing:
                    # Strengthen existing knowledge (increase confidence, add evidence)
                    semantic_store.reinforce(existing.id, extraction)
                else:
                    # New knowledge
                    semantic_store.add(extraction)

            # Phase 4: Mark episode as consolidated
            episodic_store.mark_consolidated(episode.id)

        # Phase 5: Prune low-value episodes (older than 30 days, low satisfaction)
        pruned = episodic_store.prune(
            older_than_days=30,
            min_satisfaction=0.3,
            keep_if_not_consolidated=True  # never prune before consolidation
        )

        return ConsolidationReport(
            episodes_processed=len(episodes),
            new_knowledge=new_count,
            reinforced=reinforced_count,
            pruned=pruned
        )
```

**Key insight from CLS theory (McClelland et al., 1995; updated 2025):** The reason the brain uses two complementary systems is the **stability-plasticity dilemma**. A single system that learns fast (plastic) will catastrophically forget old knowledge. A system that preserves old knowledge (stable) will learn slowly. The two-system architecture solves this: hippocampus learns fast, replays to neocortex slowly, neocortex integrates without forgetting.

For Jarvis, this means: working memory + episodes can absorb rapid input without corrupting the semantic knowledge base. Consolidation happens in a controlled batch process where the LLM has time to reason about what's genuinely new vs. what's noise.

**Schedule integration:** Add to `scheduler.py`:

```python
_scheduler.add_job(
    _run_consolidation,
    trigger="cron",
    hour=3,          # 3 AM — low activity period
    minute=0,
    id="memory_consolidation",
    replace_existing=True,
)
```

---

## Recommendation 3: Unified Memory Bus — One I/O Interface for All Stores

**The brain analogy:** The thalamus acts as a central relay station — almost all sensory input and memory retrieval passes through it. It doesn't store information itself, but it routes queries and writes to the correct brain region, and it can broadcast information to multiple regions simultaneously.

**The current problem:** Each memory store has its own read/write API. `core.py` reads from `memory.py`. `agent_memory.py` writes independently. `knowledge_base.py` sits idle. Nothing coordinates.

**What to build:**

```python
class MemoryBus:
    """
    Unified I/O interface for all memory stores.
    Every memory operation goes through the bus.
    The bus handles routing, broadcasting, and cross-store synchronization.
    """

    def __init__(self):
        self.working = WorkingMemory()           # Tier 1
        self.episodic = EpisodicStore()          # Tier 2
        self.semantic = SemanticStore()           # Tier 3
        self.procedural = ProceduralStore()      # Learned patterns
        self.audit = AgentMemoryStore()          # Decision log (existing)
        self._hooks: list[MemoryHook] = []       # Event listeners

    # ── WRITE operations ─────────────────────────────────────────────

    def record_message(self, role: str, content: str, adapter: str = None) -> str:
        """Record a message. Writes to working + episodic simultaneously."""
        msg_id = self.working.add(role, content, adapter)
        self.episodic.add_message(self.working.current_episode_id, role, content, adapter)
        self._emit("message_recorded", msg_id=msg_id, role=role, content=content)
        return msg_id

    def record_decision(self, agent: str, capability: str, **kwargs) -> str:
        """Record a routing/adapter decision. Writes to audit + links to episode."""
        decision_id = self.audit.log_decision(agent, capability, **kwargs)
        self.episodic.link_decision(self.working.current_episode_id, decision_id)
        self._emit("decision_recorded", decision_id=decision_id, agent=agent)
        return decision_id

    def store_fact(self, domain: str, fact_type: str, content: str, **kwargs) -> str:
        """Write a structured or unstructured fact to semantic memory."""
        fact_id = self.semantic.add(domain, fact_type, content, **kwargs)
        self._emit("fact_stored", fact_id=fact_id, domain=domain)
        return fact_id

    def learn_procedure(self, trigger: str, action_sequence: list, **kwargs) -> str:
        """Record a learned procedure from repeated patterns."""
        proc_id = self.procedural.add(trigger, action_sequence, **kwargs)
        self._emit("procedure_learned", proc_id=proc_id)
        return proc_id

    # ── READ operations ──────────────────────────────────────────────

    def recall(self, query: str, context: dict = None) -> MemoryRecall:
        """
        Unified recall — searches ALL tiers and returns ranked results.
        Like the brain: you don't consciously choose which memory system
        to query. You just "remember" and the relevant information surfaces.
        """
        results = MemoryRecall()

        # 1. Check working memory (instant, highest priority)
        results.working = self.working.search(query)

        # 2. Check procedural memory (do we have a compiled response for this?)
        results.procedural = self.procedural.match(query)

        # 3. Check semantic memory (generalized knowledge)
        results.semantic = self.semantic.search(query, context=context)

        # 4. Check episodic memory (specific past events)
        results.episodic = self.episodic.search(query, limit=5)

        # 5. Rank and merge (recency + relevance + confidence)
        results.merged = self._rank_and_merge(results)

        return results

    def context_for_prompt(self, user_message: str) -> str:
        """
        Build the memory context block that gets injected into LLM prompts.
        This replaces the scattered context injection in core.py.
        """
        recall = self.recall(user_message)

        sections = []
        if recall.procedural:
            sections.append(f"[KNOWN PATTERN] {recall.procedural.description}")
        if recall.semantic:
            facts = "\n".join(f"- {f.summary}" for f in recall.semantic[:5])
            sections.append(f"[KNOWN FACTS]\n{facts}")
        if recall.episodic:
            eps = "\n".join(f"- {e.summary} ({e.started_at})" for e in recall.episodic[:3])
            sections.append(f"[RELEVANT PAST CONVERSATIONS]\n{eps}")

        return "\n\n".join(sections) if sections else ""

    # ── HOOKS (event system for cross-store reactions) ────────────────

    def register_hook(self, hook: MemoryHook):
        """Register a listener for memory events."""
        self._hooks.append(hook)

    def _emit(self, event: str, **kwargs):
        for hook in self._hooks:
            try:
                hook.on_event(event, **kwargs)
            except Exception:
                pass
```

**Why hooks matter:** The hook system is how memory stores react to each other. When a new fact is stored in semantic memory, a hook can check if any procedural patterns need updating. When an episode ends with low satisfaction, a hook can flag it for priority consolidation. This is how the system becomes self-organizing rather than requiring explicit cross-store wiring.

**I/O performance budget:**

| Operation | Target Latency | Implementation |
|-----------|---------------|----------------|
| Working memory read/write | <1ms | Python dict, in-memory |
| Episodic message write | <5ms | SQLite WAL mode, async |
| Semantic search | <50ms | ChromaDB vector search |
| Semantic SQL query | <5ms | SQLite indexed |
| Full recall (all tiers) | <100ms | Parallel queries |
| Consolidation (per episode) | ~2s | LLM call, batch only |

---

## Recommendation 4: Zettelkasten-Inspired Knowledge Linking (Inspired by A-MEM)

**Research basis:** A-MEM (accepted NeurIPS 2025) showed that applying the Zettelkasten method to AI memory — where every note is atomic, has rich metadata, and is dynamically linked to related notes — outperforms flat memory systems across all tested foundation models.

**The core idea:** Every piece of knowledge in Jarvis's semantic store is a "note" that contains not just content but also:
- Keywords and tags (for fast filtering)
- Dense embedding (for semantic search)
- **Dynamic links** to related notes
- A context description (why this note matters)

**The key innovation from A-MEM that Jarvis should adopt:** When a new note is added, the system doesn't just store it — it:

1. Searches for related existing notes
2. Creates bidirectional links with relationship types
3. **Evolves existing notes** — if new information changes the context of an old note, the old note's metadata gets updated

```sql
-- Extension to the semantic store
CREATE TABLE knowledge_notes (
    id              TEXT PRIMARY KEY,
    content         TEXT NOT NULL,          -- the actual knowledge
    context_desc    TEXT NOT NULL,          -- why this matters, when to recall it
    keywords        TEXT NOT NULL,          -- comma-separated, for fast filtering
    domain          TEXT NOT NULL,
    source_agent    TEXT NOT NULL,
    confidence      REAL DEFAULT 0.8,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    access_count    INTEGER DEFAULT 0,      -- how often this note is recalled
    last_accessed   TEXT,
    embedding_id    TEXT                    -- reference to ChromaDB vector
);

CREATE TABLE knowledge_links (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES knowledge_notes(id),
    target_id       TEXT NOT NULL REFERENCES knowledge_notes(id),
    relationship    TEXT NOT NULL,          -- 'supports', 'contradicts', 'extends',
                                           -- 'caused_by', 'related_to', 'supersedes'
    strength        REAL DEFAULT 0.5,       -- strengthens with repeated co-access
    created_at      TEXT NOT NULL,
    evidence        TEXT                    -- why this link exists
);

-- Index for graph traversal
CREATE INDEX idx_links_source ON knowledge_links(source_id);
CREATE INDEX idx_links_target ON knowledge_links(target_id);
```

**Example of knowledge evolution:**

```
Day 1: GrocerySpec adds note: "Aldi chicken breast: $1.99/lb"
        → Links to: "Preferred stores" (related_to), "Protein prices" (extends)

Day 5: GrocerySpec adds note: "Aldi chicken breast: $2.49/lb"
        → A-MEM evolution triggers:
          1. Old note updated: context_desc += "Price was $1.99 as of Day 1"
          2. New note links to old note with relationship='supersedes'
          3. Causal link created: "Aldi chicken price increasing" (new pattern note)
          4. FinanceSpec's budget note updated: "Chicken price trend: +25% in 5 days"
```

**This is what makes memory alive.** Static storage records facts. Zettelkasten linking makes knowledge self-organizing — new information doesn't just accumulate, it restructures what's already known.

---

## Recommendation 5: Procedural Memory — Compiled Action Patterns

**The brain analogy:** When you first learn to drive, every action requires conscious thought (episodic + working memory). After thousands of repetitions, driving becomes procedural — the basal ganglia handles it without conscious involvement. This frees up working memory and prefrontal cortex for higher-order thinking.

**For Jarvis:** After the 50th time someone asks "what's for dinner?" and the system goes through the same routing → grocery adapter → inventory check → meal suggestion pipeline, that sequence should be compiled into a procedural memory that skips the LLM routing entirely.

```python
class ProceduralStore:
    """
    Stores learned action patterns compiled from repeated episodic patterns.
    These bypass the LLM router for known interaction types, saving ~2 seconds per call.
    """

    def match(self, user_message: str) -> Optional[Procedure]:
        """
        Check if this message matches a known procedural pattern.
        Returns a compiled action sequence, or None if no match.
        """
        # Fast keyword/embedding match against known triggers
        candidates = self._find_candidates(user_message)
        for candidate in candidates:
            if candidate.confidence > 0.9 and candidate.execution_count > 5:
                return candidate
        return None

    def compile_from_episodes(self, pattern: list[Episode]) -> Procedure:
        """
        Given a set of similar episodes, extract the common action sequence
        and compile it into a procedure.
        """
        # LLM analyzes the episodes and extracts the pattern
        # e.g., "User asks about dinner → check inventory → get meal plan → respond"
        ...
```

**Schema:**

```sql
CREATE TABLE procedures (
    id                  TEXT PRIMARY KEY,
    trigger_pattern     TEXT NOT NULL,       -- regex or semantic description
    trigger_embedding   BLOB,               -- dense embedding for fast matching
    action_sequence     TEXT NOT NULL,       -- JSON: ordered list of adapter calls
    expected_params     TEXT,               -- JSON: how to extract params from message
    confidence          REAL DEFAULT 0.5,
    execution_count     INTEGER DEFAULT 0,
    success_rate        REAL DEFAULT 1.0,
    compiled_from       TEXT,               -- JSON: list of episode IDs that formed this
    created_at          TEXT NOT NULL,
    last_used           TEXT
);
```

**When to compile:** During the consolidation "sleep cycle," the consolidation engine looks for episodes with identical routing patterns:

```python
# In ConsolidationEngine.run():
# Phase 2b: Detect procedural patterns
routing_patterns = episodic_store.group_by_routing_pattern(min_count=5)
for pattern, episodes in routing_patterns.items():
    if procedural_store.has_pattern(pattern):
        procedural_store.reinforce(pattern)
    else:
        procedure = procedural_store.compile_from_episodes(episodes)
        memory_bus.learn_procedure(procedure.trigger, procedure.action_sequence)
```

**Performance impact:** For a household assistant, maybe 60-70% of daily queries fall into well-known patterns. If those skip the LLM router entirely (saving 1-3 seconds of Ollama inference each), the system feels dramatically more responsive for common requests while still being flexible for novel ones.

**Safety:** Procedures have a confidence threshold (0.9) and minimum execution count (5) before they're used. If a procedure starts failing (success_rate drops below 0.8), it's automatically decompiled back to explicit routing, and the episodes that triggered the failure are flagged for analysis.

---

## Recommendation 6: Attention Gating — Relevance-Weighted Memory Injection

**The brain analogy:** The prefrontal cortex doesn't dump everything it knows into every decision. It applies **selective attention** — filtering which memories are relevant to the current task and suppressing irrelevant ones. The reticular activating system (RAS) further gates what even reaches conscious awareness.

**The current problem in core.py:** The routing prompt includes a fixed-format context block (ambient + last 5 messages + entities). There's no relevance filtering. Every prompt gets the same context structure regardless of whether it's about grocery shopping or a software question.

**What to build:**

```python
class AttentionGate:
    """
    Dynamically selects which memories to inject into each LLM prompt.
    Prevents context window pollution and reduces hallucination from
    irrelevant context.
    """

    def gate(self, query: str, recall: MemoryRecall, budget: int = 2000) -> str:
        """
        Given a recall result and a token budget, select the most relevant
        memories and format them for prompt injection.
        
        Uses a relevance score that combines:
        - Semantic similarity to the query
        - Recency (recent memories are more relevant)
        - Access frequency (frequently useful memories are likely useful again)
        - Domain alignment (match query domain to memory domain)
        - Surprise value (memories that contradict expectations are high-value)
        """
        scored_items = []

        for item in recall.all_items():
            score = (
                0.35 * item.semantic_similarity +   # from vector search
                0.20 * self._recency_score(item) +
                0.15 * self._frequency_score(item) +
                0.15 * self._domain_alignment(query, item) +
                0.15 * self._surprise_value(item)
            )
            scored_items.append((score, item))

        # Sort by score, pack into budget
        scored_items.sort(key=lambda x: x[0], reverse=True)
        context_parts = []
        tokens_used = 0

        for score, item in scored_items:
            item_tokens = len(item.content.split()) * 1.3  # rough estimate
            if tokens_used + item_tokens > budget:
                break
            context_parts.append(self._format_item(item, score))
            tokens_used += item_tokens

        return "\n".join(context_parts)

    def _surprise_value(self, item) -> float:
        """
        High surprise = contradicts what would be expected.
        Example: chicken price suddenly doubled → high surprise → must be included.
        Calculated as: 1 - (how well this fact fits the current semantic cluster).
        """
        ...
```

**Why "surprise" matters:** Cognitive science shows that the brain preferentially encodes and recalls surprising events (prediction error theory). For Jarvis, this means: if chicken has been $1.99 for 3 months and suddenly it's $3.49, that's high-surprise and should definitely make it into the context window — even if it has lower semantic similarity to the current query than other grocery facts.

---

## Recommendation 7: Memory Provenance Chain — Full Audit Trail for Every Fact

**What it is:** Every piece of knowledge in Jarvis traces back to its origin through an unbroken provenance chain: which source provided the raw data, which LLM processed it, what prompt was used, what confidence was assigned, and every subsequent transformation.

**Why it matters for self-improving systems:** When the metacognitive supervisor detects a bad recommendation, it needs to trace back: "Why did Jarvis think chicken was $1.99 when it was actually $3.49?" The provenance chain reveals: "The grocery specialist scraped that price 12 days ago. The confidence should have decayed to 0.4 but the decay function wasn't applied because the 'price' half-life was incorrectly set to 30 days instead of 3."

**Without provenance, debugging self-improving systems is impossible.** You can see what the system knows, but not why it knows it or how it got there.

```sql
CREATE TABLE provenance (
    id              TEXT PRIMARY KEY,
    fact_id         TEXT NOT NULL,          -- references knowledge_notes.id
    event_type      TEXT NOT NULL,          -- 'created', 'updated', 'reinforced',
                                           -- 'decayed', 'superseded', 'linked'
    timestamp       TEXT NOT NULL,
    source_type     TEXT NOT NULL,          -- 'api', 'scrape', 'user_input', 'llm_inference',
                                           -- 'consolidation', 'specialist_loop'
    source_detail   TEXT,                  -- API URL, specialist name, episode ID, etc.
    model_used      TEXT,                  -- which Ollama model processed this
    prompt_hash     TEXT,                  -- hash of the prompt used (for reproducibility)
    input_summary   TEXT,                  -- what raw data went in (truncated)
    confidence_at_event REAL,              -- confidence at this point in time
    agent           TEXT                   -- which agent/specialist performed this action
);

CREATE INDEX idx_provenance_fact ON provenance(fact_id);
CREATE INDEX idx_provenance_time ON provenance(timestamp);
```

**Provenance enables three critical capabilities:**

1. **Blame attribution:** When a recommendation is wrong, trace it back to the specific data source and processing step that introduced the error.
2. **Confidence calibration:** Compare predicted confidence at storage time with actual outcome. Over time, learn which sources and which models produce well-calibrated confidence scores.
3. **Reproducibility:** Given the prompt hash and input summary, you can re-run any knowledge extraction step to verify it. This is essential for a system that improves its own code (#5 from the previous doc).

---

## Recommendation 8: Emotional Valence Tagging — Memory That Knows What Matters

**The brain analogy:** The amygdala tags memories with emotional valence — this is why you remember your wedding day but not what you had for lunch on a random Tuesday. Emotionally tagged memories are prioritized for encoding, consolidation, and recall. They're also more resistant to decay.

**For Jarvis:** Not every interaction is equally important. The conversation where Andy discovered his grocery budget was blown is more significant than the one where he asked about the weather. The episode where a specialist caught a billing error is more valuable than a routine price check.

**Implementation:** Add a `significance` score to episodes and facts, computed from multiple signals:

```python
class SignificanceScorer:
    """
    Computes how significant a memory is — higher significance means
    stronger encoding, slower decay, and priority in recall.
    """

    def score_episode(self, episode: Episode) -> float:
        signals = {
            "novelty":      self._novelty(episode),        # how different from recent episodes
            "user_emphasis": self._emphasis(episode),       # exclamation marks, "important", "remember"
            "consequence":   self._consequence(episode),    # did this lead to action? budget change?
            "error_signal":  self._error(episode),          # did something go wrong? correction needed?
            "cross_domain":  self._cross_domain(episode),   # involved multiple domains? (more complex = more significant)
        }
        
        weights = {
            "novelty": 0.25,
            "user_emphasis": 0.20,
            "consequence": 0.25,
            "error_signal": 0.20,
            "cross_domain": 0.10,
        }
        
        return sum(signals[k] * weights[k] for k in signals)
```

**How significance affects the system:**

- **Encoding:** High-significance episodes get richer metadata extraction during consolidation
- **Decay:** High-significance facts decay at half the normal rate
- **Recall:** Significance acts as a multiplier in the attention gate's relevance score
- **Pruning:** Low-significance, old episodes are pruned first during the sleep cycle
- **Learning:** The metacognitive supervisor preferentially reviews high-significance failures

**This is the mechanism by which Jarvis learns what matters to your family.** Over time, the significance model reflects your household's actual priorities — not what the system was programmed to think matters, but what empirically drives consequential decisions.

---

## Recommendation 9: Cross-Agent Memory Substrate — Shared Blackboard Architecture

**The brain analogy:** Different brain regions (visual cortex, auditory cortex, language centers, motor cortex) don't share information through point-to-point connections. They write to and read from a shared workspace (global workspace theory, Baars 1988). Information that enters this workspace becomes "conscious" — available to all cognitive processes simultaneously.

**For Jarvis:** The specialists (grocery, finance, home, etc.) need shared memory, but they shouldn't be tightly coupled. The blackboard pattern solves this: a shared data structure that all agents can read and write, with the MemoryBus coordinating access and notifying relevant agents when something changes.

```python
class SharedBlackboard:
    """
    Global workspace for cross-specialist communication.
    Any specialist can post; all specialists can read.
    The MemoryBus distributes notifications via hooks.
    """

    def post(self, agent: str, topic: str, content: dict, 
             urgency: str = "normal") -> str:
        """
        Post to the shared blackboard. All registered hooks are notified.
        
        urgency levels:
        - 'low': processed in next scheduled cycle
        - 'normal': processed within 30 minutes
        - 'high': immediate notification to relevant specialists
        - 'critical': immediate notification to ALL specialists + Andy
        """
        entry_id = self._store(agent, topic, content, urgency)
        self.memory_bus._emit("blackboard_post", 
                              entry_id=entry_id,
                              agent=agent, 
                              topic=topic,
                              urgency=urgency)
        return entry_id

    def read(self, topics: list[str] = None, since: str = None,
             agents: list[str] = None) -> list[dict]:
        """Read blackboard entries, optionally filtered."""
        ...

    def subscribe(self, agent: str, topics: list[str]):
        """Register interest in specific topics for push notifications."""
        ...
```

**Example cross-specialist flow via blackboard:**

```
CalendarSpec posts:
  topic: "schedule_conflict"
  content: {"date": "2026-04-15", "conflicts": ["soccer 4pm", "dentist 4pm"]}
  urgency: "high"
      │
      ├── GrocerySpec reads → adjusts Tuesday meal plan 
      │   (simple dinner since schedule is chaotic)
      │
      ├── HomeSpec reads → skips Tuesday maintenance reminder
      │   (family will be busy)
      │
      └── NotificationSpec reads → alerts Andy about the conflict
          with a suggested resolution
```

**The blackboard is different from the Knowledge Lake.** The KB stores durable knowledge (facts, preferences, patterns). The blackboard stores transient signals (events, alerts, requests). Think of the KB as long-term memory and the blackboard as the "internal monologue" that specialists use to coordinate in real time.

---

## Recommendation 10: Memory Introspection API — Jarvis Can Explain Its Own Memory

**What it is:** An API (and natural language interface) that lets Andy query the memory system directly:

- "What do you know about our grocery spending?"
- "Why did you suggest Thai food last Tuesday?"
- "What have you learned about me in the last month?"
- "What are you least confident about?"
- "Show me your memory graph for 'home maintenance'"

**Why this matters for a self-improving system:** Transparency is the foundation of trust. If Jarvis is making autonomous decisions based on learned patterns, Andy needs to be able to inspect and correct those patterns. Without introspection, the system becomes a black box that's learning things you can't see or challenge.

```python
class MemoryIntrospection:
    """Natural language interface to the memory system."""

    def explain_recommendation(self, recommendation_id: str) -> str:
        """
        Trace a recommendation back through the memory system.
        Returns a human-readable explanation of WHY this was recommended.
        """
        # 1. Find the decision in agent_memory
        decision = self.bus.audit.get(recommendation_id)
        
        # 2. Find which memories contributed
        provenance = self.bus.semantic.get_provenance(decision.fact_ids)
        
        # 3. Build explanation chain
        explanation = self._build_explanation(decision, provenance)
        
        # 4. LLM formats it into natural language
        return self._format_explanation(explanation)

    def knowledge_audit(self, domain: str = None) -> dict:
        """
        Return a summary of what Jarvis knows, organized by domain.
        Includes confidence distributions, staleness, and gap analysis.
        """
        notes = self.bus.semantic.browse(domain=domain)
        return {
            "total_facts": len(notes),
            "by_domain": self._group_by_domain(notes),
            "confidence_distribution": self._confidence_histogram(notes),
            "stalest_facts": self._stalest(notes, n=10),
            "lowest_confidence": self._weakest(notes, n=10),
            "knowledge_gaps": self._identify_gaps(notes),
        }

    def memory_diff(self, since: str) -> str:
        """
        What has Jarvis learned since a given date?
        Returns new facts, updated beliefs, and retired knowledge.
        """
        ...

    def correct(self, fact_id: str, correction: str) -> str:
        """
        Andy manually corrects a fact. The old fact is superseded,
        the correction is stored with provenance source='user_correction',
        and the significance of user corrections is set to maximum.
        """
        ...
```

**Killer feature: `memory_diff` in the daily brief.**

Add to the morning brief: "Here's what I learned yesterday" — a 3-5 line summary of new knowledge, updated beliefs, and retired facts. This keeps Andy in the loop without requiring him to actively inspect the system. If something looks wrong, he can correct it immediately.

```
Good morning, Sir. Here's what's new in my memory:

LEARNED:
- Aldi raised chicken breast to $2.49/lb (was $1.99 since March)
- Emma's piano lesson moved to 4:30 PM Wednesdays (teacher request)

UPDATED:
- Monthly grocery projection revised from $720 to $760 (price increases)
- Furnace filter reminder moved up 5 days (usage pattern suggests faster accumulation)

RETIRED:
- Old Costco membership price ($60) superseded by renewal notice ($65)
```

---

## How It All Connects: The Full Memory Architecture

```
                           ┌──────────────────────┐
                           │    MEMORY BUS         │
                           │  (Recommendation 3)   │
                           │  Unified I/O + hooks  │
                           └──────────┬───────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
            ▼                         ▼                         ▼
    ┌───────────────┐     ┌───────────────────┐     ┌───────────────────┐
    │  TIER 1:      │     │  TIER 2:          │     │  TIER 3:          │
    │  WORKING      │     │  EPISODIC         │     │  SEMANTIC         │
    │  MEMORY       │     │  MEMORY           │     │  MEMORY           │
    │  (Rec 1)      │     │  (Rec 1)          │     │  (Rec 1 + 4)      │
    │               │     │                   │     │                   │
    │  In-memory    │     │  episodes.db      │     │  ChromaDB +       │
    │  dict, <1ms   │     │  SQLite, <5ms     │     │  knowledge_notes  │
    │               │     │                   │     │  Zettelkasten      │
    │  20 messages + │     │  Full episodes    │     │  linked notes     │
    │  active task   │     │  with entities +  │     │  with provenance  │
    │               │     │  decisions         │     │  (Rec 7)          │
    └───────┬───────┘     └────────┬──────────┘     └────────┬──────────┘
            │                      │                         │
            │         ┌────────────▼──────────────┐          │
            │         │  CONSOLIDATION ENGINE     │          │
            │         │  "Sleep Cycle" (Rec 2)    │──────────┘
            │         │  Episodic → Semantic      │
            │         │  Pattern extraction       │
            │         │  Nightly @ 3 AM           │
            │         └────────────┬──────────────┘
            │                      │
            │         ┌────────────▼──────────────┐
            │         │  PROCEDURAL MEMORY (Rec 5)│
            │         │  Compiled action patterns  │
            │         │  Bypass LLM for known      │
            │         │  interaction types          │
            │         └───────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────┐
    │  ATTENTION GATE (Rec 6)                              │
    │  Relevance-weighted memory injection into prompts    │
    │  Surprise value + recency + domain alignment         │
    └───────┬──────────────────────────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────┐
    │  SHARED BLACKBOARD (Rec 9)                           │
    │  Real-time cross-specialist signals                  │
    │  Events, alerts, requests — not durable knowledge    │
    └───────┬──────────────────────────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────┐
    │  SIGNIFICANCE SCORER (Rec 8)                         │
    │  Tags memories with importance (novelty, consequence,│
    │  error signal) → affects encoding, decay, recall     │
    └───────┬──────────────────────────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────┐
    │  INTROSPECTION API (Rec 10)                          │
    │  "What do you know?" / "Why did you suggest that?"   │
    │  Memory diff in daily brief                          │
    └──────────────────────────────────────────────────────┘
```

---

## Implementation Priority for Memory System

| Priority | Recommendation | Reason |
|----------|---------------|--------|
| 1st | #3 Memory Bus | Foundation — all other components plug into this |
| 2nd | #1 Three-Tier Hierarchy | Replace the six silos with a coherent structure |
| 3rd | #7 Provenance Chain | Start tracking now; data accumulates for later analysis |
| 4th | #2 Consolidation Engine | The bridge between tiers — without this, episodic memory just grows forever |
| 5th | #4 Zettelkasten Linking | Enhances semantic memory with self-organizing structure |
| 6th | #6 Attention Gate | Improves prompt quality immediately |
| 7th | #8 Significance Scoring | Improves consolidation and recall quality |
| 8th | #5 Procedural Memory | Requires enough episodes to detect patterns (~30 days of data) |
| 9th | #9 Shared Blackboard | Requires multiple running specialists |
| 10th | #10 Introspection API | Polish layer — most valuable once the system has rich memory to inspect |

---

## Addendum: Scaling the Memory Architecture for 7 Knowledge Engines

**Date:** 2026-04-13 | **Status:** Design Expansion

The original 10 recommendations above were designed for household-interaction-scale memory — conversations, decisions, preferences. The expanded Jarvis vision introduces **7 continuous knowledge accumulation engines** that radically change the volume, variety, and velocity of data flowing through the memory system. This addendum identifies the architectural gaps and provides the expanded schemas, patterns, and strategies needed to support the full vision.

### The 7 Knowledge Engines

| # | Engine | Scope | Key Sources | Est. Annual Volume |
|---|--------|-------|-------------|-------------------|
| 1 | Financial & Economic Intelligence | Markets, macro indicators, tax, company fundamentals | FRED, SEC EDGAR, BLS, Yahoo Finance, Treasury | ~5M structured records/yr |
| 2 | Geopolitical & World Events | Conflicts, policy, trade, sanctions, elections | GDELT, Congress.gov, UN, Reuters RSS, think tanks | ~2M events/yr |
| 3 | AI/ML Research Sentinel | Papers, repos, models, techniques | arXiv, Semantic Scholar, GitHub, HuggingFace, Papers With Code | ~500K items/yr |
| 4 | Legal & Regulatory | Tax law, zoning, employment, consumer protection, insurance | IRS, Federal Register, state legislatures, CMS | ~200K documents/yr |
| 5 | Health & Wellness | Nutrition science, drug interactions, local health data | PubMed, FDA OpenFDA, pollen/AQI APIs, CMS Compare | ~300K records/yr |
| 6 | Local Intelligence | Real estate, schools, crime, infrastructure, utility rates, events | Zillow, county assessor, school DOE, city council, Eventbrite | ~100K records/yr |
| 7 | Family & Life Quality | Vacations, activities, bonding, parenting, child development | TripAdvisor, AllTrails, local parks/rec, school calendars, dev research | ~50K records/yr |

**Total estimated volume: ~8M+ new records per year, growing as engines mature.**

---

### Gap 1: Dual Ingestion — Interaction Memory vs. World Knowledge

The current architecture assumes all knowledge enters through conversations (Andy talks → working memory → episodic → semantic). The 7 engines ingest world knowledge through API scrapes, RSS feeds, and file downloads — no conversation involved.

**Solution: Two ingestion paths into the same MemoryBus.**

```
┌──────────────────────────────────────────────────────────────────┐
│                         MEMORY BUS                                │
│                    (Unified I/O — unchanged)                      │
│                                                                   │
│   INTERACTION PATH                    INGESTION PATH              │
│   (from conversations)                (from engines)              │
│                                                                   │
│   User message                        API scrape result           │
│      ↓                                   ↓                        │
│   Working Memory (Tier 1)            IngestionBuffer              │
│      ↓                                   ↓                        │
│   Episodic Memory (Tier 2)           Evaluation + Scoring         │
│      ↓ (consolidation)                   ↓                        │
│   Semantic Memory (Tier 3) ←──── World Knowledge Store            │
│                                                                   │
│   Both paths get:                                                 │
│   ✓ Provenance chain                                             │
│   ✓ Zettelkasten linking                                         │
│   ✓ Significance scoring                                         │
│   ✓ Attention gate eligibility                                   │
│   ✓ Training-readiness tagging                                   │
└──────────────────────────────────────────────────────────────────┘
```

```python
class IngestionBuffer:
    """
    Entry point for non-conversational world knowledge.
    Engines write here; the buffer evaluates, deduplicates,
    and routes to the appropriate stores.
    """

    def ingest(self, engine: str, items: list[RawItem]) -> IngestionReport:
        """
        Batch ingest from an engine's gather cycle.
        Each item goes through:
        1. Deduplication (exact + semantic similarity check)
        2. Quality scoring (source reliability, data completeness)
        3. Relevance scoring (how useful to the household)
        4. Schema validation (does it fit the domain tables)
        5. Storage routing (hot SQLite, warm archive, or ChromaDB)
        6. Provenance recording
        7. Zettelkasten link discovery
        """
        report = IngestionReport(engine=engine, total=len(items))

        for item in items:
            # Dedup check
            existing = self._find_duplicate(item)
            if existing:
                if item.timestamp > existing.timestamp:
                    self._supersede(existing, item)
                    report.updated += 1
                else:
                    report.skipped += 1
                continue

            # Score and route
            quality = self._score_quality(item)
            relevance = self._score_relevance(item)

            if quality < 0.3 or relevance < 0.2:
                report.rejected += 1
                continue

            # Store with full provenance
            fact_id = self.memory_bus.store_world_knowledge(
                engine=engine,
                content=item.content,
                structured_data=item.structured,
                quality=quality,
                relevance=relevance,
                source_url=item.source_url,
                raw_hash=item.content_hash,
            )

            # Discover links to existing knowledge
            self._discover_links(fact_id, item)
            report.ingested += 1

        return report
```

**New MemoryBus method:**

```python
# Added to MemoryBus class
def store_world_knowledge(self, engine: str, content: str,
                          structured_data: dict = None,
                          quality: float = 0.8,
                          relevance: float = 0.8,
                          **kwargs) -> str:
    """
    Store world knowledge from an engine (not from conversation).
    Goes directly to Tier 3 semantic + domain-specific structured tables.
    Skips Tier 1 (working) and Tier 2 (episodic) entirely.
    """
    # Write to semantic store (ChromaDB + knowledge_notes)
    fact_id = self.semantic.add(
        domain=engine,
        content=content,
        confidence=quality * relevance,
        source_type="engine_ingestion",
        **kwargs
    )

    # Write to domain-specific structured tables if applicable
    if structured_data:
        self._store_structured(engine, fact_id, structured_data)

    # Full provenance
    self._record_provenance(fact_id, "created",
                           source_type="engine_ingestion",
                           agent=engine, **kwargs)

    self._emit("world_knowledge_stored",
               fact_id=fact_id, engine=engine)
    return fact_id
```

---

### Gap 2: Tiered Storage for Million-Scale Data

**Problem:** SQLite handles ~10M rows well. Beyond that, you need a strategy. Over 3 years, the 7 engines could accumulate 25M+ records. ChromaDB struggles past ~1M vectors.

**Solution: Hot / Warm / Cold storage tiers with automatic lifecycle management.**

```
┌─────────────────────────────────────────────────────────────────┐
│                    TIERED STORAGE STRATEGY                       │
│                                                                  │
│  HOT (< 90 days)              WARM (90d - 2yr)                  │
│  ┌────────────────────┐       ┌────────────────────┐            │
│  │  facts.db (SQLite)  │       │  archive.db (SQLite)│            │
│  │  WAL mode, in-mem   │       │  Indexed, on-disk   │            │
│  │  cache, < 5ms       │       │  < 50ms queries     │            │
│  │  ~500K-2M rows      │       │  ~5-10M rows        │            │
│  └────────────────────┘       └────────────────────┘            │
│                                                                  │
│  COLD (> 2 years)             VECTORS                            │
│  ┌────────────────────┐       ┌────────────────────┐            │
│  │  Parquet files      │       │  Domain-sharded     │            │
│  │  via DuckDB         │       │  LanceDB / ChromaDB │            │
│  │  Columnar, compress │       │  Per-engine shards   │            │
│  │  Analytical queries │       │  ~1M vectors each    │            │
│  │  Great for training │       │  Total capacity:     │            │
│  │  data export        │       │  7M+ vectors         │            │
│  └────────────────────┘       └────────────────────┘            │
│                                                                  │
│  LIFECYCLE MANAGER (runs weekly)                                 │
│  - Move 90-day-old hot → warm                                    │
│  - Move 2-year-old warm → cold (Parquet export)                  │
│  - Compact warm indexes                                          │
│  - Rebalance vector shards                                       │
│  - Report storage metrics                                        │
└─────────────────────────────────────────────────────────────────┘
```

```python
class StorageLifecycleManager:
    """Weekly job that manages data tiering and compaction."""

    def run(self) -> LifecycleReport:
        # 1. Hot → Warm migration
        hot_cutoff = datetime.now() - timedelta(days=90)
        migrated = self._migrate_to_warm(before=hot_cutoff)

        # 2. Warm → Cold archival (Parquet export)
        warm_cutoff = datetime.now() - timedelta(days=730)
        archived = self._archive_to_parquet(before=warm_cutoff)

        # 3. Compact warm indexes
        self._compact_warm_indexes()

        # 4. Vector shard rebalancing
        for engine in self.engines:
            shard = self.vector_store.get_shard(engine)
            if shard.count > 1_000_000:
                self._split_shard(shard)

        # 5. Storage metrics
        return LifecycleReport(
            hot_rows=self._count_hot(),
            warm_rows=self._count_warm(),
            cold_files=self._count_parquet_files(),
            vector_count=self._total_vectors(),
            total_disk_gb=self._disk_usage(),
        )
```

**Domain-specific structured tables (hot tier):**

```sql
-- ═══ ENGINE 1: Financial & Economic Intelligence ═══

CREATE TABLE economic_indicators (
    id              TEXT PRIMARY KEY,
    series_id       TEXT NOT NULL,       -- FRED series (e.g., 'GDP', 'UNRATE', 'CPIAUCSL')
    value           REAL NOT NULL,
    period          TEXT NOT NULL,       -- '2026-Q1', '2026-04', '2026-04-13'
    frequency       TEXT NOT NULL,       -- 'daily', 'weekly', 'monthly', 'quarterly'
    source          TEXT NOT NULL,       -- 'fred', 'bls', 'treasury'
    retrieved_at    TEXT NOT NULL,
    revised         INTEGER DEFAULT 0,  -- 1 if this is a revision of prior value
    prior_value     REAL                -- what the old value was before revision
);

CREATE TABLE market_data (
    id              TEXT PRIMARY KEY,
    symbol          TEXT NOT NULL,
    date            TEXT NOT NULL,
    open            REAL, high REAL, low REAL, close REAL,
    volume          INTEGER,
    adjusted_close  REAL,
    source          TEXT NOT NULL       -- 'yahoo', 'alphavantage'
);

CREATE TABLE sec_filings (
    id              TEXT PRIMARY KEY,
    cik             TEXT NOT NULL,       -- company CIK
    company_name    TEXT NOT NULL,
    form_type       TEXT NOT NULL,       -- '10-K', '10-Q', '8-K', 'DEF 14A'
    filed_date      TEXT NOT NULL,
    accepted_date   TEXT NOT NULL,
    document_url    TEXT NOT NULL,
    summary         TEXT,               -- LLM-generated summary
    key_metrics     TEXT,               -- JSON: extracted financial highlights
    sentiment       REAL,               -- LLM sentiment score
    relevance       REAL                -- relevance to Andy's portfolio
);

CREATE TABLE tax_changes (
    id              TEXT PRIMARY KEY,
    jurisdiction    TEXT NOT NULL,       -- 'federal', 'MN', 'hennepin_county'
    category        TEXT NOT NULL,       -- 'income', 'property', 'capital_gains', 'deduction'
    effective_date  TEXT NOT NULL,
    description     TEXT NOT NULL,
    impact_summary  TEXT,               -- LLM: "This means X for your household"
    source_url      TEXT,
    confidence      REAL DEFAULT 0.8
);

-- ═══ ENGINE 2: Geopolitical & World Events ═══

CREATE TABLE geopolitical_events (
    id              TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,       -- 'conflict', 'election', 'sanctions',
                                        -- 'trade_agreement', 'policy_change',
                                        -- 'natural_disaster', 'pandemic'
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    regions         TEXT NOT NULL,       -- JSON array: ['US', 'CN', 'EU']
    started_at      TEXT NOT NULL,
    ended_at        TEXT,               -- NULL if ongoing
    severity        REAL,               -- 0-1 scale
    market_impact   TEXT,               -- JSON: {sectors: [...], direction: 'negative', magnitude: 0.7}
    source          TEXT NOT NULL,       -- 'gdelt', 'reuters', 'congress_gov'
    source_url      TEXT,
    related_events  TEXT                -- JSON array of event IDs
);

CREATE TABLE policy_tracker (
    id              TEXT PRIMARY KEY,
    jurisdiction    TEXT NOT NULL,
    policy_type     TEXT NOT NULL,       -- 'bill', 'executive_order', 'regulation', 'fed_statement'
    title           TEXT NOT NULL,
    status          TEXT NOT NULL,       -- 'proposed', 'committee', 'passed', 'signed', 'effective'
    introduced_date TEXT NOT NULL,
    last_action     TEXT,
    impact_domains  TEXT,               -- JSON: ['finance', 'health', 'home']
    summary         TEXT,               -- LLM summary
    household_impact TEXT,              -- LLM: "Here's what this means for you"
    source_url      TEXT
);

-- ═══ ENGINE 3: AI/ML Research Sentinel ═══

CREATE TABLE research_papers (
    id              TEXT PRIMARY KEY,
    arxiv_id        TEXT,
    semantic_scholar_id TEXT,
    title           TEXT NOT NULL,
    authors         TEXT NOT NULL,       -- JSON array
    abstract        TEXT NOT NULL,
    published_date  TEXT NOT NULL,
    categories      TEXT NOT NULL,       -- JSON: ['cs.AI', 'cs.LG']
    summary         TEXT,               -- LLM: distilled key contribution
    technique_type  TEXT,               -- 'memory', 'rag', 'fine_tuning', 'agents', etc.
    applicability   TEXT,               -- JSON: {jarvis_component: 'memory_bus', improvement: '~15%', effort: 'medium'}
    quality_score   REAL,               -- citation count + venue + recency
    code_url        TEXT,               -- GitHub repo if available
    reviewed        INTEGER DEFAULT 0,  -- 1 = Sentinel has evaluated for Jarvis applicability
    actionable      INTEGER DEFAULT 0   -- 1 = could directly improve our systems
);

CREATE TABLE tracked_repos (
    id              TEXT PRIMARY KEY,
    github_url      TEXT NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    stars           INTEGER,
    language        TEXT,
    license         TEXT,
    last_commit     TEXT,
    topics          TEXT,               -- JSON array
    relevance       TEXT,               -- JSON: which Jarvis components this relates to
    summary         TEXT,               -- LLM: what this repo does and why we care
    first_seen      TEXT NOT NULL,
    last_checked    TEXT NOT NULL,
    status          TEXT DEFAULT 'tracking' -- 'tracking', 'evaluated', 'integrated', 'archived'
);

CREATE TABLE model_registry (
    id              TEXT PRIMARY KEY,
    hf_model_id     TEXT,
    name            TEXT NOT NULL,
    parameter_count TEXT,               -- '7B', '13B', '70B'
    architecture    TEXT,               -- 'llama', 'mistral', 'qwen', 'gemma'
    quantizations   TEXT,               -- JSON: ['Q4_K_M', 'Q5_K_S', 'Q8_0']
    benchmarks      TEXT,               -- JSON: {mmlu: 0.72, humaneval: 0.65}
    vram_required   TEXT,               -- JSON per quant: {'Q4_K_M': '4.5GB'}
    runs_on_our_hw  INTEGER DEFAULT 0,  -- 1 = fits in 16-24GB VRAM (or 96GB unified)
    use_case        TEXT,               -- 'routing', 'reasoning', 'coding', 'embedding'
    first_seen      TEXT NOT NULL,
    notes           TEXT                -- LLM: why this matters for us
);

CREATE TABLE improvement_proposals (
    id              TEXT PRIMARY KEY,
    source_paper_id TEXT,               -- which paper inspired this
    source_repo_id  TEXT,               -- which repo inspired this
    target_component TEXT NOT NULL,     -- 'memory_bus', 'attention_gate', 'grocery_spec', etc.
    proposal        TEXT NOT NULL,      -- LLM: what to change and why
    estimated_impact TEXT,              -- 'minor', 'moderate', 'significant'
    estimated_effort TEXT,              -- 'trivial', 'small', 'medium', 'large'
    status          TEXT DEFAULT 'proposed', -- 'proposed', 'approved', 'implemented', 'rejected'
    created_at      TEXT NOT NULL,
    reviewed_at     TEXT,
    review_notes    TEXT                -- Andy's feedback
);

-- ═══ ENGINE 4: Legal & Regulatory ═══

CREATE TABLE regulatory_changes (
    id              TEXT PRIMARY KEY,
    jurisdiction    TEXT NOT NULL,       -- 'federal', 'MN', 'minneapolis'
    domain          TEXT NOT NULL,       -- 'tax', 'zoning', 'employment', 'consumer', 'insurance'
    title           TEXT NOT NULL,
    effective_date  TEXT,
    description     TEXT NOT NULL,
    household_impact TEXT,              -- LLM: plain-English impact assessment
    action_required TEXT,               -- JSON: [{action: "...", deadline: "..."}]
    source          TEXT NOT NULL,       -- 'federal_register', 'mn_legislature', etc.
    source_url      TEXT,
    confidence      REAL DEFAULT 0.8
);

-- ═══ ENGINE 5: Health & Wellness ═══

CREATE TABLE health_knowledge (
    id              TEXT PRIMARY KEY,
    category        TEXT NOT NULL,       -- 'nutrition', 'drug_interaction', 'exercise',
                                        -- 'seasonal_health', 'air_quality', 'prevention'
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    source          TEXT NOT NULL,       -- 'pubmed', 'fda', 'cdc', 'local_health_dept'
    source_url      TEXT,
    evidence_level  TEXT,               -- 'meta_analysis', 'rct', 'observational', 'expert_opinion'
    relevance       REAL,               -- to household health profile
    last_verified   TEXT,
    seasonal        INTEGER DEFAULT 0   -- 1 = seasonal relevance (allergies, flu, etc.)
);

CREATE TABLE environmental_data (
    id              TEXT PRIMARY KEY,
    metric          TEXT NOT NULL,       -- 'aqi', 'pollen_count', 'uv_index', 'flu_activity'
    value           REAL NOT NULL,
    location        TEXT NOT NULL,       -- zip code or city
    measured_at     TEXT NOT NULL,
    source          TEXT NOT NULL,
    forecast        TEXT                -- JSON: next 5 day forecast if available
);

-- ═══ ENGINE 6: Local Intelligence ═══

CREATE TABLE local_data (
    id              TEXT PRIMARY KEY,
    category        TEXT NOT NULL,       -- 'real_estate', 'school_district', 'crime',
                                        -- 'infrastructure', 'utilities', 'business'
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,
    location        TEXT,               -- address, neighborhood, zip
    data_date       TEXT NOT NULL,
    source          TEXT NOT NULL,
    source_url      TEXT,
    trend           TEXT                -- JSON: historical values for trend analysis
);

-- ═══ ENGINE 7: Family & Life Quality ═══

CREATE TABLE family_activities (
    id              TEXT PRIMARY KEY,
    category        TEXT NOT NULL,       -- 'outdoor', 'indoor', 'event', 'travel',
                                        -- 'bonding', 'educational', 'seasonal'
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    location        TEXT,               -- specific venue or area
    distance_miles  REAL,               -- from home
    cost_estimate   TEXT,               -- 'free', '$', '$$', '$$$'
    age_appropriate TEXT,               -- JSON: {min_age: 4, max_age: 16}
    duration        TEXT,               -- '2 hours', 'half day', 'weekend'
    season          TEXT,               -- 'any', 'summer', 'winter', 'spring', 'fall'
    weather_req     TEXT,               -- 'outdoor_clear', 'any', 'indoor'
    source          TEXT NOT NULL,       -- 'alltrails', 'eventbrite', 'parks_rec', 'tripadvisor'
    source_url      TEXT,
    rating          REAL,               -- source rating
    household_rating REAL,              -- our family's rating (after doing it)
    last_done       TEXT,               -- when we last did this
    times_done      INTEGER DEFAULT 0,  -- how many times
    notes           TEXT                -- family notes, tips, memories
);

CREATE TABLE vacation_research (
    id              TEXT PRIMARY KEY,
    destination     TEXT NOT NULL,
    trip_type       TEXT NOT NULL,       -- 'road_trip', 'flight', 'camping', 'staycation'
    estimated_cost  REAL,
    duration_days   INTEGER,
    best_season     TEXT,
    kid_friendly    INTEGER DEFAULT 1,
    highlights      TEXT,               -- JSON array of attractions/activities
    logistics       TEXT,               -- JSON: travel time, accommodation options, tips
    source          TEXT NOT NULL,
    source_url      TEXT,
    household_interest REAL DEFAULT 0.5, -- learned from family preferences
    saved_at        TEXT NOT NULL,
    planned_for     TEXT                -- NULL or target date
);

CREATE TABLE parenting_knowledge (
    id              TEXT PRIMARY KEY,
    category        TEXT NOT NULL,       -- 'development', 'education', 'activities',
                                        -- 'health', 'social', 'screen_time', 'sleep'
    age_range       TEXT,               -- '5-7', '8-10', 'teen', etc.
    title           TEXT NOT NULL,
    content         TEXT NOT NULL,       -- research-backed advice or activity idea
    source          TEXT NOT NULL,       -- 'pubmed', 'aap', 'child_dev_journal'
    evidence_level  TEXT,
    actionable      INTEGER DEFAULT 0,  -- 1 = contains specific things to try
    seasonal        INTEGER DEFAULT 0
);

CREATE TABLE local_events (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT,
    venue           TEXT,
    address         TEXT,
    event_date      TEXT NOT NULL,
    event_time      TEXT,
    end_date        TEXT,               -- for multi-day events
    cost            TEXT,               -- 'free', '$5', '$10-20'
    category        TEXT,               -- 'festival', 'market', 'concert', 'sports',
                                        -- 'kids', 'community', 'holiday'
    family_friendly INTEGER DEFAULT 1,
    source          TEXT NOT NULL,       -- 'eventbrite', 'parks_rec', 'community_calendar'
    source_url      TEXT,
    distance_miles  REAL,
    relevance       REAL                -- scored against family preferences
);
```

---

### Gap 3: Training Data Export Pipeline

Every engine should tag its data for training readiness. This enables the long-term goal of fine-tuning household-specific models.

```python
class TrainingDataExporter:
    """
    Exports knowledge into standard training formats.
    Runs on-demand or as part of a monthly pipeline.
    """

    def export_instruction_pairs(self, domain: str = None,
                                  min_quality: float = 0.7,
                                  format: str = "sharegpt") -> str:
        """
        Export question→answer pairs from decision logs + graded outcomes.
        Each pair: (user question, Jarvis response, outcome grade).
        Format: ShareGPT JSON for instruction tuning.
        """
        decisions = self.memory_bus.audit.query(
            domain=domain,
            min_grade=min_quality,
            has_outcome=True,
        )

        pairs = []
        for d in decisions:
            pair = {
                "conversations": [
                    {"from": "human", "value": d.user_message},
                    {"from": "gpt", "value": d.response},
                ],
                "metadata": {
                    "domain": d.domain,
                    "grade": d.grade,
                    "outcome": d.outcome_summary,
                    "provenance": d.provenance_chain,
                },
            }
            pairs.append(pair)

        return self._write_jsonl(pairs, format)

    def export_dpo_pairs(self, domain: str = None,
                         min_grade_diff: float = 0.3) -> str:
        """
        Export DPO (Direct Preference Optimization) training pairs.
        Finds cases where similar queries got different grades:
        (prompt, chosen_response, rejected_response).
        """
        ...

    def export_knowledge_corpus(self, engines: list[str] = None,
                                 format: str = "parquet") -> str:
        """
        Export raw knowledge for continued pre-training.
        Includes world knowledge from all engines as clean text.
        """
        ...

    def training_readiness_report(self) -> dict:
        """
        How much training-quality data do we have?
        Returns counts by domain, quality tier, and format.
        """
        return {
            "instruction_pairs": {
                "total": self._count_gradable_decisions(),
                "high_quality": self._count_gradable_decisions(min_grade=0.8),
                "by_domain": self._count_by_domain(),
            },
            "dpo_pairs": self._count_dpo_candidates(),
            "knowledge_corpus": {
                "total_tokens": self._estimate_corpus_tokens(),
                "by_engine": self._corpus_by_engine(),
            },
            "estimated_readiness": self._readiness_assessment(),
            # e.g., "~6 months until LoRA fine-tune viable for grocery domain"
        }
```

```sql
-- Training readiness metadata (added to kb_index)
ALTER TABLE kb_index ADD COLUMN training_ready INTEGER DEFAULT 0;
ALTER TABLE kb_index ADD COLUMN training_quality REAL;       -- 0-1
ALTER TABLE kb_index ADD COLUMN training_format TEXT;         -- 'instruction', 'dpo', 'corpus'
ALTER TABLE kb_index ADD COLUMN training_exported_at TEXT;    -- last export timestamp

-- Decision grades for DPO pair mining (extends agent_memory)
CREATE TABLE decision_grades (
    id              TEXT PRIMARY KEY,
    decision_id     TEXT NOT NULL,
    grade_type      TEXT NOT NULL,       -- 'short_term' (24h), 'long_term' (7-30d)
    grade           REAL NOT NULL,       -- 0-1
    graded_at       TEXT NOT NULL,
    grading_method  TEXT NOT NULL,       -- 'auto_acceptance', 'auto_outcome', 'user_feedback'
    evidence        TEXT,               -- why this grade
    grader_model    TEXT                -- which model did the grading
);
```

---

### Gap 4: Bitemporal Knowledge for Time-Series Reasoning

Financial and geopolitical engines need to answer: "What did we *believe* on date X?" vs. "What was *actually true* on date X?" This is essential for backtesting and for training models on temporal reasoning.

```sql
-- Bitemporal knowledge table
-- valid_from/valid_to = when the fact was TRUE in the real world
-- known_from/known_to = when WE KNEW about it
CREATE TABLE bitemporal_facts (
    id              TEXT PRIMARY KEY,
    domain          TEXT NOT NULL,
    fact_type       TEXT NOT NULL,
    content         TEXT NOT NULL,
    value           REAL,               -- for numeric facts

    -- Temporal dimensions
    valid_from      TEXT NOT NULL,       -- when this became true in reality
    valid_to        TEXT,               -- when this stopped being true (NULL = still true)
    known_from      TEXT NOT NULL,       -- when Jarvis learned this
    known_to        TEXT,               -- when Jarvis learned this was wrong (NULL = still believed)

    -- Revision tracking
    revision_of     TEXT,               -- ID of the fact this revises
    revision_reason TEXT,               -- why the revision happened

    -- Standard metadata
    source          TEXT NOT NULL,
    confidence      REAL DEFAULT 0.8,
    provenance_id   TEXT
);

CREATE INDEX idx_bitemporal_valid ON bitemporal_facts(domain, fact_type, valid_from);
CREATE INDEX idx_bitemporal_known ON bitemporal_facts(domain, fact_type, known_from);
```

**Query patterns this enables:**

```sql
-- "What did we think GDP growth was on March 15?"
SELECT * FROM bitemporal_facts
WHERE domain = 'economic' AND fact_type = 'gdp_growth'
  AND valid_from <= '2026-03-15'
  AND (valid_to IS NULL OR valid_to > '2026-03-15')
  AND known_from <= '2026-03-15'
  AND (known_to IS NULL OR known_to > '2026-03-15');

-- "How did our belief about Q1 GDP change over time?" (revision history)
SELECT * FROM bitemporal_facts
WHERE domain = 'economic' AND fact_type = 'gdp_growth'
  AND valid_from = '2026-01-01'
ORDER BY known_from;
```

---

### Gap 5: Multi-Node Federation Strategy

When EVO-X2 nodes come online, the Knowledge Lake must span machines.

```
┌─────────────────────────────────────────────────────────────────┐
│                    FEDERATION ARCHITECTURE                       │
│                                                                  │
│  NODE 1: Primary (current machine)                              │
│  ├── Interaction memory (Tiers 1-3)                             │
│  ├── Engine 6 (Local Intelligence)                              │
│  ├── Engine 7 (Family & Life Quality)                           │
│  ├── Household adapters (grocery, home, calendar)               │
│  └── PRIMARY facts.db (source of truth)                         │
│                                                                  │
│  NODE 2: EVO-X2 #1 — Heavy Reasoning                           │
│  ├── Engine 1 (Financial Intelligence) — heavy models           │
│  ├── Engine 2 (Geopolitical Events)                             │
│  ├── Engine 4 (Legal & Regulatory)                              │
│  ├── InvestorSpec (70B reasoning models)                        │
│  └── REPLICA facts.db (Litestream sync from primary)            │
│                                                                  │
│  NODE 3: EVO-X2 #2 — Research & Training                       │
│  ├── Engine 3 (AI Research Sentinel)                            │
│  ├── Engine 5 (Health & Wellness)                               │
│  ├── Model training jobs (LoRA fine-tuning)                     │
│  ├── MetaCognitive Supervisor                                   │
│  └── REPLICA facts.db (Litestream sync from primary)            │
│                                                                  │
│  SYNC STRATEGY:                                                  │
│  ├── Litestream: continuous SQLite WAL replication               │
│  │   Primary → S3-compatible local MinIO → Replicas             │
│  ├── ChromaDB: per-node shards, cross-node search via API       │
│  ├── Blackboard: Redis or ZeroMQ pub/sub for real-time signals  │
│  └── Conflict resolution: last-writer-wins + provenance audit   │
└─────────────────────────────────────────────────────────────────┘
```

---

### Updated Implementation Priority (Full 7-Engine System)

| Priority | Component | Reason |
|----------|-----------|--------|
| 1st | Memory Bus + Three-Tier Hierarchy | Foundation for everything |
| 2nd | IngestionBuffer + World Knowledge path | Engines can't store data without this |
| 3rd | Provenance Chain | Start tracking from day 1 |
| 4th | Engine 1 (Financial) + Engine 3 (AI Research) | Highest ROI engines — investment intelligence + self-improvement |
| 5th | Consolidation Engine + Zettelkasten Linking | Cross-engine connections start forming |
| 6th | Engine 2 (Geopolitical) + Engine 4 (Legal) | Feed context to financial engine |
| 7th | Tiered Storage (Hot/Warm/Cold) | Needed once engines run for ~3 months |
| 8th | Engine 5 (Health) + Engine 6 (Local) + Engine 7 (Family) | Quality of life engines |
| 9th | Bitemporal facts + Training Export Pipeline | Needed once 6+ months of data accumulated |
| 10th | Multi-Node Federation | When first EVO-X2 arrives |
| 11th | Full model fine-tuning pipeline | When 12-18 months of graded data exists |
