"""
Civic Voice Agent — Task-Based Actionability of the Leader Briefing (eval Layer 4)

The assignment asks, by name: "How do you measure whether the summary is
actionable for a busy leader?" A 1-5 "is this good?" rating is subjective and
self-referential. This measures actionability as a BEHAVIOUR instead:

  1. Seed a realistic scenario and run it through the real pipeline
     (finalize_submission) to get real categories/urgency/extractions.
  2. Render the ACTUAL leader briefing the app would show
     (app.llm.prompts.summarize.render_report + the real one-line LLM verdict).
  3. Hand ONLY the rendered briefing text (never the underlying facts) to a fresh
     LLM acting as a busy leader, and ask the concrete questions a leader must be
     able to answer at a glance: how many issues, how many are critical, which
     category and area dominate, and which single item to act on first.
  4. Score those answers against ground truth computed from the SAME facts the
     briefing was rendered from — so we're checking whether the information is
     actually extractable from the summary, not grading taste.

This is "real" because every answer is checkable against ground truth, and the
reader proxy is deliberately blind to everything except the summary — exactly the
position the leader is in. The deterministically-rendered parts of the briefing
(counts, tallies) are correct by construction; this test confirms they're also
*legible*. The one genuinely-generated line (the verdict) is checked separately
for pointing in the right direction (escalate / quiet / normal).

Usage:
    cd backend
    python eval/score_summary_actionability.py --seed 42
    python eval/score_summary_actionability.py --seed 7 --scenarios 3 --sample 12
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlmodel import Session

from app.config import settings
from app.db.session import engine
from app.models.db_models import SubmissionType
from app.pipeline.orchestrator import finalize_submission
from app.llm.client import call_llm, call_llm_text
from app.llm.prompts.summarize import VERDICT_SYSTEM_PROMPT, build_verdict_user_prompt, render_report
from app.llm.prompts.grounding_judge import VerdictGrounding, GROUNDING_SYSTEM_PROMPT, build_grounding_user_prompt
from app.db.eval_metrics import log_metric, new_run_id
from pydantic import BaseModel, Field

from eval.score_actionability import pick_sample, build_summary_issues, build_facts_from_sample

# Synthetic areas assigned to seeded cases (category_cases.json carries no
# location) so the briefing's area/systemic sections are populated and testable.
AREAS = ["Andheri West", "Bandra East", "Dadar", "Cotton Green", "Kurla"]


class ReaderAnswers(BaseModel):
    """What a busy leader must be able to pull from the briefing at a glance."""
    total_issues: int = Field(..., description="Total number of issues/complaints in this briefing.")
    critical_count: int = Field(..., description="How many are marked critical. 0 if none are mentioned as critical.")
    top_category: str = Field(..., description="The single most common issue category. One word/phrase as written.")
    most_affected_area: str = Field(..., description="The area with the most reports, exactly as named in the briefing.")
    top_priority_location: str = Field(
        ..., description="The location of the ONE item a leader should act on first (the top item under "
                         "what needs attention). Write 'none' if the briefing flags nothing needing attention."
    )


READER_SYSTEM_PROMPT = """You are a busy local civic leader with only a minute to read a briefing about
citizen issues in your area. Answer the questions using ONLY the information written in the briefing
below — do not guess, do not use outside knowledge, and do not do any analysis beyond reading. Report
numbers and names exactly as they appear in the briefing. If the briefing does not mention something,
answer 0 (for a count) or 'none' (for a name). Respond with the structured fields only.
"""


def build_reader_user_prompt(report_text: str) -> str:
    return (
        "BRIEFING:\n"
        "----------\n"
        f"{report_text}\n"
        "----------\n\n"
        "From the briefing above, report: the total number of issues; how many are critical; the top "
        "issue category; the most affected area; and the location of the single item to act on first."
    )


# ---------------------------------------------------------------------------
# Ground truth — computed from the SAME facts dict render_report consumes, so
# the "correct answer" is exactly what the briefing displays (see module docstring).
# ---------------------------------------------------------------------------

def ground_truth(facts: dict) -> dict:
    total = facts["total_current"]
    critical = facts.get("urgency_tally", {}).get("critical", 0)
    top_category = (
        max(facts["category_tally"].items(), key=lambda x: x[1])[0] if facts.get("category_tally") else "none"
    )
    most_area = (
        max(facts["area_tally"].items(), key=lambda x: x[1])[0] if facts.get("area_tally") else "none"
    )
    crit_items = facts.get("critical_items", [])
    top_loc = crit_items[0]["location"] if crit_items else "none"

    # Expected verdict direction, from the same signals render_report exposes.
    recurring_n = len(facts.get("recurring", []))
    systemic_n = len(facts.get("systemic_categories", []))
    if critical >= 2 or recurring_n >= 1 or systemic_n >= 1:
        direction = "escalate"
    elif total <= 3 and critical == 0:
        direction = "quiet"
    else:
        direction = "normal"

    return {
        "total_issues": total,
        "critical_count": critical,
        "top_category": top_category,
        "most_affected_area": most_area,
        "top_priority_location": top_loc,
        "expected_direction": direction,
    }


_ESCALATE_KW = ["escalat", "worsen", "urgent", "immediate", "priorit", "concern", "attention", "act now", "critical", "spike", "rising"]
_QUIET_KW = ["quiet", "calm", "low ", "manageable", "stable", "no major", "nothing major", "light", "slow period"]
_NORMAL_KW = ["normal", "typical", "steady", "routine", "as expected", "in line"]


def classify_verdict_direction(verdict: str) -> str:
    v = (verdict or "").lower()
    if any(k in v for k in _ESCALATE_KW):
        return "escalate"
    if any(k in v for k in _QUIET_KW):
        return "quiet"
    if any(k in v for k in _NORMAL_KW):
        return "normal"
    return "unclear"


def _norm(s) -> str:
    return str(s or "").strip().lower()


def _loc_match(expected: str, got: str) -> bool:
    """Location is a longer free-text string, so accept a containment match
    (leader may echo a shortened form) rather than demanding character-exact."""
    e, g = _norm(expected), _norm(got)
    if e == "none":
        return g in ("none", "", "n/a")
    if not g:
        return False
    return e == g or e in g or g in e


# ---------------------------------------------------------------------------
# Grounded faithfulness (Layer 5): does the briefing match the source data?
#   * reported-data accuracy + location accuracy: deterministic — the rendered
#     text is compared straight to the facts, no LLM (they should read ~100% by
#     construction, so a drop is a real rendering/extraction regression alarm).
#   * hallucination: the LLM-written verdict is the only free-text part, so a
#     grounding judge fact-checks just that against the facts.
# ---------------------------------------------------------------------------

_INT_RE = re.compile(r"\d+")


def _allowed_numbers(facts: dict) -> set:
    """Every integer the briefing is allowed to print, derived from the facts."""
    allowed = {facts.get("total_current", 0)}
    for tally in ("category_tally", "area_tally", "urgency_tally"):
        allowed.update(facts.get(tally, {}).values())
    for item in facts.get("critical_items", []):
        allowed.add(item.get("report_count", 1))
        allowed.add(item.get("days_open", 0))
    for r in facts.get("recurring", []):
        allowed.add(r.get("report_count", 0))
    for s in facts.get("systemic_categories", []):
        allowed.add(s.get("area_count", 0))
    if facts.get("total_previous") is not None:
        allowed.add(facts["total_previous"])
        allowed.add(abs(facts["total_current"] - facts["total_previous"]))
    return {int(x) for x in allowed}


def numeric_grounding(report_text: str, facts: dict) -> tuple:
    """(matched, total) integers in the report that trace back to the facts."""
    allowed = _allowed_numbers(facts)
    nums = [int(m) for m in _INT_RE.findall(report_text)]
    if not nums:
        return 0, 0
    matched = sum(1 for n in nums if n in allowed)
    return matched, len(nums)


def _known_locations(facts: dict) -> list:
    locs = [i["location"] for i in facts.get("critical_items", []) if i.get("location")]
    locs += [r["location"] for r in facts.get("recurring", []) if r.get("location")]
    return locs


def location_grounding(report_text: str, facts: dict) -> tuple:
    """(matched, total) of the facts' named locations that actually appear in
    the briefing — i.e. the briefing didn't drop or garble a spot it should show."""
    locs = _known_locations(facts)
    if not locs:
        return 0, 0
    rt = report_text.lower()
    matched = sum(1 for loc in locs if loc and loc.lower() in rt)
    return matched, len(locs)


