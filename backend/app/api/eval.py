"""
Internal-only endpoints backing the Evaluation Console — an engineering-facing
page, deliberately not linked from the citizen or leader UI (see frontend
routing). Read app/pipeline/live_eval.py for what "baseline" vs "live" means.
"""
from fastapi import APIRouter
from app.pipeline import live_eval
from app.db.eval_metrics import fetch_trends

router = APIRouter(prefix="/eval", tags=["Eval"])

# Plain-English label + intent for each tracked metric, so the observability
# dashboard can explain a trend line without hard-coding copy in the frontend.
_METRIC_META = {
    "gatekeeper_accuracy":          {"label": "Gatekeeper accuracy", "goal": "up", "unit": "%"},
    "category_accuracy":            {"label": "Category accuracy", "goal": "up", "unit": "%"},
    "urgency_exact":                {"label": "Urgency exact-match", "goal": "up", "unit": "%"},
    "dedup_precision":              {"label": "Dedup precision", "goal": "up", "unit": "%"},
    "dedup_recall":                 {"label": "Dedup recall", "goal": "up", "unit": "%"},
    "extraction_quality_mean":      {"label": "Extraction quality (judge, 1-5)", "goal": "up", "unit": ""},
    "verbatim_copy_flagged":        {"label": "Verbatim-copy flagged", "goal": "down", "unit": "%"},
    "judge_human_agreement_within1":{"label": "Judge–human agreement (±1pt)", "goal": "up", "unit": "%"},
    "reader_accuracy_overall":      {"label": "Summary reader accuracy", "goal": "up", "unit": "%"},
    "verdict_direction_mismatch":   {"label": "Verdict direction mismatch", "goal": "down", "unit": "%"},
    "reported_data_accuracy":       {"label": "Reported-data accuracy", "goal": "up", "unit": "%"},
    "location_accuracy":            {"label": "Location accuracy", "goal": "up", "unit": "%"},
    "hallucination_rate":           {"label": "Verdict hallucination rate", "goal": "down", "unit": "%"},
}


@router.get("/report")
def get_eval_report():
    """Static numbers already on disk — no LLM calls, safe to poll freely."""
    return live_eval.load_baseline()


@router.get("/trends")
def get_eval_trends(limit: int = 20):
    """
    Observability: the last `limit` runs of each tracked metric, oldest->newest,
    for the trend sparklines. Reads the append-only eval_metrics store — no LLM
    calls, safe to poll. Metrics accumulate as the eval scripts are re-run.
    """
    series = fetch_trends(limit)
    return {"metrics_meta": _METRIC_META, "trends": series}


@router.post("/live")
def run_live_eval():
    """Runs a small (~10 case) fixed sample through the real pipeline right now."""
    baseline = live_eval.load_baseline()
    result = live_eval.run_live_check()
    result["deltas"] = live_eval.compute_deltas(result["metrics"], baseline.get("eval") or {})
    result["live_summary_sample"] = live_eval.run_live_summary_sample(result["examples"])
    result["baseline"] = baseline
    return result
