"""
Backs the internal-only "Evaluation Console" (a separate, unlinked frontend
route for the engineering team — not something a citizen or leader ever sees).

Two distinct kinds of number live here, and they must not be blurred together:

1. Baseline numbers (load_baseline) — read straight off disk from the reports
   backend/eval/*.py already produced: run_eval.py's accuracy/F1/precision
   reports, plus the human rubric scores from score_extraction.py and
   score_actionability.py. Nothing here is computed live.

2. Live check (run_live_check) — runs a small (~10 case) fixed sample through
   the REAL pipeline right now, so a viewer can see current LLM behaviour
   between full eval runs. Deliberately small and fast (seconds, not the
   45-1,045 cases of a full run_eval.py pass) — it's a smoke check, not a
   replacement for the real suites, and its numbers are labelled as such.

Extraction quality and summary actionability are NOT auto-scored here, live
or otherwise — eval_plan.md deliberately keeps those human-rubric-only (no
LLM grading its own homework). The live check surfaces raw examples of both
for visual inspection instead of inventing a number for them.
"""
import glob
import json
import os
import time
from datetime import datetime, timezone

from app.config import settings
from app.models.db_models import UrgencyLevel
from app.pipeline.stages import run_gatekeeper, run_classifier, run_urgency_scorer, run_extractor
from app.pipeline.dedup import embed, cosine_similarity
from app.pipeline.facts import assign_tier
from app.llm.client import call_llm_text
from app.llm.prompts.summarize import VERDICT_SYSTEM_PROMPT, build_verdict_user_prompt, render_report

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_EVAL_DIR = os.path.join(_BACKEND_DIR, "eval")
_REPORTS_DIR = os.path.join(_EVAL_DIR, "reports")

_URGENCY_RANK = {"critical": 3, "high": 2, "medium": 1, "low": 0}
_URGENCY_ENUM = {
    "critical": UrgencyLevel.critical, "high": UrgencyLevel.high,
    "medium": UrgencyLevel.medium, "low": UrgencyLevel.low,
}

METRIC_EXPLANATIONS = {
    "gatekeeper": {
        "label": "Gatekeeper accuracy",
        "explains": "Measures how reliably the system distinguishes a genuine complaint or suggestion "
                    "from spam, off-topic text, vague input, or abusive content. This is the first "
                    "checkpoint every submission passes through: an error here means either irrelevant "
                    "content reaches the leader's dashboard, or a genuine complaint is filtered out "
                    "before it is ever seen.",
    },
    "classification": {
        "label": "Category accuracy",
        "explains": "Measures how often the predicted category (roads, water, electricity, and so on) "
                    "matches the citizen's own selection. This determines how reliable the category "
                    "breakdown is for identifying where issues are concentrated.",
    },
    "urgency_exact": {
        "label": "Urgency exact-match",
        "explains": "Measures how often the predicted urgency level (critical, high, medium, low) "
                    "exactly matches the correct label. Urgency determines how an issue is prioritized "
                    "in the leader's summary, so an incorrect label here directly affects which issues "
                    "get attention first.",
    },
    "urgency_within_one": {
        "label": "Urgency within one level",
        "explains": "Measures how often the predicted urgency is at most one severity level away from "
                    "correct (for example, 'high' when the correct label was 'critical'). This is a more "
                    "tolerant companion to exact-match, since a one-level error is a much smaller mistake "
                    "than confusing 'critical' with 'low'.",
    },
    "dedup": {
        "label": "Duplicate detection",
        "explains": "Measures whether multiple reports describing the same underlying issue, written "
                    "in different words, are correctly identified as duplicates. This allows a leader to "
                    "see a single consolidated item rather than several separate entries for the same "
                    "problem.",
    },
    "extraction": {
        "label": "Extraction quality (human-reviewed)",
        "explains": "Average score (1-5), assigned by a human reviewer, for how accurately the system "
                    "extracts location, issue summary, affected parties, and the citizen's request from "
                    "the original text. This is reviewed manually rather than automatically, since there "
                    "is no single correct phrasing to compare against — an automated score would only "
                    "reflect one model's assessment of another's wording, not actual accuracy.",
    },
    "actionability": {
        "label": "Dashboard actionability (human-reviewed)",
        "explains": "Average score (1-5), assigned by a human reviewer examining an actual rendered "
                    "summary, covering clarity, completeness, correct prioritization, absence of clutter, "
                    "and whether the recommended action can be understood without re-reading the original "
                    "complaint. This measures whether the summary is genuinely usable for someone reviewing "
                    "it under time constraints.",
    },
    "multilingual": {
        "label": "Multilingual support (Hindi / Marathi / Hinglish)",
        "explains": "Citizen complaints are not limited to English, so the system handles Hindi, Marathi, "
                    "and Hinglish (mixed English-Hindi text) through the same gatekeeper, category, and "
                    "urgency logic used for English — with no separate translation step and no "
                    "language-specific code path. The figures below compare accuracy for each language "
                    "against the English baseline above, so any meaningful gap is visible directly rather "
                    "than assumed away.",
    },
    "llm_judge": {
        "label": "Extraction quality (LLM-judge, validated against humans)",
        "explains": "An automated judge model scores each extraction on the same 1-5 rubric a human uses, "
                    "seeing only the citizen's original text and the extraction — never a reference answer — "
                    "so it must reason from the source. To avoid an LLM simply grading its own homework, the "
                    "judge is validated against the human-scored cases: the agreement figure (how often it "
                    "lands within one point of a human) is what makes its at-scale scores trustworthy. A "
                    "separate rule-based check flags summaries that merely copy the input verbatim.",
    },
    "summary_actionability": {
        "label": "Summary actionability (task-based reader test)",
        "explains": "Rather than rating the leader's briefing subjectively, this measures whether its key "
                    "facts can actually be recovered from it. A fresh model is shown ONLY the rendered "
                    "briefing (never the underlying data) and asked the questions a busy leader needs "
                    "answered — how many issues, how many critical, which category and area dominate, and "
                    "what to act on first — and its answers are checked against ground truth. High accuracy "
                    "means the summary genuinely conveys the situation at a glance.",
    },
}


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _latest(pattern, exclude=None):
    matches = sorted(glob.glob(os.path.join(_REPORTS_DIR, pattern)), reverse=True)
    if exclude:
        matches = [m for m in matches if exclude not in os.path.basename(m)]
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# 1. Baseline — read-only, no LLM calls
# ---------------------------------------------------------------------------