def facts_for_grounding_prompt(facts: dict) -> str:
    """Compact, authoritative dump of the facts for the verdict grounding judge."""
    lines = [
        f"total_current: {facts.get('total_current')}",
        f"total_previous: {facts.get('total_previous')}",
        f"category_tally: {facts.get('category_tally')}",
        f"area_tally: {facts.get('area_tally')}",
        f"urgency_tally: {facts.get('urgency_tally')}",
        f"critical_items: {[{'category': i['category'], 'location': i['location']} for i in facts.get('critical_items', [])]}",
        f"recurring_hotspots: {len(facts.get('recurring', []))}",
        f"systemic_categories: {facts.get('systemic_categories')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scenario processing
# ---------------------------------------------------------------------------

def process_pool(cases: list, delay: float) -> list:
    """Run each seeded case through the real pipeline, assigning a synthetic
    area so the briefing's area/systemic sections have something to render."""
    processed = []
    for idx, case in enumerate(cases):
        if delay:
            time.sleep(delay)
        result = finalize_submission(
            raw_text=case["raw_text"],
            submission_type=SubmissionType.complaint,
            citizen_name="Eval Citizen",
            citizen_phone="0000000000",
            location_area=AREAS[idx % len(AREAS)],
            session=None,
        )
        processed.append({"case_id": case["id"], "raw_text": case["raw_text"], "result": result})
    return processed


def score_scenario(processed_chunk: list, delay: float) -> dict:
    with Session(engine) as session:
        issues = build_summary_issues(processed_chunk, session)
    facts = build_facts_from_sample(issues)
    gt = ground_truth(facts)

    if delay:
        time.sleep(delay)
    raw = call_llm_text(VERDICT_SYSTEM_PROMPT, build_verdict_user_prompt(facts))
    verdict = raw.strip() if raw else ""
    report = render_report(facts, verdict)

    # ── Grounded faithfulness (Layer 5) ──
    num_matched, num_total = numeric_grounding(report, facts)
    loc_matched, loc_total = location_grounding(report, facts)
    if delay:
        time.sleep(delay)
    grounding = call_llm(
        GROUNDING_SYSTEM_PROMPT,
        build_grounding_user_prompt(facts_for_grounding_prompt(facts), verdict),
        VerdictGrounding,
    )
    # Judge unavailable -> treat as unknown for this scenario (excluded from rate).
    verdict_hallucinated = None
    unsupported = []
    if grounding is not None:
        unsupported = grounding.unsupported_claims or []
        verdict_hallucinated = (not grounding.faithful) or bool(unsupported)

    if delay:
        time.sleep(delay)
    answers = call_llm(READER_SYSTEM_PROMPT, build_reader_user_prompt(report), ReaderAnswers)

    grounding_result = {
        "numeric_matched": num_matched, "numeric_total": num_total,
        "location_matched": loc_matched, "location_total": loc_total,
        "verdict_hallucinated": verdict_hallucinated,
        "unsupported_claims": unsupported,
    }

    if answers is None:
        return {"ok": False, "report": report, "ground_truth": gt, "grounding": grounding_result}

    field_correct = {
        "total_issues": answers.total_issues == gt["total_issues"],
        "critical_count": answers.critical_count == gt["critical_count"],
        "top_category": _norm(answers.top_category) == _norm(gt["top_category"]),
        "most_affected_area": _norm(answers.most_affected_area) == _norm(gt["most_affected_area"]),
        "top_priority_location": _loc_match(gt["top_priority_location"], answers.top_priority_location),
    }
    verdict_dir = classify_verdict_direction(verdict)
    return {
        "ok": True,
        "report": report,
        "verdict": verdict,
        "verdict_direction": verdict_dir,
        "verdict_direction_match": verdict_dir == gt["expected_direction"],
        "ground_truth": gt,
        "reader_answers": answers.model_dump(),
        "field_correct": field_correct,
        "grounding": grounding_result,
    }


READER_FIELDS = ["total_issues", "critical_count", "top_category", "most_affected_area", "top_priority_location"]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--scenarios", type=int, default=3, help="how many distinct briefings to test")
    p.add_argument("--sample", type=int, default=12, help="issues per briefing")
    p.add_argument("--model", default=None)
    p.add_argument("--delay", type=float, default=None,
                   help="seconds slept before each LLM call (default 1.5 when GROQ_API_KEY is set, else 0)")
    return p.parse_args()


def main():
    args = parse_args()
    if args.model:
        settings.LLM_MODEL = args.model
    delay = args.delay if args.delay is not None else (1.5 if settings.GROQ_API_KEY else 0.0)

    pool = pick_sample(args.scenarios * args.sample, args.seed)
    print(f"\n  Model: {settings.LLM_MODEL} | {args.scenarios} briefings x {args.sample} issues "
          f"(seed={args.seed}, delay={delay}s)")
    print(f"  Running {len(pool)} cases through the real pipeline first...\n")
    processed = process_pool(pool, delay)

    scenarios = []
    for s in range(args.scenarios):
        chunk = processed[s * args.sample:(s + 1) * args.sample]
        if not chunk:
            break
        print(f"  --- Briefing {s + 1}/{args.scenarios} ---")
        result = score_scenario(chunk, delay)
        scenarios.append(result)
        if result["ok"]:
            fc = result["field_correct"]
            print("    reader: " + "  ".join(f"{f}={'OK' if fc[f] else 'X'}" for f in READER_FIELDS))
            print(f"    verdict '{result['verdict']}' -> {result['verdict_direction']} "
                  f"(expected {result['ground_truth']['expected_direction']}) "
                  f"{'OK' if result['verdict_direction_match'] else 'MISS'}")
        else:
            print("    reader LLM returned nothing for this briefing (skipped in aggregate).")

    ok_scenarios = [s for s in scenarios if s["ok"]]
    per_field = {}
    for f in READER_FIELDS:
        vals = [1 if s["field_correct"][f] else 0 for s in ok_scenarios]
        per_field[f] = round(sum(vals) / len(vals) * 100, 1) if vals else None
    all_flags = [v for s in ok_scenarios for v in s["field_correct"].values()]
    overall = round(sum(1 for v in all_flags if v) / len(all_flags) * 100, 1) if all_flags else None
    verdict_matches = [s["verdict_direction_match"] for s in ok_scenarios]
    verdict_mismatch_pct = (
        round(sum(1 for m in verdict_matches if not m) / len(verdict_matches) * 100, 1) if verdict_matches else None
    )

    # ── Grounded faithfulness aggregation (Layer 5) ──
    g = [s["grounding"] for s in scenarios if s.get("grounding")]
    num_matched = sum(x["numeric_matched"] for x in g)
    num_total = sum(x["numeric_total"] for x in g)
    loc_matched = sum(x["location_matched"] for x in g)
    loc_total = sum(x["location_total"] for x in g)
    judged = [x for x in g if x["verdict_hallucinated"] is not None]
    reported_data_accuracy = round(num_matched / num_total * 100, 1) if num_total else None
    location_accuracy = round(loc_matched / loc_total * 100, 1) if loc_total else None
    hallucination_rate = (
        round(sum(1 for x in judged if x["verdict_hallucinated"]) / len(judged) * 100, 1) if judged else None
    )

    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    out_path = os.path.join(reports_dir, f"summary_actionability_{args.seed}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "model": settings.LLM_MODEL, "seed": args.seed,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "scenarios_run": len(ok_scenarios), "issues_per_scenario": args.sample,
            "reader_accuracy_per_field_pct": per_field,
            "reader_accuracy_overall_pct": overall,
            "verdict_direction_mismatch_pct": verdict_mismatch_pct,
            "grounding": {
                "reported_data_accuracy_pct": reported_data_accuracy,
                "location_accuracy_pct": location_accuracy,
                "verdict_hallucination_rate_pct": hallucination_rate,
                "numeric_checked": num_total, "location_checked": loc_total, "verdicts_judged": len(judged),
            },
            "scenarios": scenarios,
        }, f, indent=2, ensure_ascii=False)

    # ── Log headline metrics to the observability store (trends over time) ──
    run_id = new_run_id()
    model = settings.LLM_MODEL
    n_briefings = len(ok_scenarios)
    if overall is not None:
        log_metric("reader_actionability", "reader_accuracy_overall", overall, n_briefings, model, run_id)
    if verdict_mismatch_pct is not None:
        log_metric("reader_actionability", "verdict_direction_mismatch", verdict_mismatch_pct, len(verdict_matches), model, run_id)
    if reported_data_accuracy is not None:
        log_metric("summary_grounding", "reported_data_accuracy", reported_data_accuracy, num_total, model, run_id)
    if location_accuracy is not None:
        log_metric("summary_grounding", "location_accuracy", location_accuracy, loc_total, model, run_id)
    if hallucination_rate is not None:
        log_metric("summary_grounding", "hallucination_rate", hallucination_rate, len(judged), model, run_id)

    print(f"\n{'='*60}")
    print(f"  Task-Based Actionability + Grounded Faithfulness of the Briefing")
    print(f"  ({len(ok_scenarios)} briefing(s), model {settings.LLM_MODEL})")
    print(f"{'='*60}")
    for f in READER_FIELDS:
        val = per_field[f]
        print(f"  {f:<24}: {'-' if val is None else str(val) + '%'} answered correctly from the summary alone")
    print(f"  {'OVERALL reader accuracy':<24}: {'-' if overall is None else str(overall) + '%'}")
    print(f"  {'verdict direction miss':<24}: {'-' if verdict_mismatch_pct is None else str(verdict_mismatch_pct) + '%'}")
    print(f"  {'reported-data accuracy':<24}: {'-' if reported_data_accuracy is None else str(reported_data_accuracy) + '%'}  (numbers in summary that match the data)")
    print(f"  {'location accuracy':<24}: {'-' if location_accuracy is None else str(location_accuracy) + '%'}  (source locations that appear in the summary)")
    print(f"  {'verdict hallucination':<24}: {'-' if hallucination_rate is None else str(hallucination_rate) + '%'}  (verdicts making an unsupported claim)")
    print("\n  Reading: high reader accuracy = the summary is legible; high grounding + low")
    print("  hallucination = it is faithful to the underlying data (nothing invented).")
    print(f"\n  Saved -> {out_path}\n")


if __name__ == "__main__":
    main()
