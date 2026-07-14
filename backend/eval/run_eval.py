"""
Civic Voice Agent — Evaluation Harness
Usage:
    cd backend
    python eval/run_eval.py                          # demo suite (default), LLM_MODEL from .env
    python eval/run_eval.py --model phi3:mini
    python eval/run_eval.py --suite core              # ~245-case suite, run every iteration
    python eval/run_eval.py --suite full              # full ~1,045-case suite (slow, multi-hour on CPU)
    python eval/run_eval.py --suite core --model qwen2.5:1.5b
    python eval/run_eval.py --suite core --model llama-3.1-8b-instant --delay 2.0  # slower Groq tier / persistent 429s

Suites (see eval_plan.md Phase D):
    demo  = datasets/prompt_eval.json (60 cases, 15 sampled from each of the four files
            below) -> default. Fast smoke-test / demo-day dataset only; NOT a substitute
            for core/full (see what_i_am_not_building.md).
    core  = test_cases.json (45) + datasets/edge_case_cases.json (200)   -> ~245 cases, run every iteration
    full  = core + datasets/category_cases.json (800)                    -> ~1,045 cases, run at milestones only
    multilingual = datasets/multilingual_cases.json (15: 5 Hindi + 5 Marathi + 5 Hinglish)
                   -> Roadmap Phase 14, genuinely new content, no dedup pairs authored here

Duplicate-detection evaluates against datasets/dedup_cases.json (100 cases) for
core/full, or the 15-case group-aware subset inside prompt_eval.json for demo —
independent of the LLM-stage cases either way, since it's embedding-only.
"""
import json
import os
import sys
import time
import argparse
from itertools import combinations
from collections import defaultdict

# Ensure backend/ is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import app modules (settings singleton is created here)
from app.config import settings
from app.pipeline.stages import run_gatekeeper, run_classifier, run_urgency_scorer
from app.db.eval_metrics import log_metric, new_run_id

GATEKEEPER_LABELS = [
    "valid_complaint", "valid_suggestion", "spam_or_gibberish",
    "off_topic", "too_vague_to_process", "abusive_or_harmful", "personal_emergency",
]
CATEGORY_LABELS = [
    "roads", "water", "electricity", "sanitation",
    "education", "healthcare", "safety", "other",
]


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Override LLM_MODEL for this run")
    parser.add_argument("--suite", default="demo", choices=["demo", "core", "full", "multilingual"],
                         help="demo = 60 fast cases (default), core = ~245 cases, full = ~1,045 cases (slow), "
                              "multilingual = 15 Hindi/Marathi/Hinglish cases (Roadmap Phase 14)")
    parser.add_argument("--delay", type=float, default=None,
                         help="seconds to sleep before each LLM call, to stay under a hosted "
                              "provider's tokens-per-minute cap (e.g. Groq's free tier: 6000 TPM, "
                              "easily exceeded by back-to-back calls at ~245+ cases). "
                              "Default: 1.5s when GROQ_API_KEY is set, 0s for local Ollama.")
    return parser.parse_args()


def _load_json(relpath):
    path = os.path.join(os.path.dirname(__file__), relpath)
    # Explicit UTF-8 — Windows' default locale encoding (cp1252) can't decode
    # the Hindi/Marathi/Devanagari content in multilingual_cases.json.
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cases(suite: str):
    if suite == "demo":
        demo = _load_json("datasets/prompt_eval.json")
        return demo["test_cases"] + demo["edge_cases"] + demo["category_cases"]
    if suite == "multilingual":
        return _load_json("datasets/multilingual_cases.json")
    cases = _load_json("test_cases.json") + _load_json("datasets/edge_case_cases.json")
    if suite == "full":
        cases += _load_json("datasets/category_cases.json")
    return cases


def load_dedup_cases(suite: str):
    if suite == "demo":
        return _load_json("datasets/prompt_eval.json")["dedup_cases"]
    if suite == "multilingual":
        return []  # no dedup pairs authored in this set; dedup is language-agnostic (embeddings), already covered elsewhere
    return _load_json("datasets/dedup_cases.json")


# ---------------------------------------------------------------------------
# Multiclass metrics: per-label precision/recall/F1 + confusion matrix
# ---------------------------------------------------------------------------