def load_baseline() -> dict:
    # Most recent run wins, regardless of suite — an old, larger "core" run
    # on a stale model is a worse baseline than yesterday's run on the model
    # actually in use. The suite/model/case-count are surfaced in the response
    # so the UI can label the number honestly instead of hiding the tradeoff.
    # The multilingual suite is excluded here — it's a small, dedicated check
    # with its own section below, not a substitute for the main English baseline.
    eval_path = _latest("eval_*.json", exclude="_multilingual.json")
    eval_report = _load_json(eval_path) if eval_path else None

    multilingual_path = _latest("eval_*_multilingual.json")
    multilingual_report = _load_json(multilingual_path) if multilingual_path else None

    extraction_path = _latest("extraction_scores_*.json")
    extraction_report = _load_json(extraction_path) if extraction_path else None

    actionability_path = _latest("actionability_scores_*.json")
    actionability_summary = None
    if actionability_path:
        raw = _load_json(actionability_path)
        states = raw.get("states", [])
        if states:
            dims = ["clarity", "completeness", "correct_prioritization", "absence_of_clutter", "actionability_of_ask"]
            actionability_summary = {
                "scorer": raw.get("scorer"),
                "n_states": len(states),
                "means": {d: round(sum(s["scores"][d] for s in states) / len(states), 2) for d in dims},
            }

    # Layer 3 — automated LLM-judge extraction scores + the human-agreement
    # validation that makes them credible (two separate report files).
    llm_judge_path = _latest("extraction_llm_scores_*.json")
    llm_judge_report = _load_json(llm_judge_path) if llm_judge_path else None
    llm_validation_path = _latest("extraction_llm_validation_*.json")
    llm_validation_report = _load_json(llm_validation_path) if llm_validation_path else None

    # Layer 4 — task-based reader-proxy actionability of the leader briefing.
    summary_act_path = _latest("summary_actionability_*.json")
    summary_act_report = _load_json(summary_act_path) if summary_act_path else None

    return {
        "explanations": METRIC_EXPLANATIONS,
        "eval_report_file": os.path.basename(eval_path) if eval_path else None,
        "eval_model": eval_report.get("model") if eval_report else None,
        "eval_suite": eval_report.get("suite") if eval_report else None,
        "eval_total_cases": eval_report.get("total_cases") if eval_report else None,
        "eval_timestamp": eval_report.get("timestamp") if eval_report else None,
        "eval": eval_report,
        "extraction_report_file": os.path.basename(extraction_path) if extraction_path else None,
        "extraction": extraction_report["summary"] if extraction_report else None,
        "actionability_report_file": os.path.basename(actionability_path) if actionability_path else None,
        "actionability": actionability_summary,
        "multilingual_report_file": os.path.basename(multilingual_path) if multilingual_path else None,
        "multilingual_model": multilingual_report.get("model") if multilingual_report else None,
        "multilingual_total_cases": multilingual_report.get("total_cases") if multilingual_report else None,
        "multilingual_timestamp": multilingual_report.get("timestamp") if multilingual_report else None,
        "multilingual": multilingual_report,
        # Layer 3 — LLM-judge extraction quality + its validation against humans.
        "llm_judge_report_file": os.path.basename(llm_judge_path) if llm_judge_path else None,
        "llm_judge": llm_judge_report,
        "llm_judge_validation_file": os.path.basename(llm_validation_path) if llm_validation_path else None,
        "llm_judge_validation": llm_validation_report,
        # Layer 4 — task-based reader-proxy actionability of the briefing.
        "summary_actionability_report_file": os.path.basename(summary_act_path) if summary_act_path else None,
        "summary_actionability": summary_act_report,
    }


