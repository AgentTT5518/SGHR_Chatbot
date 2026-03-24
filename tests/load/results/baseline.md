# Load Test Baseline

**Date:** 2026-03-24
**Status:** Infrastructure validated, pending full Locust run

## Infrastructure

- **Mock LLM mode:** Implemented via `MOCK_LLM=true` env var
  - Bypasses Anthropic API entirely
  - Returns canned response: "This is a mock response for load testing..."
  - Still creates sessions and persists messages in SQLite
  - Validated via `tests/load/test_mock_llm.py` (3 tests passing)

- **Locust scenarios:** 3 user classes validated (syntax + logic)
  - `ChatUser` (weight=6): SSE stream consumption, session reuse
  - `AdminUser` (weight=2): Collection stats, feedback list/stats
  - `FeedbackUser` (weight=2): Session setup → feedback submission

## How to Run

```bash
# Install locust
pip install -r tests/load/requirements-load.txt

# Start backend with mock LLM
MOCK_LLM=true uvicorn backend.main:app --port 8000

# Run Locust (web UI)
locust -f tests/load/locustfile.py --host http://localhost:8000

# Run Locust (headless, 10 users, 60s)
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --headless \
  --users 10 \
  --spawn-rate 2 \
  --run-time 60s
```

## Baseline Benchmarks (TBD)

Run the headless command above and record:

| Metric | Value |
|--------|-------|
| p50 latency | — |
| p95 latency | — |
| p99 latency | — |
| Throughput (req/s) | — |
| Error rate (%) | — |
| Test duration | — |
| Total requests | — |

Fill in after first Locust run with `MOCK_LLM=true`.
