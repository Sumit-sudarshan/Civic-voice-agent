"""
Civic Voice Agent — Extraction Quality Rubric Scoring (eval_plan.md Phase D/12.2)

There's no automatic metric for extraction quality (no single correct phrasing for
issue_summary/location/affected_parties/ask), so this is a semi-manual tool: it runs
the extractor on a sample of valid cases and asks a human to score each field 1-5
against a rubric, then tallies mean + %>=4 per field.

Usage:
    cd backend
    python eval/score_extraction.py                      # sample 20 cases from core suite
    python eval/score_extraction.py --suite full --sample 40
    python eval/score_extraction.py --resume eval/reports/extraction_scores_20260101_120000.json

Rubric (score each field 1-5):
    5 = Fully correct, captures exactly what's in the text, no invention.
    4 = Correct and usable, minor phrasing awkwardness only.
    3 = Mostly correct but missing a detail a leader would want.
    2 = Partially wrong or vague enough to be unhelpful.
    1 = Wrong, or invented information not present in raw_text.

At each case, enter four space-separated scores for location/issue_summary/affected_parties/ask
(e.g. "5 5 4 5"), or:
    s  = skip this case (not counted)
    q  = save progress and quit (resume later with --resume)
"""
import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.pipeline.stages import run_extractor
from eval.run_eval import load_cases

FIELDS = ["location", "issue_summary", "affected_parties", "ask"]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="core", choices=["demo", "core", "full"])
    parser.add_argument("--sample", type=int, default=20, help="number of cases to score")
    parser.add_argument("--seed", type=int, default=42, help="random seed for sampling")
    parser.add_argument("--model", default=None)
    parser.add_argument("--resume", default=None, help="path to a previous extraction_scores_*.json to continue")
    return parser.parse_args()


def pick_sample(suite: str, sample: int, seed: int, already_scored_ids: set):
    cases = [c for c in load_cases(suite) if c["is_valid_submission"]]
    cases = [c for c in cases if c["id"] not in already_scored_ids]
    random.Random(seed).shuffle(cases)
    return cases[:sample]


def prompt_scores(case, extraction):
    print("\n" + "-" * 60)
    print(f"  [{case['id']}] {case['raw_text']}")
    if case.get("location"):
        print(f"  (citizen's confirmed location given to the model: {case['location']!r} — "
              f"'location' below should combine this with any extra detail from the text, not omit it)")
    print("-" * 60)
    for field in FIELDS:
        print(f"    {field:<18}: {getattr(extraction, field)!r}")
    print()
    raw = input("  Scores for location issue_summary affected_parties ask (1-5 each, or s/q): ").strip()
    if raw.lower() == "q":
        return "quit"
    if raw.lower() == "s" or not raw:
        return None
    parts = raw.split()
    if len(parts) != 4 or not all(p.isdigit() and 1 <= int(p) <= 5 for p in parts):
        print("  Invalid input, expected 4 numbers 1-5 (e.g. '5 5 4 5'). Skipping case.")
        return None
    return {field: int(p) for field, p in zip(FIELDS, parts)}


def summarize(scored: list) -> dict:
    summary = {}
    for field in FIELDS:
        vals = [s["scores"][field] for s in scored if field in s["scores"]]
        if not vals:
            summary[field] = {"mean": None, "pct_ge_4": None, "n": 0}
            continue
        summary[field] = {
            "mean": round(sum(vals) / len(vals), 2),
            "pct_ge_4": round(sum(1 for v in vals if v >= 4) / len(vals) * 100, 1),
            "n": len(vals),
        }
    return summary


def _save(out_path: str, scored: list, model: str, suite: str):
    summary = summarize(scored)
    with open(out_path, "w") as f:
        json.dump({"model": model, "suite": suite, "summary": summary, "scored": scored}, f, indent=2)
    return summary


def main():
    args = parse_args()
    if args.model:
        settings.LLM_MODEL = args.model

    scored = []
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    if args.resume and os.path.exists(args.resume):
        with open(args.resume) as f:
            scored = json.load(f)["scored"]
        print(f"  Resumed {len(scored)} previously scored cases from {args.resume}")
        out_path = args.resume  # keep appending to the same file across resumes
    else:
        ts = time.strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(reports_dir, f"extraction_scores_{ts}.json")

    already_ids = {s["id"] for s in scored}
    sample = pick_sample(args.suite, args.sample, args.seed, already_ids)
    print(f"\n  Model: {settings.LLM_MODEL} | Suite: {args.suite} | Sampling {len(sample)} unscored cases")
    print("  Enter 4 scores per case (location issue_summary affected_parties ask), 's' to skip, 'q' to save+quit.")
    print(f"  Progress is saved after every scored case -> {out_path}\n")

    try:
        for case in sample:
            try:
                extraction = run_extractor(case["raw_text"], case.get("location"))
            except Exception as e:
                print(f"  [{case['id']}] extractor error: {e}, skipping")
                continue
            if extraction is None:
                print(f"  [{case['id']}] extractor returned None, skipping")
                continue

            result = prompt_scores(case, extraction)
            if result == "quit":
                break
            if result is None:
                continue
            scored.append({"id": case["id"], "raw_text": case["raw_text"], "scores": result})
            _save(out_path, scored, settings.LLM_MODEL, args.suite)  # persist after every case — a Ctrl+C or crash loses at most the in-flight one
    except KeyboardInterrupt:
        print("\n  Interrupted — progress already saved up to the last scored case.")

    summary = _save(out_path, scored, settings.LLM_MODEL, args.suite)

    print(f"\n{'='*55}")
    print(f"  Extraction Quality Summary ({len(scored)} cases scored)")
    print(f"{'='*55}")
    for field, s in summary.items():
        if s["n"] == 0:
            print(f"  {field:<18}: no scores yet")
        else:
            print(f"  {field:<18}: mean={s['mean']}  %>=4={s['pct_ge_4']}%  (n={s['n']})")
    print(f"\n  Saved -> {out_path}")
    print(f"  Resume later with: python eval/score_extraction.py --resume {out_path}\n")


if __name__ == "__main__":
    main()
