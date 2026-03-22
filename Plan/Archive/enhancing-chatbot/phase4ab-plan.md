# Plan: Phase 4A/4B — Query Expansion & Contextual Compression

**Status:** Complete
**Created:** 2026-03-21
**Feature Branch:** `feature/enhancing-chatbot-retrieval-quality`

---

## Context

Phases 1-3 of the Enhancing Chatbot feature are complete. Phase 4A (Query Expansion) and 4B (Contextual Compression) were originally deferred until retrieval quality metrics justified them. We're now proceeding proactively as standard RAG best practices — both features are toggleable via config.

**Problem:** The current retrieval pipeline embeds the user's query as-is and returns chunks by similarity. This misses synonym coverage (e.g., "annual leave" vs "vacation" vs "PTO") and can return marginally relevant chunks that waste context window budget.

**Solution:**
- **4A:** Generate 2-3 Haiku rephrasings before retrieval, retrieve for each variant, merge with RRF
- **4B:** After retrieval, re-score chunks by embedding similarity to the original query, drop low-relevance results

---

## Data Flow

```
retrieval_tools.py (tool handler)
  │
  ├─ [4A] query_expander.expand(query)      → [original, rephrasing1, rephrasing2]
  │
  ├─ retriever.retrieve_multi(queries)       → N retrievals (parallel) + generalized RRF merge → cap at 8
  │
  ├─ [4B] compressor.compress(q_emb, chunks) → filter by cosine sim vs stored embeddings
  │         (replaces _apply_threshold when enabled)
  │
  └─ _format_results(compressed_chunks)      → formatted text with citations
```

---

## Implementation Steps

### Step 1: Config settings
**File:** `backend/config.py`

Add 4 settings:
```python
# Phase 4A: Query Expansion
use_query_expansion: bool = True
query_expansion_count: int = 3

# Phase 4B: Contextual Compression
use_contextual_compression: bool = True
compression_threshold: float = 0.45  # min cosine similarity to keep
```

Threshold rationale: BGE normalized embeddings produce cosine similarities of 0.5-0.8 for relevant HR content. Starting at 0.45 is conservative — filters only clearly irrelevant chunks. Tune after testing with real queries.

Also add placeholders to `.env.example`.

### Step 2: Update vector_store.py to optionally return embeddings
**File:** `backend/retrieval/vector_store.py`

Add `include_embeddings: bool = False` parameter to `query()`. When True, add `"embeddings"` to the `include` list and return `embedding` field in each result dict. This avoids re-embedding chunk texts in the compressor (Option A — uses stored embeddings from ChromaDB).

### Step 3: Generalize RRF + add retrieve_multi in retriever.py
**File:** `backend/retrieval/retriever.py`

- Refactor `_reciprocal_rank_fusion(semantic, keyword)` → `_reciprocal_rank_fusion(*ranked_lists)` to accept N lists
- **Fix dedup key:** Use `doc["id"]` (ChromaDB chunk ID) as the primary key, falling back to `doc["text"][:100]` only if `id` is missing. This avoids the 100-char prefix collision risk, especially when multiple query variants retrieve the same chunks
- Existing 2-list hybrid path still works (passes 2 lists)
- Add `retrieve_multi(queries, n_per_collection=10, collection=None, section_filter=None) -> list[dict]`:
  - If `collection` is set, calls `retrieve_from_collection` per query; else calls `retrieve` per query
  - **Runs queries in parallel** using `concurrent.futures.ThreadPoolExecutor` (embedding + ChromaDB calls are CPU/IO bound, not async)
  - Merges all result sets with generalized RRF
  - **Caps at 8 results** after RRF merge (same as current pipeline)
  - One function with optional `collection` param instead of two separate functions

### Step 4: Create query expander
**File:** `backend/retrieval/query_expander.py` (new)

- `async def expand(query: str) -> list[str]` — calls Haiku to generate rephrasings
- Prompt instructs Haiku to produce HR/Singapore-employment synonym rephrasings, one per line, no numbering
- Returns `[original_query, rephrasing1, ...]`
- Best-effort: on any error, log and return `[query]`
- Respects `settings.use_query_expansion` and `settings.query_expansion_count`
- Uses structured logger (`retrieval.query_expander`)

### Step 5: Create contextual compressor
**File:** `backend/retrieval/compressor.py` (new)

- `def compress(query_embedding: list[float], chunks: list[dict], threshold: float | None = None) -> list[dict]`
- Takes the **query embedding** as input (caller passes it, avoiding a duplicate `embed_query` call)
- Uses **stored embeddings** from chunks (the `embedding` field returned by `vector_store.query()` when `include_embeddings=True`)
- Computes cosine similarity via dot product (BGE embeddings are normalized)
- Drops chunks below threshold (default from `settings.compression_threshold`)
- Adds `relevance_score` field to surviving chunks
- Returns filtered list sorted by relevance_score descending
- **Replaces `_apply_threshold`** when enabled — it's a stricter, more principled filter. When compression is disabled, `_apply_threshold` continues to apply as before
- Uses structured logger (`retrieval.compressor`)

### Step 6: Wire into retrieval tools
**File:** `backend/chat/tools/retrieval_tools.py`

