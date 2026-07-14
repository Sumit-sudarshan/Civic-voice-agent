"""
Civic Voice Agent — Model Comparison Runner (Appendix Item 6 / bug_fix.md Phase 3)

Runs run_eval.py sequentially against two (or more) models and prints a
side-by-side comparison table — exactly the before/after story needed for
the write-up's evaluation section.

Usage:
    cd backend
    python eval/run_eval_compare.py
    python eval/run_eval_compare.py --models qwen2.5:1.5b phi3:mini
    python eval/run_eval_compare.py --models qwen2.5:1.5b phi3:mini gemma2:2b

Output:
    - Prints a readable side-by-side table to stdout
    - Saves a combined JSON comparison report to eval/reports/compare_<timestamp>.json
"""
import argparse
import json
import os
import sys
import time

# Ensure backend/ is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from eval.run_eval import run_eval


DEFAULT_MODELS = ["qwen2.5:1.5b", "phi3:mini"]


def parse_args():
    parser = argparse.ArgumentParser(description="Compare eval results across LLM models")
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help=f"Models to compare (default: {' '.join(DEFAULT_MODELS)})",
    )
    parser.add_argument(
        "--suite", default="core", choices=["core", "full"],
        help="core = ~245 fast cases (default), full = ~1,045 cases (slow)",
    )
    return parser.parse_args()


def _pct(val, total, decimals=1):
    if not total:
        return "—"
    return f"{val / total * 100:.{decimals}f}%"


def print_comparison_table(reports: list[dict]):
    """Print a side-by-side comparison of eval results for multiple models."""
    if not reports:
        print("No results to compare.")
        return

    col_w = max(22, max(len(r["model"]) for r in reports) + 4)
    divider = "+" + "+".join(["-" * col_w] * (len(reports) + 1)) + "+"

    def row(label, *values):
        cells = [f"  {label:<{col_w - 2}}"] + [f"  {str(v):<{col_w - 2}}" for v in values]
        return "|" + "|".join(cells) + "|"

    headers = ["Metric"] + [r["model"] for r in reports]

    print()
    print("=" * (col_w * (len(reports) + 1) + len(reports) + 2))
    print("  Model Evaluation Comparison")
    print("=" * (col_w * (len(reports) + 1) + len(reports) + 2))
    print(divider)
    print(row(*headers))
    print(divider)

    # Gatekeeper
    print(row("Gatekeeper accuracy",
        *[f"{r['gatekeeper']['accuracy_pct']:.1f}%  ({r['gatekeeper']['correct']}/{r['gatekeeper']['total']})"
          for r in reports]))

    # Category classification
    print(row("Category accuracy",
        *[f"{r['classification']['accuracy_pct']:.1f}%  ({r['classification']['correct']}/{r['classification']['total']})"
          for r in reports]))

    # Urgency
    print(row("Urgency exact match",
        *[f"{r['urgency']['exact_match_pct']:.1f}%  ({r['urgency']['exact_correct']}/{r['urgency']['total']})"
          for r in reports]))
    print(row("Urgency within-one",
        *[f"{r['urgency']['within_one_pct']:.1f}%  ({r['urgency']['within_one_correct']}/{r['urgency']['total']})"
          for r in reports]))

    # Dedup
    print(row("Dedup precision",
        *[f"{r['dedup']['precision']:.3f}  (TP={r['dedup']['tp']} FP={r['dedup']['fp']})"
          for r in reports]))
    print(row("Dedup recall",
        *[f"{r['dedup']['recall']:.3f}  (FN={r['dedup']['fn']})"
          for r in reports]))

    # Timing
    print(row("LLM time (s)",
        *[f"{r['elapsed_llm_seconds']:.1f}s  (total {r['elapsed_total_seconds']:.1f}s)"
          for r in reports]))

    print(divider)

    # Winner detection per metric
    print()
    print("  Highlights:")
    metrics = {
        "Gatekeeper accuracy":  [r["gatekeeper"]["accuracy_pct"] for r in reports],
        "Category accuracy":    [r["classification"]["accuracy_pct"] for r in reports],
        "Urgency exact match":  [r["urgency"]["exact_match_pct"] for r in reports],
        "Urgency within-one":   [r["urgency"]["within_one_pct"] for r in reports],
        "Speed (lower=better)": [r["elapsed_llm_seconds"] for r in reports],
    }

    for metric, values in metrics.items():
        if metric == "Speed (lower=better)":
            winner_idx = values.index(min(values))
        else:
            winner_idx = values.index(max(values))
        winner_model = reports[winner_idx]["model"]
        winner_val   = values[winner_idx]
        print(f"    {metric:<28}: ✓ {winner_model}  ({winner_val:.1f})")

    print()


def main():
    args = parse_args()
    models = args.models

    print(f"\n  Running evaluation for {len(models)} model(s): {', '.join(models)}")
    print(f"  This will take several minutes per model — please wait.\n")

    reports = []
    for model in models:
        print(f"\n{'─'*55}")
        print(f"  Evaluating: {model}")
        print(f"{'─'*55}")
        try:
            report = run_eval(model_override=model, suite=args.suite)
            reports.append(report)
        except Exception as e:
            print(f"  ERROR evaluating {model}: {e}")
            continue

    if len(reports) < 2:
        print("\n  Not enough successful runs to compare.")
        return

    print_comparison_table(reports)

    # Save combined comparison JSON
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    compare_path = os.path.join(reports_dir, f"compare_{ts}.json")

    with open(compare_path, "w") as f:
        json.dump({"models": [r["model"] for r in reports], "results": reports}, f, indent=2)

    print(f"  Comparison report saved → {compare_path}\n")


if __name__ == "__main__":
    main()
