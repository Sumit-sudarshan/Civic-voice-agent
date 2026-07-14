"""
Civic Voice Agent — Dashboard Actionability Rubric Scoring (eval_plan.md Phase E / roadmap.md 12.3)

Unlike score_extraction.py (which scores individual extractions one at a time), this
scores a whole DASHBOARD STATE at once -- because "Correct prioritization" and
"Absence of noise/duplicate clutter" are properties of a *list* (does the ordering
make sense, do near-duplicates visibly clutter the view), not of any single card.

The tool runs a representative sample of complaints through the real orchestrator
(app.pipeline.orchestrator.finalize_submission), renders them sorted by predicted
urgency exactly like the real Home dashboard would, deliberately includes one
un-merged near-duplicate pair (session=None means dedup merge is skipped) so the
"clutter" dimension has something real to catch, and asks for ONE set of 5 scores
for the whole rendered list.

Run it twice under two different --scorer names with the same --seed to get two
independent opinions on the identical state, then use --compare to check agreement.

Usage:
    cd backend
    python eval/score_actionability.py --scorer alice
    python eval/score_actionability.py --scorer bob            # same default seed -> same state
    python eval/score_actionability.py --compare alice bob     # compare their scores on matching states

Rubric (score the WHOLE list 1-5 on each):
    Clarity                 - Can you tell at a glance what each issue is?
    Completeness             - Is location / ask / affected parties present and useful?
    Correct prioritization   - Does the urgency-sorted order actually make sense?
    Absence of clutter        - Are near-duplicate/noisy entries visibly polluting the view?
    Actionability of the ask - Could a leader act on this without re-reading the raw text?
"""
import argparse
import json
import os
import random
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlmodel import Session

from app.config import settings
from app.db.session import engine
from app.models.db_models import SubmissionType
from app.pipeline.orchestrator import finalize_submission
from app.pipeline.facts import build_issue_facts
from app.llm.client import call_llm_text
from app.llm.prompts.summarize import VERDICT_SYSTEM_PROMPT, build_verdict_user_prompt, render_report
from eval.run_eval import _load_json

DIMENSIONS = ["clarity", "completeness", "correct_prioritization", "absence_of_clutter", "actionability_of_ask"]
TIER_ORDER = {"ACT TODAY": 0, "ESCALATE": 1, "THIS WEEK": 2, "WATCH": 3, "ROUTINE": 4}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scorer", help="your name/id, so two people's scores can be compared")
    parser.add_argument("--sample", type=int, default=24, help="how many cases to seed the state with")
    parser.add_argument("--seed", type=int, default=42, help="fixed seed -> reproducible state for cross-scorer comparison")
    parser.add_argument("--model", default=None)
    parser.add_argument("--compare", nargs="+", metavar="SCORER", help="compare scores across two or more previously-run scorer names")
    return parser.parse_args()


def pick_sample(n: int, seed: int):
    """Stratified pull across all 8 categories from category_cases.json, plus one
    deliberately un-merged near-duplicate pair from dedup_cases.json for clutter-testing."""
    category_cases = [c for c in _load_json("datasets/category_cases.json") if c["submission_type"] == "complaint"]
    by_category = defaultdict(list)
    for c in category_cases:
        by_category[c["category"]].append(c)
    rng = random.Random(seed)
    for lst in by_category.values():
        rng.shuffle(lst)

    dedup_cases = _load_json("datasets/dedup_cases.json")
    groups = defaultdict(list)
    for c in dedup_cases:
        groups[c["duplicate_group_id"]].append(c)
    dup_pair = next(v for v in groups.values() if len(v) == 2)

    sample = list(dup_pair)  # guarantees a real clutter case is present
    remaining = n - len(sample)
    categories = sorted(by_category.keys())
    i = 0
    while remaining > 0 and any(by_category.values()):
        cat = categories[i % len(categories)]
        if by_category[cat]:
            sample.append(by_category[cat].pop())
            remaining -= 1
        i += 1
        if i > n * 10:
            break
    rng.shuffle(sample)
    return sample


def process_sample(sample: list):
    processed = []
    for case in sample:
        result = finalize_submission(
            raw_text=case["raw_text"],
            submission_type=SubmissionType.complaint,
            citizen_name="Eval Citizen",
            citizen_phone="0000000000",
            session=None,
        )
        processed.append({"case_id": case["id"], "raw_text": case["raw_text"], "result": result})
    return processed


