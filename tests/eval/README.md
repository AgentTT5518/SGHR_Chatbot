# Retrieval Quality Evaluation

Measures how well the retrieval pipeline returns relevant HR content for user queries.

## Prerequisites

Requires an ingested ChromaDB instance with real documents:
```bash
python -m backend.ingestion.ingest_pipeline
```

## Running

```bash
# Default settings (uses current .env config)
python -m tests.eval.eval_retrieval

# Test with specific settings
python -m tests.eval.eval_retrieval --expansion off --compression off
python -m tests.eval.eval_retrieval --expansion on --compression on --threshold 0.50
python -m tests.eval.eval_retrieval --k 5  # top-5 instead of top-8

# Save to specific file
python -m tests.eval.eval_retrieval --output tests/eval/results/baseline.json
```

## Metrics

- **Keyword Recall**: Fraction of expected keywords found in retrieved chunks (per query, then averaged)
- **Adversarial Pass Rate**: Fraction of off-topic queries that correctly return no matching keywords
- **Latency**: Wall-clock time per retrieval call (includes expansion + compression if enabled)

## Dataset

`dataset.json` contains 55 labelled queries across categories:
- HR topics: annual leave, sick leave, notice period, definitions, eligibility, maternity/paternity/childcare leave, overtime, public holidays, probation, retrenchment, retirement, rest days, salary, disputes, KET, part-time, dismissal, working hours, CPF
- Adversarial: 5 off-topic queries (weather, US taxes, restaurants, history, cooking)

Each query has:
- `expected_keywords`: terms that should appear in relevant chunks
- `expected_sections`: Employment Act sections expected in metadata
- `expect_low_relevance`: true for adversarial queries

## Adding Queries

Add entries to `dataset.json` following the existing format. Include diverse phrasing for each category.

## Results

Results are saved to `tests/eval/results/` (gitignored). Each result file contains config, aggregate metrics, per-category breakdown, and per-query details.
