# ADR: Enhancing Chatbot — Tools, Memory & Orchestration

**Status:** Accepted
**Date:** 2026-03-21
**Branch:** `feature/Enchancing_Chatbot`

---

## ADR-01: Single Agent Over Multi-Agent

**Decision:** Use a single Claude agent with tools, not a multi-agent architecture.

**Alternatives considered:**
- Multi-agent with specialized sub-agents (retrieval agent, calculator agent, etc.)
- LangGraph with state machines

**Rationale:** Research from Anthropic, Microsoft, Google, and LangChain benchmarks unanimously recommends single-agent for bounded-domain chatbots. Multi-agent adds ~15x token cost vs ~4x for single-agent, fragments context, and complicates debugging. The domain has 2 sources and ~8 tools — well within single-agent capacity.

**Consequence:** Revisit only if tool count exceeds ~15 or fundamentally different security/domain boundaries emerge.

---

## ADR-02: No Framework Dependency (LangChain/LangGraph)

**Decision:** Build the agentic loop directly with the Anthropic SDK.

**Alternatives considered:**
- LangChain with LCEL chains
- LangGraph with state graphs
- LlamaIndex with query engines

**Rationale:** The agentic loop is ~30 lines of Python. Direct SDK usage provides: no abstraction tax, full control over message format, native SSE streaming, no dependency churn. LangChain patterns are used as architectural reference only.

**Consequence:** If multi-agent becomes necessary, will need to evaluate framework adoption at that point.

---

## ADR-03: Token Counting — Anthropic API with tiktoken Fallback

**Decision:** Use `client.beta.messages.count_tokens()` for accurate token counting, with `tiktoken cl100k_base + 15% safety margin` as fallback.

**Alternatives considered:**
- tiktoken only (free but ~10-20% inaccurate for Claude's tokenizer)
- Anthropic API only (accurate but adds network dependency)

**Rationale:** Claude's tokenizer differs from OpenAI's tiktoken. The Anthropic API provides exact counts in a single fast call. tiktoken fallback ensures the system works when the API is unreachable.

**Consequence:** One additional API call per request for token counting. Minimal latency impact.

---

## ADR-04: SummaryBuffer Over Full Summarization

**Decision:** Use a tiered approach: recent messages verbatim + older messages compressed into a running summary.

**Alternatives considered:**
- Full summarization (compress everything)
- Sliding window only (truncate old messages)
- Map-reduce summarization

**Rationale:** HR consultations require high fidelity for recent details (e.g., specific salary figures, dates) while older context is needed mainly for topic continuity. SummaryBuffer preserves recent exchange precision while compressing older context.

**Consequence:** Haiku calls for summary generation add latency, but are async and best-effort.

---

## ADR-05: Haiku for All Enhancement Calls (Best-Effort)

**Decision:** Use `claude-haiku-4-5` for summarization, fact extraction, and profile extraction. All calls are best-effort — on failure, log and proceed.

**Alternatives considered:**
- Sonnet for all calls (more accurate but 10x cost)
- Local model for extraction (complex setup)

**Rationale:** Enhancement calls (summary, facts, profile) don't need Sonnet-level reasoning. Haiku is fast and cheap. Making them best-effort ensures a failed Haiku call never blocks the user's request.

**Consequence:** In rare Haiku outages, conversations proceed without summaries or profile updates. No user-visible degradation.

---

## ADR-06: SQLite for Profile Storage

**Decision:** Store user profiles in SQLite alongside session data.

**Alternatives considered:**
- Separate PostgreSQL database
- Redis for profile caching
- ChromaDB metadata

**Rationale:** Already using SQLite for sessions. Adding a `user_profiles` table avoids a new dependency. Profile data is structured (employment type, salary bracket, tenure) and fits relational storage well.

**Consequence:** Migrate to PostgreSQL if concurrent writes become a bottleneck (unlikely for single-server deployment).

---

## ADR-07: ChromaDB for Semantic Cache

**Decision:** Use a dedicated ChromaDB collection (`verified_answers`) for the verified Q&A cache.

**Alternatives considered:**
- Separate Pinecone/Weaviate instance
- SQLite with embedding column
- In-memory cache

**Rationale:** Already using ChromaDB for document retrieval. Adding a collection is a natural extension. Similarity search over cached answers is the core use case — ChromaDB handles this natively.

**Consequence:** Verified answers collection shares the ChromaDB instance. No additional infrastructure.

---

## ADR-08: Two-Tier Similarity Thresholds for Cache

**Decision:** Two thresholds for cache hits: ≥ 0.95 (high confidence, serve directly) and 0.88–0.94 (medium confidence, serve with disclaimer).

**Alternatives considered:**
- Single threshold (binary hit/miss)
- Three-tier with "maybe" zone

**Rationale:** A single threshold is too rigid — false positives erode trust, false negatives waste API calls. Two tiers provide a middle ground: high-confidence answers save cost with no UX penalty, medium-confidence answers provide value with appropriate caveats.

**Consequence:** Thresholds are configurable via `.env`. Will need tuning with real usage data. Model-dependent — may need adjustment if embeddings change.

---

## ADR-09: Streaming with Tool Use — Status SSE Events

**Decision:** Emit `{"status": "thinking", "detail": "Searching Employment Act..."}` SSE events before each tool call. Frontend renders as step-by-step status messages that disappear when streaming begins.

**Alternatives considered:**
- Silent processing (no feedback during tool calls)
- Fake "typing..." indicator
- Show raw tool call details

**Rationale:** Tool dispatch can take 1-3 seconds. Without feedback, the UI feels frozen. Status events provide transparency into what the system is doing without overwhelming users with technical details.

**Consequence:** Frontend needs to handle `status` SSE events alongside `token` events.

---

## ADR-10: Hardcoded EA Calculation Rules

**Decision:** Calculation tools use deterministic Python with hardcoded Employment Act rules (s43, s89, Part IX). Rules are versioned and documented in code.

**Alternatives considered:**
- Let Claude calculate from retrieved text (unreliable arithmetic)
- External rules engine
- Database-driven rules

**Rationale:** Employment Act calculations (leave entitlement, notice period) have precise formulas that shouldn't be left to LLM arithmetic. Hardcoding ensures deterministic, auditable results.

**Consequence:** Rules may change when EA is amended. Mitigated with admin alerts when EA is re-ingested. Rules must be manually verified and updated.

---

## ADR-11: DBSCAN for FAQ Clustering

**Decision:** Use DBSCAN (density-based clustering) with cosine distance on BGE embeddings for FAQ pattern detection.

**Alternatives considered:**
- K-Means (requires specifying k)
- Hierarchical clustering (expensive at scale)
- Simple frequency counting (misses semantic similarity)

**Rationale:** DBSCAN doesn't require specifying the number of clusters, handles noise naturally, and works well with cosine distance on embeddings. FAQ patterns are inherently variable in count — density-based clustering fits naturally.

**Consequence:** DBSCAN's `eps` parameter (0.3) needs tuning with real data. Capped at 500 most recent queries for performance.

---

## ADR-12: Phase 4 Deferral (Query Expansion + Contextual Compression)

**Decision:** Defer Phase 4A (query expansion) and 4B (contextual compression) until retrieval quality metrics justify them.

**Rationale:** The tool-based architecture in Phase 2 already provides intelligent query routing — Claude decides which collection to search and with what terms. Adding query expansion (extra Haiku call per retrieval) and compression (re-embedding) introduces overhead that isn't justified without evidence of a recall problem.

**Consequence:** Phase 4C (metadata filtering) shipped with Phase 2 as it was low-cost. 4A/4B remain documented in the plan for future activation.