- Add `async def _enhanced_retrieve(query, collection=None, n=10, section_filter=None) -> list[dict]` helper:
  1. Embed the original query once with `embed_query()` — cache this embedding
  2. If `use_query_expansion`: call `expand(query)` → expanded queries list; else `[query]`
  3. If len(queries) > 1: call `retrieve_multi(queries, collection=collection, section_filter=section_filter)` (which runs parallel retrievals + RRF merge + cap at 8)
  4. Else: call existing `retrieve_from_collection` or `retrieve` (unchanged path)
  5. If `use_contextual_compression`: pass `include_embeddings=True` to the retrieve call (needs plumbing), then call `compress(q_embedding, chunks)`. This replaces `_apply_threshold`.
  6. Return final chunks
- Modify `search_employment_act`, `search_mom_guidelines`, `search_all_policies` to use `_enhanced_retrieve`
- `get_legal_definitions` unchanged (targeted Section 2 lookup)

### Step 7: Plumb include_embeddings through retriever
**File:** `backend/retrieval/retriever.py`

- Add `include_embeddings: bool = False` parameter to `retrieve`, `retrieve_from_collection`, `retrieve_multi`, `_hybrid_retrieve`, `_semantic_retrieve`
- Pass through to `vector_store.query(..., include_embeddings=include_embeddings)`
- Only `_enhanced_retrieve` (when compression is enabled) passes `True`

### Step 8: Adjust _apply_threshold interaction
**File:** `backend/retrieval/retriever.py`

- When `include_embeddings=True` (i.e., compression will run downstream), skip `_apply_threshold` in `retrieve_from_collection` and let the compressor handle filtering
- When `include_embeddings=False` (compression disabled), `_apply_threshold` applies as before
- This prevents double-filtering with different semantics

### Step 9: Tests
- `tests/retrieval/test_query_expander.py` — mock Anthropic client, verify expand returns original + N, verify best-effort fallback, verify respects count setting
- `tests/retrieval/test_compressor.py` — provide pre-computed embeddings in chunks, verify filtering by threshold, verify relevance_score, edge cases
- Extend existing retriever tests — test generalized RRF with 3+ lists, test `retrieve_multi`, test `id`-based dedup key

### Step 10: Update docs
- Update `ARCHITECTURE.md` — Component Map (query_expander, compressor) + Feature Log
- Update `.env.example` with new settings

---

## Files Summary

| Action | File | Description |
|--------|------|-------------|
| Create | `backend/retrieval/query_expander.py` | Haiku-based query expansion |
| Create | `backend/retrieval/compressor.py` | Embedding similarity chunk filtering |
| Create | `tests/retrieval/test_query_expander.py` | Expander tests |
| Create | `tests/retrieval/test_compressor.py` | Compressor tests |
| Modify | `backend/config.py` | 4 new settings |
| Modify | `backend/retrieval/vector_store.py` | include_embeddings option in query() |
| Modify | `backend/retrieval/retriever.py` | Generalized RRF (id-based keys) + retrieve_multi (parallel) + include_embeddings plumbing + _apply_threshold bypass |
| Modify | `backend/chat/tools/retrieval_tools.py` | _enhanced_retrieve helper wrapping expand → retrieve → compress |
| Modify | `ARCHITECTURE.md` | Component Map + Feature Log |
| Modify | `.env.example` | New setting placeholders |

---

## Latency Impact

| Component | Added Latency | Mitigation |
|-----------|--------------|------------|
| Haiku query expansion | ~200-500ms | Best-effort; async; skipped when disabled |
| 3x ChromaDB queries | ~50-150ms | **Run in parallel** via ThreadPoolExecutor |
| Cosine similarity computation | ~1-2ms | Dot product on 8 vectors — negligible |
| **Total** | **~250-650ms** | Acceptable for HR chatbot; configurable off |

---

## Acceptance Criteria

**4A:**
- [ ] When enabled, Haiku generates 2-3 rephrasings per retrieval tool query
- [ ] All rephrasings + original retrieved **in parallel** and merged via generalized RRF
- [ ] RRF uses chunk `id` as dedup key (not text prefix)
- [ ] RRF output capped at 8 results
- [ ] Haiku failure → retrieval proceeds with original query only (no user-visible error)
- [ ] When disabled, retrieval identical to current behavior

**4B:**
- [ ] Chunks re-scored by cosine similarity using **stored embeddings** from ChromaDB (no re-embedding)
- [ ] Chunks below threshold dropped; replaces `_apply_threshold` when enabled
- [ ] No LLM call — embedding math only
- [ ] When disabled, `_apply_threshold` applies as before

**Both:**
- [ ] All existing tests pass
- [ ] New tests cover happy paths, error paths, and config toggles
- [ ] ARCHITECTURE.md updated
- [ ] `.env.example` updated

---

## Verification

1. `python -m pytest tests/ -v` — all pass
2. `ruff check backend/` — clean
3. Start backend with both features enabled, send HR queries, verify expanded queries in logs
4. Disable each feature via .env, verify fallback to original behavior
5. Kill Anthropic API (or use invalid key), verify query expansion degrades gracefully
6. Check logs for `retrieval.query_expander` and `retrieval.compressor` entries