def build_summary_issues(processed: list, session: Session) -> list:
    """
    Same fact-assembly the real /stats/top-issues-summary endpoint uses
    (app.pipeline.facts.build_issue_facts) — so this tool scores the actual
    tiered summary format, not a stand-in rendering of it.

    Caveat: this eval harness doesn't have structured location_address/
    location_area ground truth to feed in (category_cases.json has no
    location fields — see Phase C of eval_plan.md), so cluster_size always
    comes back 0 here — that's only exercised by real conversational
    submissions where the dialogue manager has gathered a structured spot.
    """
    issues = []
    for p in processed:
        r = p["result"]
        facts = build_issue_facts(r, session)
        issues.append({
            "category": r.category.value if r.category else "other",
            "location_area": r.location_area,
            "urgency_level": r.urgency_level.value if r.urgency_level else None,
            "needs_human_review": r.needs_human_review,
            "issue_summary": r.extracted_issue_summary or p["raw_text"][:80],
            **facts,
        })
    issues.sort(key=lambda i: (TIER_ORDER.get(i["tier"], 5), -i["report_count"]))
    return issues


def _area_known(area) -> bool:
    return bool(area) and str(area).strip().lower() != "not specified"


def build_facts_from_sample(issues: list) -> dict:
    """
    Lightweight stand-in for app.api.stats.build_report_facts, sized for a
    single synthetic eval snapshot rather than a live time-ranged DB query
    (no previous-period delta data available here). area_tally / urgency_tally /
    systemic_categories are computed the same way build_report_facts does, so a
    briefing rendered from this is populated exactly like the live one — which
    matters for the reader-proxy actionability eval (score_summary_actionability.py),
    where those sections are what the reader is quizzed on.
    """
    category_tally = dict(Counter(i["category"] for i in issues))
    area_tally = dict(Counter(i["location_area"] for i in issues if _area_known(i.get("location_area"))))
    urgency_tally = dict(Counter(i["urgency_level"] for i in issues if i.get("urgency_level")))

    critical_items = [
        {
            "category": i["category"], "location": i["location"], "urgency": "critical",
            "days_open": i["days_open"], "report_count": i["report_count"],
            "issue_summary": i["issue_summary"],
        }
        for i in issues if i["tier"] == "ACT TODAY"
    ]

    recurring = []
    seen = set()
    for i in issues:
        key = (i["category"], i["location"])
        if key in seen:
            continue
        total = i["cluster_size"] + i["report_count"]
        if total >= 3:
            seen.add(key)
            recurring.append({"category": i["category"], "location": i["location"], "report_count": total})

    # Systemic signal: one category recurring across >=3 distinct named areas
    # (a citywide process problem, vs. recurring's single-spot hotspot).
    category_areas: dict = {}
    for i in issues:
        if not _area_known(i.get("location_area")):
            continue
        category_areas.setdefault(i["category"], set()).add(i["location_area"])
    systemic_categories = sorted(
        [{"category": c, "area_count": len(a)} for c, a in category_areas.items() if len(a) >= 3],
        key=lambda s: -s["area_count"],
    )

    return {
        "submission_type": "complaint",
        "range_label": "Eval sample",
        "total_current": len(issues),
        "total_previous": None,
        "category_tally": category_tally,
        "area_tally": area_tally,
        "urgency_tally": urgency_tally,
        "category_deltas": {},
        "critical_items": critical_items,
        "recurring": recurring,
        "systemic_categories": systemic_categories,
        "top_supported": [],
    }


def render_state(issues: list) -> str:
    """
    Renders the exact same bullet-and-stats briefing shape a leader sees in
    the app (see llm/prompts/summarize.py) — precomputed facts rendered
    deterministically, with a single LLM-authored verdict line.
    """
    facts = build_facts_from_sample(issues)
    user_prompt = build_verdict_user_prompt(facts)
    raw = call_llm_text(VERDICT_SYSTEM_PROMPT, user_prompt)
    verdict = raw.strip() if raw else "Unable to generate a summary."
    report = render_report(facts, verdict)

    flags = [f"  [{i+1}] NEEDS_REVIEW" for i, issue in enumerate(issues) if issue["needs_human_review"]]
    flags_block = ("\n\nFLAGS\n" + "\n".join(flags)) if flags else ""

    return report + flags_block