def compute_multiclass_metrics(labels: list, y_true: list, y_pred: list) -> dict:
    """Standard multiclass P/R/F1 (one-vs-rest per label) + confusion matrix.
    y_true/y_pred are lists of label strings; unseen predicted labels are tolerated
    (counted as false positives for that label) even if not in `labels`.
    """
    confusion = defaultdict(lambda: defaultdict(int))
    for t, p in zip(y_true, y_pred):
        confusion[t][p] += 1

    per_label = {}
    for lbl in labels:
        tp = confusion[lbl][lbl]
        fp = sum(confusion[t][lbl] for t in confusion if t != lbl)
        fn = sum(v for k, v in confusion[lbl].items() if k != lbl)
        support = sum(confusion[lbl].values())
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_label[lbl] = {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
            "support": support,
        }

    total = len(y_true)
    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    macro_p = sum(v["precision"] for v in per_label.values()) / len(labels) if labels else 0.0
    macro_r = sum(v["recall"] for v in per_label.values()) / len(labels) if labels else 0.0
    macro_f1 = sum(v["f1"] for v in per_label.values()) / len(labels) if labels else 0.0

    return {
        "accuracy_pct": round(correct / total * 100, 1) if total else 0.0,
        "correct": correct,
        "total": total,
        "macro_precision": round(macro_p, 3),
        "macro_recall": round(macro_r, 3),
        "macro_f1": round(macro_f1, 3),
        "per_label": per_label,
        "confusion_matrix": {t: dict(v) for t, v in confusion.items()},
    }


# ---------------------------------------------------------------------------
# Dedup evaluation — pairwise embedding cosine similarity
# ---------------------------------------------------------------------------

def embed_text(client, model: str, text: str):
    resp = client.embeddings(model=model, prompt=text)
    return resp["embedding"]


def cosine_sim(a, b):
    import numpy as np
    a, b = np.array(a), np.array(b)
    n = (np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / n) if n > 0 else 0.0


def run_dedup_eval(cases: list, threshold: float = 0.85) -> dict:
    """Pairwise embedding dedup: predict duplicate pairs then score against GT."""
    import ollama

    client = ollama.Client(host=settings.OLLAMA_HOST)
    valid = [c for c in cases if c["is_valid_submission"]]

    print(f"\n  Embedding {len(valid)} valid cases for dedup eval...")
    embeddings = {}
    for c in valid:
        try:
            embeddings[c["id"]] = embed_text(client, settings.EMBEDDING_MODEL, c["raw_text"])
        except Exception as e:
            print(f"    Embed error [{c['id']}]: {e}")

    predicted_pairs = set()
    ids = [c["id"] for c in valid if c["id"] in embeddings]
    for a_id, b_id in combinations(sorted(ids), 2):
        sim = cosine_sim(embeddings[a_id], embeddings[b_id])
        if sim >= threshold:
            predicted_pairs.add((a_id, b_id))

    groups = defaultdict(list)
    for c in cases:
        if c.get("duplicate_group_id") is not None:
            groups[c["duplicate_group_id"]].append(c["id"])

    true_pairs = set()
    for members in groups.values():
        for a, b in combinations(sorted(members), 2):
            true_pairs.add((a, b))

    tp = len(predicted_pairs & true_pairs)
    fp = len(predicted_pairs - true_pairs)
    fn = len(true_pairs - predicted_pairs)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

    return {
        "true_pairs": len(true_pairs),
        "predicted_pairs": len(predicted_pairs),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
    }


# ---------------------------------------------------------------------------
# Main eval
# ---------------------------------------------------------------------------

