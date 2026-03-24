# Retrieval Quality Tuning — Before/After Comparison

**Date:** 2026-03-24
**Dataset:** 55 queries (50 HR, 5 adversarial) across 24 categories

## Aggregate Metrics

| Metric | Raw Baseline | Enhanced Baseline (old defaults) | Tuned (new defaults) |
|--------|-------------|--------------------------------|---------------------|
| Avg keyword recall | 0.675 | 0.666 | **0.675** |
| Avg latency (ms) | 112 | 1559 | **120** |
| Adversarial pass rate | 1.000 | 1.000 | **1.000** |

- **Raw baseline:** expansion=off, compression=off (pure hybrid retrieval)
- **Enhanced baseline:** expansion=on (3 Haiku rephrasings), compression=on (threshold=0.45)
- **Tuned:** expansion=off, compression=on (threshold=0.35)

## Settings Changes

| Setting | Before | After | Reason |
|---------|--------|-------|--------|
| `USE_QUERY_EXPANSION` | true | **false** | +1.4s latency for <0.01 recall gain |
| `COMPRESSION_THRESHOLD` | 0.45 | **0.35** | More permissive; retains more relevant chunks |
| `THRESHOLD_FLOOR` | 0.25 | 0.25 | No change needed (insensitive in tested range) |
| `RRF_K` | 60 | 60 | No change needed (insensitive in tested range) |

## Key Findings

1. **Query expansion was net negative** with old defaults: recall dropped from 0.675 to 0.666. Expansion introduces borderline chunks that compression then filters, sometimes losing relevant results.

2. **Compression threshold sensitivity:** ct=0.50+ degrades recall (0.67, 0.567). ct=0.25-0.45 all yield 0.675 recall. ct=0.35 chosen as a balanced midpoint that filters noise while retaining context.

3. **threshold_floor and rrf_k are insensitive** across the tested ranges (tf=0.20-0.30, rrf_k=40-80). Current chunk distance distributions don't exercise these thresholds — all configs produce identical recall.

4. **Latency:** Expansion adds ~1.4s per query (Haiku API round-trip). Without expansion, latency is ~120ms including compression overhead (~8ms for cosine similarity filtering).

## Per-Category Comparison (select categories)

| Category | Raw Baseline | Enhanced (old) | Tuned |
|----------|-------------|---------------|-------|
| annual_leave | 0.778 | 0.611 | 0.778 |
| childcare_leave | 0.625 | 0.875 | 0.625 |
| definitions | 0.889 | 0.889 | 0.889 |
| disputes | 1.000 | 1.000 | 1.000 |
| maternity_leave | 0.375 | 0.375 | 0.375 |
| probation | 0.833 | 0.708 | 0.833 |
| sick_leave | 0.375 | 0.500 | 0.375 |

## Sweep Summary

- **Stage 1:** 45 configs (5 ct x 3 tf x 3 rrf_k), expansion OFF — recall range: 0.567-0.675
- **Stage 2:** 15 configs (top-5 x 3 expansion counts), expansion ON — best recall: 0.676
- **Conclusion:** Expansion provides marginal benefit (+0.001) at significant latency cost

## Bug Fixes Applied

1. **Module-level constants bug:** `retriever.py` froze `THRESHOLD_FLOOR`, `THRESHOLD_MULTIPLIER`, `_RRF_K`, `_MAX_RESULTS` at import time. Sweep parameter overrides were silently ignored. Fixed to read `settings.*` at call time.

2. **Eval pipeline bug:** `eval_retrieval.py` called `retriever.retrieve()` directly, bypassing expansion and compression. Fixed to use the full expand -> retrieve -> compress pipeline.
