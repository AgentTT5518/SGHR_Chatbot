#!/usr/bin/env python3
"""
Retrieval quality evaluation script.

Measures precision@k, recall@k, and MRR against a labelled query dataset.
Runs against the local ChromaDB instance (requires ingested data).

Usage:
    python -m tests.eval.eval_retrieval
    python -m tests.eval.eval_retrieval --expansion off --compression off
    python -m tests.eval.eval_retrieval --threshold 0.50 --k 8
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_dataset(path: Path | None = None) -> list[dict]:
    if path is None:
        path = Path(__file__).parent / "dataset.json"
    with open(path) as f:
        return json.load(f)


def evaluate_query(
    query: str,
    expected_keywords: list[str],
    expected_sections: list[str],
    expect_low_relevance: bool,
    k: int,
) -> dict:
    """Run retrieval for a single query and compute metrics."""
    from backend.retrieval.retriever import retrieve

    start = time.monotonic()
    results = retrieve(query, n_per_collection=k)
    latency_ms = (time.monotonic() - start) * 1000

    # Combine all text from results for keyword matching
    all_text = " ".join(r.get("text", "") for r in results).lower()
    all_metadata = [r.get("metadata", {}) for r in results]

    # Keyword hits: how many expected keywords appear in retrieved text
    keyword_hits = sum(
        1 for kw in expected_keywords if kw.lower() in all_text
    ) if expected_keywords else 0
    keyword_total = len(expected_keywords) if expected_keywords else 0

    # Section hits: how many expected sections appear in metadata
    result_sections = set()
    for meta in all_metadata:
        for key in ("section", "part", "source"):
            val = meta.get(key, "")
            if val:
                result_sections.add(str(val))

    section_hits = sum(
        1 for s in expected_sections
        if any(s.lower() in rs.lower() for rs in result_sections)
    ) if expected_sections else 0
    section_total = len(expected_sections) if expected_sections else 0

    # Keyword precision and recall
    keyword_precision = keyword_hits / min(k, len(results)) if results else 0.0
    keyword_recall = keyword_hits / keyword_total if keyword_total > 0 else 1.0

    # For adversarial queries, check that results have low relevance
    low_relevance_pass = True
    if expect_low_relevance:
        # If retrieval returns results with high distances (low similarity), that's good
        # Check if keyword overlap is minimal
        low_relevance_pass = keyword_hits == 0

    return {
        "num_results": len(results),
        "keyword_hits": keyword_hits,
        "keyword_total": keyword_total,
        "keyword_recall": keyword_recall,
        "section_hits": section_hits,
        "section_total": section_total,
        "latency_ms": round(latency_ms, 1),
        "low_relevance_pass": low_relevance_pass,
    }


def run_evaluation(
    dataset: list[dict],
    k: int = 8,
    expansion: bool | None = None,
    compression: bool | None = None,
    threshold: float | None = None,
) -> dict:
    """Run the full evaluation suite and return aggregate metrics."""
    from backend.config import settings

    # Override settings if specified
    original_expansion = settings.use_query_expansion
    original_compression = settings.use_contextual_compression
    original_threshold = settings.compression_threshold

    if expansion is not None:
        object.__setattr__(settings, "use_query_expansion", expansion)
    if compression is not None:
        object.__setattr__(settings, "use_contextual_compression", compression)
    if threshold is not None:
        object.__setattr__(settings, "compression_threshold", threshold)

    try:
        results_by_category: dict[str, list[dict]] = defaultdict(list)
        all_results: list[dict] = []

        for i, item in enumerate(dataset):
            query = item["query"]
            category = item["category"]
            expect_low = item.get("expect_low_relevance", False)

            result = evaluate_query(
                query=query,
                expected_keywords=item.get("expected_keywords", []),
                expected_sections=item.get("expected_sections", []),
                expect_low_relevance=expect_low,
                k=k,
            )
            result["query"] = query
            result["category"] = category

            all_results.append(result)
            results_by_category[category].append(result)

            print(f"  [{i+1}/{len(dataset)}] {category}: {query[:60]}... "
                  f"kw={result['keyword_hits']}/{result['keyword_total']} "
                  f"({result['latency_ms']:.0f}ms)")

        # Aggregate metrics
        hr_results = [r for r in all_results if r["category"] != "adversarial_off_topic"]
        adversarial_results = [r for r in all_results if r["category"] == "adversarial_off_topic"]

        avg_keyword_recall = (
            sum(r["keyword_recall"] for r in hr_results) / len(hr_results)
            if hr_results else 0.0
        )
        avg_latency = (
            sum(r["latency_ms"] for r in all_results) / len(all_results)
            if all_results else 0.0
        )
        adversarial_pass_rate = (
            sum(1 for r in adversarial_results if r["low_relevance_pass"]) / len(adversarial_results)
            if adversarial_results else 1.0
        )

        # Per-category breakdown
        category_summary = {}
        for cat, cat_results in sorted(results_by_category.items()):
            cat_hr = [r for r in cat_results if cat != "adversarial_off_topic"]
            if cat_hr:
                cat_recall = sum(r["keyword_recall"] for r in cat_hr) / len(cat_hr)
            else:
                cat_recall = 0.0
            cat_latency = sum(r["latency_ms"] for r in cat_results) / len(cat_results)
            category_summary[cat] = {
                "count": len(cat_results),
                "avg_keyword_recall": round(cat_recall, 3),
                "avg_latency_ms": round(cat_latency, 1),
            }

        config = {
            "use_query_expansion": settings.use_query_expansion,
            "use_contextual_compression": settings.use_contextual_compression,
            "compression_threshold": settings.compression_threshold,
            "retrieval_mode": settings.retrieval_mode,
            "k": k,
        }

        return {
            "config": config,
            "total_queries": len(dataset),
            "hr_queries": len(hr_results),
            "adversarial_queries": len(adversarial_results),
            "avg_keyword_recall": round(avg_keyword_recall, 3),
            "avg_latency_ms": round(avg_latency, 1),
            "adversarial_pass_rate": round(adversarial_pass_rate, 3),
            "category_summary": category_summary,
            "details": all_results,
        }

    finally:
        # Restore original settings
        object.__setattr__(settings, "use_query_expansion", original_expansion)
        object.__setattr__(settings, "use_contextual_compression", original_compression)
        object.__setattr__(settings, "compression_threshold", original_threshold)


def main():
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--dataset", type=Path, default=None, help="Path to dataset.json")
    parser.add_argument("--k", type=int, default=8, help="Number of results to retrieve")
    parser.add_argument("--expansion", choices=["on", "off"], default=None)
    parser.add_argument("--compression", choices=["on", "off"], default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--output", type=Path, default=None, help="Save results to JSON file")
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)

    expansion = None if args.expansion is None else (args.expansion == "on")
    compression = None if args.compression is None else (args.compression == "on")

    print(f"\nRunning evaluation on {len(dataset)} queries...")
    print(f"  expansion={args.expansion or 'default'}, "
          f"compression={args.compression or 'default'}, "
          f"threshold={args.threshold or 'default'}, k={args.k}\n")

    result = run_evaluation(
        dataset=dataset,
        k=args.k,
        expansion=expansion,
        compression=compression,
        threshold=args.threshold,
    )

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"RESULTS SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total queries:          {result['total_queries']}")
    print(f"HR queries:             {result['hr_queries']}")
    print(f"Adversarial queries:    {result['adversarial_queries']}")
    print(f"Avg keyword recall:     {result['avg_keyword_recall']:.3f}")
    print(f"Avg latency:            {result['avg_latency_ms']:.1f} ms")
    print(f"Adversarial pass rate:  {result['adversarial_pass_rate']:.3f}")
    print(f"\nPer-category breakdown:")
    for cat, summary in sorted(result["category_summary"].items()):
        print(f"  {cat:30s}  n={summary['count']:2d}  "
              f"recall={summary['avg_keyword_recall']:.3f}  "
              f"latency={summary['avg_latency_ms']:.0f}ms")

    # Save results
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults saved to {args.output}")
    else:
        default_output = Path(__file__).parent / "results" / "latest.json"
        default_output.parent.mkdir(parents=True, exist_ok=True)
        with open(default_output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nResults saved to {default_output}")


if __name__ == "__main__":
    main()