# ---------------------------------------------------------------------------
# 2. Live check — small fixed sample, run through the real pipeline right now
# ---------------------------------------------------------------------------

def _pick_live_sample(n_categories: int = 8, n_invalid: int = 2) -> list:
    """One valid case per distinct category (deterministic — first occurrence
    in file order) + a couple of invalid ones, from the same hand-labeled
    test_cases.json the offline `core` suite uses — so a viewer can sanity-check
    against a small slice of the exact same ground truth."""
    cases = _load_json(os.path.join(_EVAL_DIR, "test_cases.json"))
    valid = [c for c in cases if c["is_valid_submission"]]
    invalid = [c for c in cases if not c["is_valid_submission"]]

    seen_categories = set()
    sample = []
    for c in valid:
        if c["category"] not in seen_categories:
            sample.append(c)
            seen_categories.add(c["category"])
        if len(seen_categories) >= n_categories:
            break
    sample += invalid[:n_invalid]
    return sample, cases


def _pick_dedup_pair(cases: list):
    groups = {}
    for c in cases:
        gid = c.get("duplicate_group_id")
        if gid:
            groups.setdefault(gid, []).append(c)
    for members in groups.values():
        if len(members) >= 2:
            return members[0], members[1]
    return None, None


def _acc(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total, "accuracy_pct": round(correct / total * 100, 1) if total else None}


def run_live_check(n_categories: int = 8, n_invalid: int = 2) -> dict:
    sample, all_cases = _pick_live_sample(n_categories, n_invalid)

    gk_correct = gk_total = 0
    cl_correct = cl_total = 0
    ug_exact = ug_within_one = ug_total = 0
    examples = []

    start = time.time()
    for case in sample:
        text = case["raw_text"]
        expected_valid = case["is_valid_submission"]

        try:
            gk_res = run_gatekeeper(text)
        except Exception:
            gk_res = None

        gk_total += 1
        predicted_valid = bool(gk_res and gk_res.label in ("valid_complaint", "valid_suggestion"))
        gk_ok = predicted_valid == expected_valid
        gk_correct += int(gk_ok)

        example = {
            "id": case["id"],
            "raw_text": text,
            "gatekeeper": {
                "expected_valid": expected_valid,
                "predicted_label": gk_res.label if gk_res else None,
                "correct": gk_ok,
            },
        }

        if expected_valid and gk_res:
            try:
                cl_res = run_classifier(text)
            except Exception:
                cl_res = None
            if cl_res:
                cl_total += 1
                cl_ok = cl_res.category.value == case["category"]
                cl_correct += int(cl_ok)
                example["classification"] = {
                    "expected": case["category"], "predicted": cl_res.category.value, "correct": cl_ok,
                }

            try:
                ug_res = run_urgency_scorer(text)
            except Exception:
                ug_res = None
            if ug_res:
                ug_total += 1
                predicted_urg = ug_res.urgency.value
                actual_urg = case["urgency"]
                exact = predicted_urg == actual_urg
                within_one = abs(_URGENCY_RANK.get(predicted_urg, 0) - _URGENCY_RANK.get(actual_urg, 0)) <= 1
                ug_exact += int(exact)
                ug_within_one += int(within_one)
                example["urgency"] = {
                    "expected": actual_urg, "predicted": predicted_urg,
                    "exact": exact, "within_one": within_one,
                }

            try:
                ext_res = run_extractor(text, None)
            except Exception:
                ext_res = None
            if ext_res:
                example["extraction"] = {
                    "location": ext_res.location,
                    "issue_summary": ext_res.issue_summary,
                    "affected_parties": ext_res.affected_parties,
                    "ask": ext_res.ask,
                }

        examples.append(example)

    # Dedup smoke check — one known-duplicate pair, embedding similarity only
    dedup_check = None
    d1, d2 = _pick_dedup_pair(all_cases)
    if d1 and d2:
        try:
            # cosine_similarity does numpy math internally — cast to native
            # Python types, since numpy.float64/numpy.bool_ aren't JSON-serializable.
            sim = float(cosine_similarity(embed(d1["raw_text"]), embed(d2["raw_text"])))
            predicted_dup = bool(sim >= 0.85)
            dedup_check = {
                "case_a": d1["raw_text"], "case_b": d2["raw_text"],
                "similarity": round(sim, 3), "threshold": 0.85,
                "predicted_duplicate": predicted_dup, "expected_duplicate": True,
                "correct": predicted_dup,
            }
        except Exception as e:
            dedup_check = {"error": str(e)}

    elapsed = time.time() - start

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": settings.LLM_MODEL,
        "elapsed_seconds": round(elapsed, 1),
        "sample_size": len(sample),
        "metrics": {
            "gatekeeper": _acc(gk_correct, gk_total),
            "classification": _acc(cl_correct, cl_total),
            "urgency_exact": _acc(ug_exact, ug_total),
            "urgency_within_one": _acc(ug_within_one, ug_total),
        },
        "dedup_smoke_check": dedup_check,
        "examples": examples,
    }


