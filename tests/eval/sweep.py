#!/usr/bin/env python3
"""
Two-stage parameter sweep for retrieval quality tuning.

Stage 1 (fast, no API calls):
  Sweep with query expansion OFF across COMPRESSION_THRESHOLD, THRESHOLD_FLOOR,
  and RRF_K combinations. Pure retrieval, no Haiku calls.

Stage 2 (top N only):
  Take the top-5 configs from Stage 1, test each with expansion ON at
  QUERY_EXPANSION_COUNT [2, 3, 4].

Usage:
    python -m tests.eval.sweep
    python -m tests.eval.sweep --stage 1          # Stage 1 only
    python -m tests.eval.sweep --stage 2 --top 3  # Stage 2 with top-3
    python -m tests.eval.sweep --output results/sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.eval.eval_retrieval import load_dataset, run_evaluation  # noqa: E402


# Stage 1 parameter grid (no expansion)
COMPRESSION_THRESHOLDS = [0.35, 0.40, 0.45, 0.50, 0.55]
THRESHOLD_FLOORS = [0.20, 0.25, 0.30]
RRF_KS = [40, 60, 80]

# Stage 2 expansion counts
EXPANSION_COUNTS = [2, 3, 4]


def run_stage_1(dataset: list[dict], k: int = 8) -> list[dict]:
    """Run Stage 1: sweep with expansion OFF."""
    from backend.config import settings

    combos = list(product(COMPRESSION_THRESHOLDS, THRESHOLD_FLOORS, RRF_KS))
    print(f"\n{'=' * 60}")
    print(f"STAGE 1: {len(combos)} configs (expansion OFF)")
    print(f"{'=' * 60}\n")

    results = []
    for i, (ct, tf, rrf) in enumerate(combos, 1):
        # Override settings for this run
        object.__setattr__(settings, "compression_threshold", ct)
        object.__setattr__(settings, "threshold_floor", tf)
        object.__setattr__(settings, "rrf_k", rrf)

        label = f"ct={ct:.2f} tf={tf:.2f} rrf_k={rrf}"
        print(f"[{i}/{len(combos)}] {label}")

        start = time.monotonic()
        result = run_evaluation(
            dataset=dataset,
            k=k,
            expansion=False,
            compression=True,
            threshold=ct,
        )
        elapsed = time.monotonic() - start

        entry = {
            "stage": 1,
            "compression_threshold": ct,
            "threshold_floor": tf,
            "rrf_k": rrf,
            "expansion": False,
            "expansion_count": None,
            "avg_keyword_recall": result["avg_keyword_recall"],
            "avg_latency_ms": result["avg_latency_ms"],
            "adversarial_pass_rate": result["adversarial_pass_rate"],
            "sweep_time_s": round(elapsed, 1),
        }
        results.append(entry)
        print(f"  recall={entry['avg_keyword_recall']:.3f}  "
              f"latency={entry['avg_latency_ms']:.0f}ms  "
              f"adversarial={entry['adversarial_pass_rate']:.3f}  "
              f"({elapsed:.1f}s)\n")

    # Sort by recall descending, then latency ascending
    results.sort(key=lambda r: (-r["avg_keyword_recall"], r["avg_latency_ms"]))
    return results


def run_stage_2(
    dataset: list[dict],
    stage1_results: list[dict],
    top_n: int = 5,
    k: int = 8,
) -> list[dict]:
    """Run Stage 2: test top-N configs from Stage 1 with expansion ON."""
    from backend.config import settings

    top_configs = stage1_results[:top_n]
    combos = [(cfg, ec) for cfg in top_configs for ec in EXPANSION_COUNTS]

    print(f"\n{'=' * 60}")
    print(f"STAGE 2: {len(combos)} configs (expansion ON, top-{top_n} from Stage 1)")
    print(f"{'=' * 60}\n")

    results = []
    for i, (cfg, ec) in enumerate(combos, 1):
        ct = cfg["compression_threshold"]
        tf = cfg["threshold_floor"]
        rrf = cfg["rrf_k"]

        object.__setattr__(settings, "compression_threshold", ct)
        object.__setattr__(settings, "threshold_floor", tf)
        object.__setattr__(settings, "rrf_k", rrf)
        object.__setattr__(settings, "query_expansion_count", ec)

        label = f"ct={ct:.2f} tf={tf:.2f} rrf_k={rrf} expansion_count={ec}"
        print(f"[{i}/{len(combos)}] {label}")

        start = time.monotonic()
        result = run_evaluation(
            dataset=dataset,
            k=k,
            expansion=True,
            compression=True,
            threshold=ct,
        )
        elapsed = time.monotonic() - start

        entry = {
            "stage": 2,
            "compression_threshold": ct,
            "threshold_floor": tf,
            "rrf_k": rrf,
            "expansion": True,
            "expansion_count": ec,
            "avg_keyword_recall": result["avg_keyword_recall"],
            "avg_latency_ms": result["avg_latency_ms"],
            "adversarial_pass_rate": result["adversarial_pass_rate"],
            "sweep_time_s": round(elapsed, 1),
        }
        results.append(entry)
        print(f"  recall={entry['avg_keyword_recall']:.3f}  "
              f"latency={entry['avg_latency_ms']:.0f}ms  "
              f"adversarial={entry['adversarial_pass_rate']:.3f}  "
              f"({elapsed:.1f}s)\n")

    results.sort(key=lambda r: (-r["avg_keyword_recall"], r["avg_latency_ms"]))
    return results


def main():
    parser = argparse.ArgumentParser(description="Two-stage parameter sweep")
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--stage", type=int, choices=[1, 2], default=None,
                        help="Run only this stage (default: both)")
    parser.add_argument("--top", type=int, default=5,
                        help="Number of top Stage 1 configs to test in Stage 2")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    dataset = load_dataset(args.dataset)

    all_results = {"stage1": [], "stage2": []}

    if args.stage is None or args.stage == 1:
        stage1 = run_stage_1(dataset, k=args.k)
        all_results["stage1"] = stage1

        print(f"\n{'=' * 60}")
        print("STAGE 1 TOP-5:")
        for i, r in enumerate(stage1[:5], 1):
            print(f"  {i}. ct={r['compression_threshold']:.2f} "
                  f"tf={r['threshold_floor']:.2f} "
                  f"rrf_k={r['rrf_k']}  "
                  f"recall={r['avg_keyword_recall']:.3f}  "
                  f"latency={r['avg_latency_ms']:.0f}ms")

    if args.stage is None or args.stage == 2:
        if not all_results["stage1"]:
            # Load from previous run
            default_output = Path(__file__).parent / "results" / "sweep.json"
            if default_output.exists():
                with open(default_output) as f:
                    prev = json.load(f)
                all_results["stage1"] = prev.get("stage1", [])
            if not all_results["stage1"]:
                print("Error: No Stage 1 results available. Run Stage 1 first.")
                sys.exit(1)

        stage2 = run_stage_2(dataset, all_results["stage1"], top_n=args.top, k=args.k)
        all_results["stage2"] = stage2

        print(f"\n{'=' * 60}")
        print("STAGE 2 TOP-5:")
        for i, r in enumerate(stage2[:5], 1):
            print(f"  {i}. ct={r['compression_threshold']:.2f} "
                  f"tf={r['threshold_floor']:.2f} "
                  f"rrf_k={r['rrf_k']} "
                  f"exp={r['expansion_count']}  "
                  f"recall={r['avg_keyword_recall']:.3f}  "
                  f"latency={r['avg_latency_ms']:.0f}ms")

    # Save results
    output_path = args.output or Path(__file__).parent / "results" / "sweep.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