def run_eval(model_override: str = None, suite: str = "core", delay: float = None):
    if model_override:
        settings.LLM_MODEL = model_override

    # Groq's free/on-demand tier caps at 6000 tokens/minute — back-to-back calls
    # across a 245+ case suite exceed that reliably, triggering repeated 429s.
    # Local Ollama has no such external cap, so no delay is needed there.
    if delay is None:
        delay = 1.5 if settings.GROQ_API_KEY else 0.0

    model_name = settings.LLM_MODEL
    print(f"\n{'='*55}")
    print(f"  Civic Voice - Evaluation Run")
    print(f"  Model : {model_name}")
    print(f"  Suite : {suite}")
    print(f"  Delay : {delay}s between LLM calls")
    print(f"  Time  : {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    cases = load_cases(suite)
    urgency_map = {"critical": 3, "high": 2, "medium": 1, "low": 0}

    # Gatekeeper: multiclass (cases with an explicit expected_label) + legacy binary
    # (older test_cases.json entries only have is_valid_submission, not a specific label)
    gk_true, gk_pred = [], []
    legacy_binary_correct, legacy_binary_total = 0, 0

    # Classification: split complaint vs. suggestion, each its own confusion matrix
    cl_true = {"complaint": [], "suggestion": []}
    cl_pred = {"complaint": [], "suggestion": []}

    ug_exact = ug_within_one = ug_total = 0
    errors = []

    # Per-language breakdown (Roadmap Phase 14) — only populated for cases whose
    # id is prefixed ml_hi_/ml_mr_/ml_hin_ (the multilingual suite), so this stays
    # empty/absent for every other suite without any special-casing elsewhere.
    lang_stats = defaultdict(lambda: {
        "gk_correct": 0, "gk_total": 0,
        "cl_correct": 0, "cl_total": 0,
        "ug_exact": 0, "ug_total": 0,
    })

    def _language_group(cid: str):
        cid = str(cid)
        if cid.startswith("ml_hin_"):
            return "hinglish"
        if cid.startswith("ml_hi_"):
            return "hindi"
        if cid.startswith("ml_mr_"):
            return "marathi"
        return None

    start = time.time()
    print(f"\n  Running {len(cases)} test cases...\n")

    for case in cases:
        cid = case["id"]
        text = case["raw_text"]
        expected_valid = case["is_valid_submission"]
        expected_label = case.get("expected_label")
        submission_type = case.get("submission_type", "complaint")
        lang_group = _language_group(cid)

        # --- Stage 1: Gatekeeper ---
        if delay:
            time.sleep(delay)
        try:
            gk_res = run_gatekeeper(text)
        except Exception as e:
            gk_res = None
            errors.append(f"[{cid}] Gatekeeper exception: {e}")

        if gk_res is None:
            errors.append(f"[{cid}] Gatekeeper returned None")
            continue

        if expected_label:
            gk_true.append(expected_label)
            gk_pred.append(gk_res.label)
            if gk_res.label != expected_label:
                errors.append(f"[{cid}] GK mismatch: predicted={gk_res.label!r} expected={expected_label!r}")
        else:
            legacy_binary_total += 1
            predicted_valid = gk_res.label in ("valid_complaint", "valid_suggestion")
            if predicted_valid == expected_valid:
                legacy_binary_correct += 1
            else:
                errors.append(f"[{cid}] GK binary mismatch: predicted_valid={predicted_valid} expected_valid={expected_valid} label={gk_res.label!r}")

        if lang_group:
            lang_stats[lang_group]["gk_total"] += 1
            # Exact 7-label match — same standard as the "combined" multiclass
            # number above. The coarser valid/invalid check would silently
            # mark a wrong-but-still-invalid label (e.g. abusive_or_harmful
            # instead of too_vague_to_process) as "correct" here even though
            # it's flagged as an error above — that inconsistency previously
            # showed 100% for a language that actually had a real miss.
            gk_correct_for_lang = (
                gk_res.label == expected_label if expected_label
                else (gk_res.label in ("valid_complaint", "valid_suggestion")) == expected_valid
            )
            if gk_correct_for_lang:
                lang_stats[lang_group]["gk_correct"] += 1

        if not expected_valid:
            continue

        # --- Stage 2: Classification ---
        if delay:
            time.sleep(delay)
        try:
            cl_res = run_classifier(text)
        except Exception as e:
            cl_res = None
            errors.append(f"[{cid}] Classifier exception: {e}")

        if cl_res is None:
            errors.append(f"[{cid}] Classifier returned None")
        else:
            bucket = submission_type if submission_type in cl_true else "complaint"
            cl_true[bucket].append(case["category"])
            cl_pred[bucket].append(cl_res.category.value)
            if cl_res.category.value != case["category"]:
                errors.append(f"[{cid}] CL mismatch: predicted={cl_res.category.value!r} expected={case['category']!r}")
            if lang_group:
                lang_stats[lang_group]["cl_total"] += 1
                if cl_res.category.value == case["category"]:
                    lang_stats[lang_group]["cl_correct"] += 1

        # --- Stage 3: Urgency (complaints only) ---
        if submission_type == "complaint":
            if delay:
                time.sleep(delay)
            try:
                ug_res = run_urgency_scorer(text)
            except Exception as e:
                ug_res = None
                errors.append(f"[{cid}] Urgency exception: {e}")

            if ug_res is None:
                errors.append(f"[{cid}] Urgency returned None")
            else:
                ug_total += 1
                predicted_urg = ug_res.urgency.value
                actual_urg = case["urgency"]
                if predicted_urg == actual_urg:
                    ug_exact += 1
                if abs(urgency_map.get(predicted_urg, 0) - urgency_map.get(actual_urg, 0)) <= 1:
                    ug_within_one += 1
                else:
                    errors.append(f"[{cid}] UG off by >1: predicted={predicted_urg!r} expected={actual_urg!r}")
                if lang_group:
                    lang_stats[lang_group]["ug_total"] += 1
                    if predicted_urg == actual_urg:
                        lang_stats[lang_group]["ug_exact"] += 1

        # Some Windows terminal codepages can't print Devanagari/non-ASCII text
        # and would otherwise crash mid-run, losing every result gathered so far
        # (this report is only written once, at the end) — degrade to a safe
        # transliteration instead of raising.
        try:
            print(f"  [{cid}] done  {text[:50]}...")
        except UnicodeEncodeError:
            safe_text = text[:50].encode("ascii", errors="replace").decode("ascii")
            print(f"  [{cid}] done  {safe_text}...")

    elapsed_llm = time.time() - start

    # --- Dedup (embedding-based, model-agnostic, always the new 100-case set) ---
    dedup = run_dedup_eval(load_dedup_cases(suite))

    elapsed = time.time() - start

    gk_multiclass = compute_multiclass_metrics(GATEKEEPER_LABELS, gk_true, gk_pred) if gk_true else None
    legacy_binary_acc = round(legacy_binary_correct / legacy_binary_total * 100, 1) if legacy_binary_total else None

    cl_complaint = compute_multiclass_metrics(CATEGORY_LABELS, cl_true["complaint"], cl_pred["complaint"]) if cl_true["complaint"] else None
    cl_suggestion = compute_multiclass_metrics(CATEGORY_LABELS, cl_true["suggestion"], cl_pred["suggestion"]) if cl_true["suggestion"] else None

    ug_exact_pct = round(ug_exact / ug_total * 100, 1) if ug_total else 0.0
    ug_tol_pct = round(ug_within_one / ug_total * 100, 1) if ug_total else 0.0

    # Combined top-level numbers (kept for run_eval_compare.py / backward compatibility)
    gk_combined_correct = (gk_multiclass["correct"] if gk_multiclass else 0) + legacy_binary_correct
    gk_combined_total = (gk_multiclass["total"] if gk_multiclass else 0) + legacy_binary_total
    cl_combined_correct = (cl_complaint["correct"] if cl_complaint else 0) + (cl_suggestion["correct"] if cl_suggestion else 0)
    cl_combined_total = (cl_complaint["total"] if cl_complaint else 0) + (cl_suggestion["total"] if cl_suggestion else 0)

    summary = f"""
{'='*55}
  Results for model: {model_name}  (suite: {suite})
{'='*55}
  Total cases   : {len(cases)}
  Elapsed (LLM) : {elapsed_llm:.1f}s
  Elapsed total : {elapsed:.1f}s

  [Gatekeeper - combined]
    Accuracy          : {gk_combined_correct / gk_combined_total * 100 if gk_combined_total else 0:.1f}%  ({gk_combined_correct}/{gk_combined_total})"""
    if gk_multiclass:
        summary += f"""
  [Gatekeeper - 7-label breakdown, {gk_multiclass['total']} cases with explicit expected_label]
    Macro F1          : {gk_multiclass['macro_f1']}
    Per label         : """ + ", ".join(f"{lbl}={v['f1']}" for lbl, v in gk_multiclass["per_label"].items())
    if legacy_binary_total:
        summary += f"""
  [Gatekeeper - legacy binary, {legacy_binary_total} cases without expected_label]
    Accuracy          : {legacy_binary_acc}%  ({legacy_binary_correct}/{legacy_binary_total})"""

    summary += f"""

  [Category Classification - combined]
    Accuracy          : {cl_combined_correct / cl_combined_total * 100 if cl_combined_total else 0:.1f}%  ({cl_combined_correct}/{cl_combined_total})"""
    if cl_complaint:
        summary += f"""
  [Category - complaints, {cl_complaint['total']} cases]
    Macro F1          : {cl_complaint['macro_f1']}
    Per category      : """ + ", ".join(f"{lbl}={v['f1']}" for lbl, v in cl_complaint["per_label"].items())
    if cl_suggestion:
        summary += f"""
  [Category - suggestions, {cl_suggestion['total']} cases]
    Macro F1          : {cl_suggestion['macro_f1']}
    Per category      : """ + ", ".join(f"{lbl}={v['f1']}" for lbl, v in cl_suggestion["per_label"].items())

    summary += f"""

  [Urgency Scoring]
    Exact match       : {ug_exact_pct:.1f}%  ({ug_exact}/{ug_total})
    Within-one-level  : {ug_tol_pct:.1f}%  ({ug_within_one}/{ug_total})

  [Duplicate Detection]  (embedding cosine >= 0.85, model-agnostic, datasets/dedup_cases.json)
    True pairs (GT)   : {dedup['true_pairs']}
    Predicted pairs   : {dedup['predicted_pairs']}
    TP / FP / FN      : {dedup['tp']} / {dedup['fp']} / {dedup['fn']}
    Precision         : {dedup['precision']:.3f}
    Recall            : {dedup['recall']:.3f}

  Errors / mismatches logged: {len(errors)}
{'='*55}"""
    print(summary)

    if errors:
        print("  Error detail (first 30):")
        for e in errors[:30]:
            print(f"    {e}")
        if len(errors) > 30:
            print(f"    ... and {len(errors) - 30} more (see saved report)")

    # Save JSON report
    reports_dir = os.path.join(os.path.dirname(__file__), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe_model = model_name.replace(":", "_").replace("/", "_")
    report_path = os.path.join(reports_dir, f"eval_{ts}_{safe_model}_{suite}.json")

    report_data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model_name,
        "suite": suite,
        "total_cases": len(cases),
        "elapsed_llm_seconds": round(elapsed_llm, 2),
        "elapsed_total_seconds": round(elapsed, 2),
        # Backward-compatible top-level summary (consumed by run_eval_compare.py)
        "gatekeeper": {
            "accuracy_pct": round(gk_combined_correct / gk_combined_total * 100, 1) if gk_combined_total else 0.0,
            "correct": gk_combined_correct,
            "total": gk_combined_total,
        },
        "classification": {
            "accuracy_pct": round(cl_combined_correct / cl_combined_total * 100, 1) if cl_combined_total else 0.0,
            "correct": cl_combined_correct,
            "total": cl_combined_total,
        },
        "urgency": {
            "exact_match_pct": ug_exact_pct,
            "within_one_pct": ug_tol_pct,
            "exact_correct": ug_exact,
            "within_one_correct": ug_within_one,
            "total": ug_total,
        },
        "dedup": dedup,
        # New detailed breakdowns (Phase D)
        "gatekeeper_multiclass": gk_multiclass,
        "gatekeeper_legacy_binary": {
            "accuracy_pct": legacy_binary_acc, "correct": legacy_binary_correct, "total": legacy_binary_total,
        } if legacy_binary_total else None,
        "classification_complaint": cl_complaint,
        "classification_suggestion": cl_suggestion,
        # Roadmap Phase 14 — per-language breakdown, present only when the
        # loaded cases actually include ml_hi_/ml_mr_/ml_hin_-prefixed ids.
        "language_breakdown": {
            lang: {
                "gatekeeper_pct": round(s["gk_correct"] / s["gk_total"] * 100, 1) if s["gk_total"] else None,
                "category_pct": round(s["cl_correct"] / s["cl_total"] * 100, 1) if s["cl_total"] else None,
                "urgency_exact_pct": round(s["ug_exact"] / s["ug_total"] * 100, 1) if s["ug_total"] else None,
                "n": s["gk_total"],
            }
            for lang, s in lang_stats.items()
        } if lang_stats else None,
        "errors": errors,
    }

    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=2)

    # Log headline metrics to the observability store (trends over time).
    run_id = new_run_id()
    if gk_combined_total:
        log_metric("classification", "gatekeeper_accuracy", report_data["gatekeeper"]["accuracy_pct"], gk_combined_total, model_name, run_id)
    if cl_combined_total:
        log_metric("classification", "category_accuracy", report_data["classification"]["accuracy_pct"], cl_combined_total, model_name, run_id)
    if ug_total:
        log_metric("classification", "urgency_exact", ug_exact_pct, ug_total, model_name, run_id)
    log_metric("classification", "dedup_precision", dedup["precision"] * 100, dedup["true_pairs"], model_name, run_id)
    log_metric("classification", "dedup_recall", dedup["recall"] * 100, dedup["true_pairs"], model_name, run_id)

    print(f"\n  Report saved -> {report_path}\n")
    return report_data


if __name__ == "__main__":
    args = parse_args()
    run_eval(model_override=args.model, suite=args.suite, delay=args.delay)
