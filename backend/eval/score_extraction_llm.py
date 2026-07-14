"""
Civic Voice Agent — Automated Extraction Quality via LLM-as-Judge (eval Layer 3)

This is the automated, at-scale counterpart to score_extraction.py's manual
human rubric. It runs the extractor on a sample of valid cases, then asks a
GROUNDED judge LLM (see app/llm/prompts/judge.py) to score the SAME four fields
on the SAME 1-5 rubric a human uses — plus a deterministic, model-free
verbatim-copy check on issue_summary.

Why this is not "the LLM grading its own homework":
  * The judge only ever sees the citizen's raw_text + the extraction; it's never
    handed a reference answer, so it must reason from the source like a human does.
  * --validate re-scores exactly the cases a human already scored (the 19 in
    reports/extraction_scores_*.json) and reports judge-vs-human agreement
    (mean absolute error, % within 1 point, correlation). If the judge tracks the
    humans, its at-scale scores are a validated proxy; if it doesn't, the numbers
    say so honestly.

Usage:
    cd backend
    # 1) Run the judge over a fresh sample and save per-field means:
    python eval/score_extraction_llm.py --suite core --sample 25

    # 2) Validate the judge against real human scores (the credibility check):
    python eval/score_extraction_llm.py --validate reports/extraction_scores_20260712_170602.json

Rubric (same as score_extraction.py, so scores are directly comparable):
    5 = Fully correct, captures exactly what's in the text, no invention.
    4 = Correct and usable, minor phrasing awkwardness only.
    3 = Mostly correct but missing a detail a leader would want.
    2 = Partially wrong or vague enough to be unhelpful.
    1 = Wrong, or invented information not present in raw_text.
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
from app.llm.client import call_llm
from app.db.eval_metrics import log_metric, new_run_id
from app.llm.prompts.judge import (
    ExtractionJudgment,
    JUDGE_SYSTEM_PROMPT,
    build_judge_user_prompt,
)
from eval.run_eval import load_cases

# Human report field name -> judge model attribute. Kept explicit so the
# per-field validation lines up exactly with what a human scored.
FIELDS = ["location", "issue_summary", "affected_parties", "ask"]
_JUDGE_ATTR = {
    "location": "location_score",
    "issue_summary": "issue_summary_score",
    "affected_parties": "affected_parties_score",
    "ask": "ask_score",
}
_REASON_ATTR = {
    "location": "location_reason",
    "issue_summary": "issue_summary_reason",
    "affected_parties": "affected_parties_reason",
    "ask": "ask_reason",
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--suite", default="core", choices=["demo", "core", "full", "multilingual"])
    p.add_argument("--sample", type=int, default=25, help="cases to judge (ignored in --validate mode)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model", default=None, help="override LLM_MODEL for both extractor and judge")
    p.add_argument("--validate", default=None,
                   help="path to a human extraction_scores_*.json; re-judge those exact cases and "
                        "report judge-vs-human agreement instead of a fresh sample run")
    p.add_argument("--copy-threshold", type=float, default=0.6,
                   help="issue_summary is flagged as a verbatim copy when the longest shared contiguous "
                        "word-run with raw_text is >= this fraction of the summary's length")
    p.add_argument("--delay", type=float, default=None,
                   help="seconds slept before each LLM call (default 1.5 when GROQ_API_KEY is set, else 0)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Deterministic verbatim-copy check (no LLM) — one of the assignment's named
# quality concerns ("avoids copying raw input verbatim"), measured objectively.
# ---------------------------------------------------------------------------

def _tokenize(text: str):
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in (text or "")).split() if t]


def _longest_common_run(a: list, b: list) -> int:
    """Length of the longest contiguous token run common to both lists (classic
    LCS-substring DP). Short inputs, so O(n*m) is fine."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                best = max(best, cur[j])
        prev = cur
    return best


def copy_ratio(issue_summary: str, raw_text: str) -> float:
    """Fraction of the summary that is one contiguous lift from raw_text. ~1.0
    means the 'summary' is basically a copied sentence; low means it was distilled."""
    summ = _tokenize(issue_summary)
    if not summ:
        return 0.0
    run = _longest_common_run(summ, _tokenize(raw_text))
    return round(run / len(summ), 3)


# ---------------------------------------------------------------------------
# Shared: run extractor + judge on one case
# ---------------------------------------------------------------------------

def _judge_one(case: dict, delay: float):
    """Returns (extraction_dict, ExtractionJudgment) or (None, None) on failure."""
    if delay:
        time.sleep(delay)
    try:
        extraction = run_extractor(case["raw_text"], case.get("location"))
    except Exception as e:
        print(f"    [{case['id']}] extractor error: {e}")
        return None, None
    if extraction is None:
        print(f"    [{case['id']}] extractor returned None")
        return None, None

    if delay:
        time.sleep(delay)
    judgment = call_llm(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=build_judge_user_prompt(
            case["raw_text"], extraction.location, extraction.issue_summary,
            extraction.affected_parties, extraction.ask,
        ),
        response_model=ExtractionJudgment,
    )
    if judgment is None:
        print(f"    [{case['id']}] judge returned None")
        return None, None

    extraction_dict = {
        "location": extraction.location,
        "issue_summary": extraction.issue_summary,
        "affected_parties": extraction.affected_parties,
        "ask": extraction.ask,
    }
    return extraction_dict, judgment