def compute_deltas(live_metrics: dict, baseline_eval: dict) -> dict:
    """Live-sample accuracy minus the offline baseline's, where both exist.
    Small-sample deltas are noisy by nature (n~8-10) — the frontend must
    label these as a smoke-check signal, not a statistically robust trend."""
    if not baseline_eval:
        return {}
    deltas = {}

    gk_base = (baseline_eval.get("gatekeeper") or {}).get("accuracy_pct")
    gk_live = live_metrics["gatekeeper"]["accuracy_pct"]
    if gk_base is not None and gk_live is not None:
        deltas["gatekeeper"] = round(gk_live - gk_base, 1)

    cl_base = (baseline_eval.get("classification") or {}).get("accuracy_pct")
    cl_live = live_metrics["classification"]["accuracy_pct"]
    if cl_base is not None and cl_live is not None:
        deltas["classification"] = round(cl_live - cl_base, 1)

    ug_base = (baseline_eval.get("urgency") or {}).get("exact_match_pct")
    ug_live = live_metrics["urgency_exact"]["accuracy_pct"]
    if ug_base is not None and ug_live is not None:
        deltas["urgency_exact"] = round(ug_live - ug_base, 1)

    return deltas


# ---------------------------------------------------------------------------
# 3. Live summary sample — illustrative only, not scored (see actionability above)
# ---------------------------------------------------------------------------

def run_live_summary_sample(examples: list, max_items: int = 3):
    issues = []
    for ex in examples:
        if "urgency" not in ex or "extraction" not in ex:
            continue
        urgency_enum = _URGENCY_ENUM.get(ex["urgency"]["predicted"])
        issues.append({
            "category": ex.get("classification", {}).get("predicted", "other"),
            "tier": assign_tier(urgency_enum, reopened=False, report_count=1),
            "location": ex["extraction"]["location"] or "not specified",
            "report_count": 1,
            "days_open": 0,
            "cluster_size": 0,
            "reopened_after_resolution": False,
        })
        if len(issues) >= max_items:
            break

    if not issues:
        return None

    category_tally: dict = {}
    for i in issues:
        category_tally[i["category"]] = category_tally.get(i["category"], 0) + 1
    critical_items = [
        {"category": i["category"], "location": i["location"], "urgency": "critical",
         "days_open": i["days_open"], "report_count": i["report_count"], "issue_summary": i["location"]}
        for i in issues if i["tier"] == "ACT TODAY"
    ]
    facts = {
        "submission_type": "complaint",
        "range_label": "Illustrative live sample (not a statistically meaningful count)",
        "total_current": len(issues), "total_previous": None,
        "category_tally": category_tally, "area_tally": {}, "urgency_tally": {},
        "category_deltas": {}, "critical_items": critical_items, "recurring": [],
        "systemic_categories": [], "top_supported": [],
    }
    user_prompt = build_verdict_user_prompt(facts)
    raw = call_llm_text(VERDICT_SYSTEM_PROMPT, user_prompt)
    verdict = raw.strip() if raw else "Unable to generate a summary."
    return render_report(facts, verdict)
