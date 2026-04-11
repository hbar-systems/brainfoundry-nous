# Memory Architecture for hbar-brain
*Distilled from research session — April 2026*

---

## Core Framing

Memory in AI is fundamentally an **organizational problem**. The compute and retrieval mechanics are secondary. The hard part is what structure you impose on experience so that it becomes retrievable, composable, and useful later.

The model doesn't learn you. The **system around the model** learns you, and presents that learning to the model fresh at the start of each conversation.

---

## Why Memory Is an Open Problem

Memory fractures into several distinct sub-problems without a unified solution:

**Largely solved:**
- In-context memory (transformer attention over a long prompt)
- Retrieval-augmented generation (RAG) — mature enough for production, with known failure modes

**Genuinely open:**
- *Continual learning without catastrophic forgetting* — how to update weights from new experience without destroying prior knowledge. Current approaches (EWC, LoRA, replay buffers) are workarounds, not solutions.
- *Episodic vs. semantic consolidation* — no clean architecture for deciding what becomes a retrievable episode vs. a compressed belief vs. discarded.
- *Long-horizon working memory* — even with large context windows, attention degrades. The "lost in the middle" problem is real. No equivalent of human chunking and hierarchical compression.
- *Associative and reconstructive memory* — human memory rebuilds from fragments. AI retrieval is mostly lookup-based.
- *Memory with identity continuity* — how a node accumulates experience and remains coherent over time without freezing or drifting.

Human memory is not one system — it's at least five (working, episodic, semantic, procedural, priming), integrated through sleep consolidation and emotional salience weighting. AI currently has rough analogs to maybe two of these, poorly integrated.

---

## Why "Always Inject Everything" Breaks

The intuitive solution — just inject all memory into every context — fails for specific reasons:

- **Cost and latency** — every token in context costs compute on every forward pass. At scale this becomes untenable.
- **Attention degrades over distance** — models have strong recency bias. Information in the middle of long contexts is systematically underweighted. 200K tokens injected ≠ 200K tokens used.
- **Not all memory is equal** — without salience and recency filters, old low-value content competes with high-value recent content. Signal-to-noise degrades.
- **Injection defers, not solves, retrieval** — once you have more than fits in context, you must decide what to inject. You're doing retrieval anyway, just less explicitly.
- **Raw episodes are noisier than consolidated beliefs** — "on March 3rd the user said they prefer concise answers" is worse than the distilled belief: "user prefers concision." Consolidation is what creates useful memory from raw experience.
- **Identity and coherence** — a node whose "self" is a pile of logs has a different quality of continuity than one with consolidated beliefs and patterns.

Always-injection is fine as a prototype and for short sessions. It breaks down over time, at scale, and wherever quality of memory matters.

---

## The RAG + Conversation Storage Architecture

This is the right immediate architecture for hbar-brain. The gaps to design around:

### Chunking
Conversations don't chunk cleanly by token count — semantic coherence gets destroyed. Requires either semantic chunking (split at meaning boundaries) or summarization-based compression before storage.

### The Value Formula
A naive retrieval scoring formula:

```
value = α·recency + β·relevance(query) + γ·salience + δ·source_weight
```

Each term has design problems:
- *Recency* — easy but over-weights mundane present
- *Relevance* — cosine similarity by default, which is semantic proximity, not usefulness
- *Salience* — hardest to measure. Candidates: novelty relative to existing semantic memory, outcome significance, explicit flagging
- *Source weight* — own writing vs. ingested docs vs. conversation should weight differently

Treat this as a **parameter space to tune**, not a formula to derive analytically. Run it, observe retrieval failures, adjust.

### The Missing Layer: Consolidation
RAG + conversation storage gives retrieval over raw episodes. It does not give a semantic layer that *updates*. 200 conversations refining your thinking on node architecture → RAG retrieves individual conversations, not your current distilled belief.

Consolidation is what turns episodic memory into semantic memory. Without it, memory grows but never matures.

---

## Fine-tuning on Open Weights Models

Fine-tuning and RAG are complementary layers, not competitors.

**What fine-tuning solves:**
- Style and format adaptation
- Domain-specific vocabulary and reasoning patterns
- Behavioral tendencies — making the model reason in your idiom
- Encoding stable, slow-changing knowledge into weights

**What fine-tuning does not solve:**
- *New information after training cutoff* — bakes knowledge in statically. Requires retraining to update.
- *Catastrophic forgetting* — fine-tuning on new data degrades prior knowledge. PEFT methods (LoRA, QLoRA) reduce but don't eliminate this. This is the core unsolved problem.
- *Episodic specificity* — weights encode without provenance. The model "knows" something but can't trace when it learned it or how confident to be.
- *Lookup-based retrieval* — weights don't support "recall specifically what happened on March 3rd."

**The practical split:**
- Fine-tune for identity, style, reasoning patterns, stable domain knowledge — slow-changing things that define *how the node thinks*
- RAG for episodic memory, recent information, specific traceable facts — fast-changing things

Fine-tune the base model periodically (monthly, quarterly) as your thinking evolves. RAG handles the dynamic layer on top.

**The real blocker for continuous fine-tuning** is the feedback signal. To fine-tune well you need a signal for what's good — labeled examples for supervised fine-tuning, preference data for RLHF. Generating that signal systematically from node experience is itself an unsolved design problem. Define early: what does "this memory update was good" mean for hbar-brain, and how do you measure it?

---

## How hbar-brain "Learns You"

The model doesn't learn you. The three mechanisms available:

