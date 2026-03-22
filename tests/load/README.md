# Load Testing — SGHR Chatbot

Load tests use [Locust](https://locust.io/) to simulate concurrent users hitting the FastAPI backend.

## Prerequisites

Install the load-test dependencies into a **separate** virtual environment (or the same one, but note these are intentionally kept out of the main `requirements.txt`):

```bash
pip install -r tests/requirements-load.txt
```

## Mocking the Anthropic Client

**Do not run load tests against the live Anthropic API.** Each chat request triggers a Claude API call, which is slow and expensive under load.

Before starting a load run, configure the backend to use a mock LLM. Recommended approach:

1. Set the environment variable `MOCK_LLM=1` before starting the backend.
2. In the backend startup code, check for this flag and replace the real Anthropic client with a stub that yields a deterministic SSE token stream (e.g., a fixed answer split into tokens with short delays).

This gives realistic streaming behavior without incurring API costs or hitting rate limits.

## Running the Tests

Start the backend (with mocked LLM):

```bash
MOCK_LLM=1 uvicorn backend.main:app --port 8000
```

Then in a separate terminal, run Locust:

```bash
# Web UI mode (open http://localhost:8089 in your browser)
locust -f tests/load/locustfile.py

# Headless mode (e.g., 50 users, ramp up 5/s, run for 2 minutes)
locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 2m
```

The default host is `http://localhost:8000`. Override with `--host`:

```bash
locust -f tests/load/locustfile.py --host http://staging.example.com:8000
```

## Test Scenarios

| User Class     | Weight | Endpoint(s)                                              | Notes                                      |
|----------------|--------|----------------------------------------------------------|--------------------------------------------|
| `ChatUser`     | 6      | `POST /api/chat`                                         | Sends questions, consumes full SSE stream   |
| `AdminUser`    | 2      | `GET /admin/collections`, `/admin/feedback`, `/admin/feedback/stats` | Requires `X-Admin-Key: dev-only-key` header |
| `FeedbackUser` | 2      | `POST /api/feedback`                                     | Creates a session first, then submits ratings |

## Baseline Expectations

With a mocked LLM on a single-core dev machine:

| Metric               | Target          |
|----------------------|-----------------|
| Chat p95 latency     | < 500 ms        |
| Admin p95 latency    | < 100 ms        |
| Feedback p95 latency | < 200 ms        |
| Error rate           | < 1%            |
| Throughput           | 50+ req/s total |

These are rough starting points. Adjust based on your hardware, concurrency level, and whether the backend is running with `--workers` (multiple Uvicorn workers).

## Tips

- Increase Uvicorn workers for higher concurrency: `uvicorn backend.main:app --workers 4`
- Use `--tags chat` to run only chat scenarios: `locust -f tests/load/locustfile.py --tags chat`
- Export results to CSV: `locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 2m --csv=tests/load/results`