def _summarize_scores(rows: list) -> dict:
    """rows: list of {field: score}. Returns mean + %>=4 + n per field."""
    out = {}
    for field in FIELDS:
        vals = [r[field] for r in rows if field in r and r[field] is not None]
        if not vals:
            out[field] = {"mean": None, "pct_ge_4": None, "n": 0}
        else:
            out[field] = {
                "mean": round(sum(vals) / len(vals), 2),
                "pct_ge_4": round(sum(1 for v in vals if v >= 4) / len(vals) * 100, 1),
                "n": len(vals),
            }
    return out


# ---------------------------------------------------------------------------
# Mode 1: fresh judge run over a sample
# ---------------------------------------------------------------------------

def run_judge(args, delay: float):
    cases = [c for c in load_cases(args.suite) if c["is_valid_submission"]]
    random.Random(args.seed).shuffle(cases)
    sample = cases[:args.sample]

    print(f"\n  Model: {settings.LLM_MODEL} | Suite: {args.suite} | Judging {len(sample)} cases "
          f"(seed={args.seed}, delay={delay}s)\n")

    scored, score_rows, copy_ratios = [], [], []
    for case in sample:
        extraction, judgment = _judge_one(case, delay)
        if extraction is None:
            continue
        scores = {f: getattr(judgment, _JUDGE_ATTR[f]) for f in FIELDS}
        reasons = {f: getattr(judgment, _REASON_ATTR[f]) for f in FIELDS}
        cr = copy_ratio(extraction["issue_summary"], case["raw_text"])
        score_rows.append(scores)
        copy_ratios.append(cr)
        scored.append({
            "id": case["id"], "raw_text": case["raw_text"],
            "extraction": extraction, "scores": scores, "reasons": reasons,
            "copy_ratio": cr,
        })
        print(f"  [{case['id']}] "
              + "  ".join(f"{f}={scores[f]}" for f in FIELDS)
              + f"  copy={cr}")

    summary = _summarize_scores(score_rows)
    flagged = sum(1 for c in copy_ratios if c >= args.copy_threshold)
    verbatim = {
        "mean_copy_ratio": round(sum(copy_ratios) / len(copy_ratios), 3) if copy_ratios else None,
        "pct_flagged": round(flagged / len(copy_ratios) * 100, 1) if copy_ratios else None,
        "threshold": args.copy_threshold,
        "n": len(copy_ratios),
    }

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(reports_dir, f"extraction_llm_scores_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "mode": "judge", "model": settings.LLM_MODEL, "suite": args.suite,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "n": len(scored),
            "summary": summary, "verbatim_copy": verbatim, "scored": scored,
        }, f, indent=2, ensure_ascii=False)

    # Log headline metrics to the observability store (trends over time).
    run_id = new_run_id()
    field_means = [s["mean"] for s in summary.values() if s["mean"] is not None]
    if field_means:
        overall_mean = round(sum(field_means) / len(field_means), 2)
        log_metric("extraction_llm", "extraction_quality_mean", overall_mean, len(scored), settings.LLM_MODEL, run_id)
    if verbatim["pct_flagged"] is not None:
        log_metric("extraction_llm", "verbatim_copy_flagged", verbatim["pct_flagged"], verbatim["n"], settings.LLM_MODEL, run_id)

    print(f"\n{'='*60}")
    print(f"  LLM-Judge Extraction Quality  ({len(scored)} cases, model {settings.LLM_MODEL})")
    print(f"{'='*60}")
    for field, s in summary.items():
        if s["n"]:
            print(f"  {field:<18}: mean={s['mean']}  %>=4={s['pct_ge_4']}%  (n={s['n']})")
    if verbatim["n"]:
        print(f"  {'verbatim-copy':<18}: mean copy-ratio={verbatim['mean_copy_ratio']}  "
              f"flagged>= {verbatim['threshold']}: {verbatim['pct_flagged']}%")
    print(f"\n  Saved -> {out_path}")
    print(f"  Validate it against human scores with:\n"
          f"    python eval/score_extraction_llm.py --validate reports/extraction_scores_<ts>.json\n")


# ---------------------------------------------------------------------------
# Mode 2: validate the judge against real human scores (the credibility check)
# ---------------------------------------------------------------------------

def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:  # a constant column has no linear correlation defined
        return None
    return round(num / (dx * dy), 3)