### 1. Static Identity Injection
A curated profile injected into every conversation — facts, preferences, context. Works but manually maintained, slowly updated, and flat. Doesn't capture evolving thinking or patterns across time.

### 2. Dynamic Retrieval at Session Start
Before a conversation begins, the system queries your memory store based on current context and injects the most valuable retrieved chunks. RAG applied to *you* rather than to documents. Your past conversations, notes, and distilled beliefs become the retrieval corpus.

### 3. Periodic Consolidation into a Living Document
A scheduled process reads recent episodes and updates a structured semantic document — your current beliefs, active problems, patterns, preferences. This document gets injected every session. Not raw logs — distilled you.

### The Full Loop

```
[conversation happens]
        ↓
[conversation saved to episodic store]
        ↓
[consolidation process — nightly or triggered]
  → reads recent episodes
  → updates semantic memory document
  → flags high-salience items
        ↓
[next session starts]
  → semantic document injected (who you are, current state)
  → dynamic retrieval of relevant episodes injected
  → model reconstructs a working model of you
        ↓
[conversation happens]
```

The model is always *reading about you* rather than *having known you*. The closer the semantic document gets to capturing how you think — not just what you know — the less the stateless model limitation matters in practice.

---

## Memory as Organizational Problem

To make raw experience into memory, you must answer explicitly:

- **What unit do you store?** Full conversation? Turns? Extracted insights? Decisions made?
- **What schema do you attach?** Timestamp, topic, domain, confidence, salience score, links to related memories?
- **What tier does it go to?** Episodic (raw, happened) vs. semantic (distilled, true) vs. procedural (how to do X)
- **What triggers consolidation?** Time? Volume? Explicit flagging?
- **What is the retrieval key?** How will you find this later?

---

## The Identity Layer as Schema

The identity layer is not just *about* you — it is the **organizational schema** for all memory in the system. What hbar is, what it cares about, what domains it operates in, how it thinks — this determines what is salient, how things get categorized, what connects to what.

The identity layer should explicitly define:
- **Domains** — named areas of work and thought
- **Current tensions** — active problems being worked through
- **Stable beliefs** — things settled, don't need re-deriving
- **Reasoning patterns** — characteristic approaches to problems
- **Active projects and their state**

Every memory gets located relative to this schema. That is what makes it retrievable and composable rather than merely stored.

---

## The Memory Protocol (Start Now)

Before building infrastructure, establish a discipline. At the end of each significant session:

```
DATE:
DOMAIN: (which hbar.systems subsystem or life area)
SESSION TYPE: (exploration / decision / problem-solving / creative)

KEY INSIGHTS: (what became clearer)
OPEN QUESTIONS: (what is unresolved)
DECISIONS MADE: (what you committed to)
BELIEF UPDATES: (what changed in how you think about X)
LINKS: (what does this connect to — other sessions, concepts, systems)
```

This is your episodic store, manually seeded. It trains your intuition for what is worth capturing before you automate it. It also becomes training data for the consolidation process later.

The protocol you start today becomes the schema your automation implements later.

---

## Full Architecture (Target State)

```
raw experience (conversations, notes, docs)
        ↓ consolidation
structured episodic store (tagged, schematized)
        ↓ consolidation
semantic memory (distilled beliefs, patterns, knowledge)
        ↓
identity document (living, updated, injected every session)
```

**Two-tier memory store:**
- *Episodic store* — conversations, docs, raw experience, tagged and schematized
- *Semantic store* — distilled beliefs, patterns, facts, updated by consolidation

Retrieval pulls from both. Consolidation is what connects them.

---

## Build Priorities (Sequenced)

1. **Save everything** — every conversation, timestamped, structured
2. **Start the memory protocol manually** — before any automation exists
3. **Build consolidation** — even a simple weekly LLM pass that reads recent conversations and updates a "current state of hbar" document
4. **Design the injection layer** — what gets injected every session (semantic document) vs. what gets retrieved dynamically (relevant episodes)
5. **Instrument retrieval quality** — retrieval hit rate, staleness, wrong memory surfaced. Without metrics you are building blind.
6. **Fine-tune periodically** — once enough consolidated signal exists to know what stable patterns are worth baking into weights

---

## Phase 3 — Stylistic Layer (Personal Model)

Phases 1 and 2 give a brain that **knows about you**. Phase 3 gives a brain that **sounds like you**.

```
Phase 1 (now)    →  semantic facts — what is true about you and your world
Phase 2          →  episodic store — what happened, when, how you expressed it
Phase 3          →  stylistic layer — how you think, your reasoning patterns, your vocabulary
```

Phase 3 requires fine-tuning or LoRA adapters on the base model itself, trained on your conversation history. This is technically feasible (Mistral + QLoRA on your own hardware) and is the most powerful form of sovereignty: a model that reasons in your voice, about your world, on your hardware.

**The feedback signal problem:** to fine-tune well you need labeled examples or preference data. Generating that signal systematically from node experience is itself an unsolved design problem. Define early: what does "this model update was good" mean for your brain, and how do you measure it?

The personal model layer is Phase 3 — not blocking anything today, but worth designing for. The episodic store you build in Phase 2 becomes the training corpus for Phase 3.

---

## Key References

- Tulving — *Elements of Episodic Memory* (functional taxonomy)
- MemGPT paper (2023) — closest thing to a production memory OS for agents
- Generative Agents paper, Park et al. (2023) — memory + reflection + planning
- Mem0, Letta, Zep — production memory layers; study their architectures critically

---

*This document should itself be subject to the memory protocol — reviewed periodically, updated as the architecture evolves, and linked to implementation notes as the system gets built.*