def prompt_state_scores():
    print("\n" + "=" * 60)
    print("  Score the WHOLE list above (1-5 each), space-separated, in order:")
    print("  clarity completeness correct_prioritization absence_of_clutter actionability_of_ask")
    print("  (or 'q' to quit without saving)")
    raw = input("  > ").strip()
    if raw.lower() == "q":
        return None
    parts = raw.split()
    if len(parts) != 5 or not all(p.isdigit() and 1 <= int(p) <= 5 for p in parts):
        print("  Invalid input, expected 5 numbers 1-5. Try again.")
        return prompt_state_scores()
    return {dim: int(p) for dim, p in zip(DIMENSIONS, parts)}


def report_path_for(scorer: str) -> str:
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return os.path.join(reports_dir, f"actionability_scores_{scorer}.json")


def run_scoring(args):
    if args.model:
        settings.LLM_MODEL = args.model
    if not args.scorer:
        print("  --scorer <name> is required to score (or use --compare to review existing scores).")
        return

    sample = pick_sample(args.sample, args.seed)
    print(f"\n  Model: {settings.LLM_MODEL} | Seeding {len(sample)} cases (seed={args.seed}) through the real pipeline...")
    processed = process_sample(sample)

    with Session(engine) as session:
        issues = build_summary_issues(processed, session)
        print("\n" + "=" * 60)
        print(f"  AI SUMMARY  (tiered, {len(issues)} items — same format as the live dashboard)")
        print("=" * 60)
        print(render_state(issues))

    scores = prompt_state_scores()
    if scores is None:
        print("  Not saved.")
        return

    out_path = report_path_for(args.scorer)
    existing = []
    if os.path.exists(out_path):
        with open(out_path) as f:
            existing = json.load(f).get("states", [])

    existing.append({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": settings.LLM_MODEL,
        "seed": args.seed,
        "case_ids": [p["case_id"] for p in processed],
        "scores": scores,
    })
    with open(out_path, "w") as f:
        json.dump({"scorer": args.scorer, "states": existing}, f, indent=2)
    print(f"\n  Saved -> {out_path}")


def run_compare(scorer_names: list):
    all_states = {}
    for name in scorer_names:
        path = report_path_for(name)
        if not os.path.exists(path):
            print(f"  No scores found for '{name}' at {path}, skipping.")
            continue
        with open(path) as f:
            all_states[name] = json.load(f)["states"]

    if len(all_states) < 2:
        print("  Need at least 2 scorers with saved states to compare.")
        return

    # Match states across scorers by identical case_id sets (same seed -> same sample)
    by_case_set = defaultdict(dict)
    for name, states in all_states.items():
        for s in states:
            key = tuple(sorted(s["case_ids"]))
            by_case_set[key][name] = s["scores"]

    matched = {k: v for k, v in by_case_set.items() if len(v) >= 2}
    if not matched:
        print("  No matching states (same case sample) found across scorers -- run with the same --seed.")
        return

    print(f"\n{'='*60}")
    print(f"  Actionability Agreement Report  ({len(matched)} matched state(s), scorers: {', '.join(scorer_names)})")
    print(f"{'='*60}")

    dim_means = defaultdict(list)
    dim_agree = defaultdict(list)
    for key, by_scorer in matched.items():
        names = list(by_scorer.keys())
        for dim in DIMENSIONS:
            vals = [by_scorer[n][dim] for n in names]
            dim_means[dim].extend(vals)
            for i in range(len(vals)):
                for j in range(i + 1, len(vals)):
                    dim_agree[dim].append(abs(vals[i] - vals[j]) <= 1)

    for dim in DIMENSIONS:
        mean = sum(dim_means[dim]) / len(dim_means[dim]) if dim_means[dim] else 0
        agree_pct = (sum(dim_agree[dim]) / len(dim_agree[dim]) * 100) if dim_agree[dim] else 0
        print(f"  {dim:<26}: mean={mean:.2f}  agreement(within 1pt)={agree_pct:.0f}%")
    print()


def main():
    args = parse_args()
    if args.compare:
        run_compare(args.compare)
    else:
        run_scoring(args)


if __name__ == "__main__":
    main()