def _resolve_report_path(path: str) -> str:
    """Accept an absolute path, a path relative to CWD, or just a filename /
    reports-relative path (resolved against eval/reports/), so the same string
    printed by a judge run works verbatim in --validate regardless of CWD."""
    if os.path.isabs(path) and os.path.exists(path):
        return path
    candidates = [
        path,
        os.path.join(os.path.dirname(__file__), path),
        os.path.join(os.path.dirname(__file__), "reports", os.path.basename(path)),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return path  # let open() raise a clear FileNotFoundError on the original


def run_validate(args, delay: float):
    validate_path = _resolve_report_path(args.validate)
    with open(validate_path, encoding="utf-8") as f:
        human = json.load(f)
    human_cases = human.get("scored", [])
    if not human_cases:
        print(f"  No scored cases in {args.validate}; nothing to validate against.")
        return

    print(f"\n  Validating judge (model {settings.LLM_MODEL}) against {len(human_cases)} human-scored "
          f"cases from {os.path.basename(args.validate)}")
    print("  NOTE: the human report stored raw_text + scores but NOT the exact extraction that was\n"
          "  scored, so the extractor is re-run here. Agreement therefore also reflects extractor\n"
          "  stability, not the judge alone — reported honestly rather than hidden.\n")

    # Per-field parallel arrays of (human, judge) for the cases we could re-judge.
    paired = {f: {"human": [], "judge": []} for f in FIELDS}
    audit = []
    for hc in human_cases:
        case = {"id": hc["id"], "raw_text": hc["raw_text"], "location": hc.get("location")}
        extraction, judgment = _judge_one(case, delay)
        if extraction is None:
            continue
        for f in FIELDS:
            if f in hc.get("scores", {}):
                hv = hc["scores"][f]
                jv = getattr(judgment, _JUDGE_ATTR[f])
                paired[f]["human"].append(hv)
                paired[f]["judge"].append(jv)
                audit.append({"id": hc["id"], "field": f, "human": hv, "judge": jv})
        print(f"  [{hc['id']}] " + "  ".join(
            f"{f}: H{hc['scores'].get(f, '-')}/J{getattr(judgment, _JUDGE_ATTR[f])}" for f in FIELDS))

    agreement = {}
    all_abs, all_within = [], []
    for f in FIELDS:
        hs, js = paired[f]["human"], paired[f]["judge"]
        if not hs:
            agreement[f] = {"n": 0}
            continue
        abs_errs = [abs(h - j) for h, j in zip(hs, js)]
        within1 = [1 if e <= 1 else 0 for e in abs_errs]
        all_abs += abs_errs
        all_within += within1
        agreement[f] = {
            "n": len(hs),
            "mae": round(sum(abs_errs) / len(abs_errs), 2),
            "pct_within_1": round(sum(within1) / len(within1) * 100, 1),
            "human_mean": round(sum(hs) / len(hs), 2),
            "judge_mean": round(sum(js) / len(js), 2),
            "pearson": _pearson(hs, js),
        }

    overall = {
        "n": len(all_abs),
        "mae": round(sum(all_abs) / len(all_abs), 2) if all_abs else None,
        "pct_within_1": round(sum(all_within) / len(all_within) * 100, 1) if all_within else None,
    }

    if overall["pct_within_1"] is not None:
        log_metric("extraction_llm", "judge_human_agreement_within1", overall["pct_within_1"],
                   overall["n"], settings.LLM_MODEL, new_run_id())

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(reports_dir, f"extraction_llm_validation_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "mode": "validate", "model": settings.LLM_MODEL,
            "human_report": os.path.basename(args.validate),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "caveat": "Extractor was re-run (human report did not store the scored extraction), so "
                      "agreement folds in extractor stability, not only judge accuracy.",
            "agreement": agreement, "overall": overall, "pairs": audit,
        }, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"  Judge-vs-Human Agreement  ({overall['n']} field-scores across {len(human_cases)} cases)")
    print(f"{'='*60}")
    for f in FIELDS:
        a = agreement[f]
        if a.get("n"):
            print(f"  {f:<18}: within-1pt {a['pct_within_1']}%  MAE {a['mae']}  "
                  f"(human avg {a['human_mean']} vs judge avg {a['judge_mean']}, r={a['pearson']}, n={a['n']})")
    if overall["n"]:
        print(f"  {'OVERALL':<18}: within-1pt {overall['pct_within_1']}%  MAE {overall['mae']}  (n={overall['n']})")
    print("\n  Reading: high % within-1-point + low MAE = the judge tracks human judgment closely,")
    print("  so its automated at-scale scores are a validated proxy for the manual rubric.")
    print(f"\n  Saved -> {out_path}\n")


def main():
    args = parse_args()
    if args.model:
        settings.LLM_MODEL = args.model
    delay = args.delay if args.delay is not None else (1.5 if settings.GROQ_API_KEY else 0.0)

    if args.validate:
        run_validate(args, delay)
    else:
        run_judge(args, delay)


if __name__ == "__main__":
    main()
