from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.db.session import get_session
from app.models.db_models import Complaint, Leader, SubmissionType, Status, UrgencyLevel, PipelineStatus
from app.auth.deps import get_current_leader
from app.llm.client import call_llm_text
from app.llm.prompts.summarize import (
    VERDICT_SYSTEM_PROMPT,
    build_verdict_user_prompt,
    render_report,
)
from app.pipeline.facts import build_issue_facts
from app.utils.validators import mask_phone

router = APIRouter(prefix="/stats", tags=["Stats"])

# ---------------------------------------------------------------------------
# Same cutoff convention as /complaints and /stats/trends's own local map, so
# a given time_range value means the identical window everywhere in the app.
_TIME_RANGE_DAYS = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "6mo": 182, "1y": 365}

# ---------------------------------------------------------------------------
# In-memory 15-minute report cache
# Key: (time_range, submission_type, fingerprint of matching ids) -> {"report": str, "generated_at": datetime}
# ---------------------------------------------------------------------------
_report_cache: dict = {}
_CACHE_TTL_MINUTES = 15


def _valid_complaints(all_records):
    """
    Filter helper: returns only records that are:
      - submission_type == complaint  (not a suggestion)
      - pipeline_status == done       (fully processed, not a pending/processing stub)
      - is_valid_submission == True   (not spam / off-topic / too vague)
    """
    return [
        c for c in all_records
        if c.submission_type == SubmissionType.complaint
        and c.pipeline_status == PipelineStatus.done
        and c.is_valid_submission is True
    ]


@router.get("/summary")
def get_summary(session: Session = Depends(get_session), leader: Leader = Depends(get_current_leader)):
    all_records = session.exec(select(Complaint).where(Complaint.concerned_leader_id == leader.id)).all()

    complaints = _valid_complaints(all_records)
    suggestions = [
        c for c in all_records
        if c.submission_type == SubmissionType.suggestion
    ]

    total_issues   = len(complaints)
    open_count     = sum(1 for c in complaints if c.status == Status.open)
    resolved_count = sum(1 for c in complaints if c.status == Status.resolved)
    suggestions_count = len(suggestions)

    critical_count = sum(
        1 for c in complaints
        if c.status != Status.resolved
        and c.urgency_level == UrgencyLevel.critical
    )

    return {
        "total_issues": total_issues,
        "open":         open_count,
        "resolved":     resolved_count,
        "suggestions":  suggestions_count,
        "critical":     critical_count,
    }


@router.get("/trends")
def get_trends(
    session:    Session = Depends(get_session),
    leader:     Leader  = Depends(get_current_leader),
    time_range: str     = Query("all", description="24h | 7d | 30d | all"),
):
    all_records = session.exec(select(Complaint).where(Complaint.concerned_leader_id == leader.id)).all()

    # Only count valid, fully-processed complaints in charts
    all_complaints = _valid_complaints(all_records)

    # ── Apply time filter ──
    now = datetime.now(timezone.utc)
    cutoff_map = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "6mo": 182, "1y": 365}
    days = cutoff_map.get(time_range)
    if days:
        cutoff = now - timedelta(days=days)
        def _aware(dt):
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        complaints = [c for c in all_complaints if _aware(c.created_at) >= cutoff]
    else:
        complaints = all_complaints

    by_category = {}
    by_area     = {}
    by_urgency  = {}
    by_date: dict = {}  # YYYY-MM-DD → {open, resolved, in_progress}

    for c in complaints:
        cat = c.category.value if c.category else "other"
        by_category[cat] = by_category.get(cat, 0) + 1

        area_key = c.location_area or "not specified"
        by_area[area_key] = by_area.get(area_key, 0) + 1

        if c.urgency_level:
            urg = c.urgency_level.value
            by_urgency[urg] = by_urgency.get(urg, 0) + 1

        # Date-grouped trend
        if c.created_at:
            day = c.created_at.strftime("%Y-%m-%d")
            if day not in by_date:
                by_date[day] = {"date": day, "open": 0, "resolved": 0, "in_progress": 0}
            status_key = c.status.value if c.status.value in ("open", "resolved", "in_progress") else "open"
            by_date[day][status_key] += 1

    # Sort by_date chronologically
    by_date_list = sorted(by_date.values(), key=lambda d: d["date"])

    # ── Top recurring (by report_count) across ALL time ──
    top_recurring = sorted(
        [c for c in all_complaints if c.duplicate_of is None],
        key=lambda c: -(c.report_count or 1)
    )[:8]
    top_recurring_data = [
        {
            "id":       str(c.id),
            "summary":  c.extracted_issue_summary or c.raw_text[:80],
            "category": c.category.value if c.category else "other",
            "area":     c.location_area,
            "count":    c.report_count or 1,
            "urgency":  c.urgency_level.value if c.urgency_level else None,
            "status":   c.status.value,
        }
        for c in top_recurring
    ]

    # ── KPI: most common category and most affected area ──
    kpi_most_common_category = max(by_category, key=by_category.get) if by_category else None
    kpi_most_affected_area   = max(by_area,      key=by_area.get)     if by_area     else None

    return {
        "by_category":            by_category,
        "by_area":                by_area,
        "by_urgency":             by_urgency,
        "by_date":                by_date_list,
        "top_recurring":          top_recurring_data,
        "kpi_most_common_category": kpi_most_common_category,
        "kpi_most_affected_area":   kpi_most_affected_area,
        "total_in_range":         len(complaints),
        "time_range":             time_range,
    }



def _period_bounds(time_range: str, now: datetime):
    days = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "6mo": 182, "1y": 365}.get(time_range)
    if not days:
        return None, None
    cur_start = now - timedelta(days=days)
    return cur_start - timedelta(days=days), cur_start


def _tally(items, attr):
    d: dict = {}
    for c in items:
        v = getattr(c, attr)
        key = v.value if hasattr(v, "value") else v
        if key is None:
            continue
        d[key] = d.get(key, 0) + 1
    return d


_RANGE_LABELS = {
    "24h": "Last 24 hours", "7d": "Last 7 days", "15d": "Last 15 days",
    "30d": "Last 30 days (1 month)", "6mo": "Last 6 months", "1y": "Last 1 year", "all": "All time",
}


@router.get("/issues")
def get_issues(
    session:    Session = Depends(get_session),
    leader:     Leader  = Depends(get_current_leader),
    submission_type: str = Query("complaint", description="complaint | suggestion"),
    archived:   bool = Query(False, description="False (default) = active issues only; True = resolved/archived issues"),
    time_range: Optional[str] = Query(None, description="24h | 7d | 15d | 30d | 6mo | 1y"),
):
    """
    Returns ALL valid, non-duplicate complaints or suggestions — no top-N cap
    — ordered by most recent first, for the dashboard's full issue list
    (client-side filtered/paginated from there). Scoped to this leader's own
    jurisdiction (FR9/FR10) — never another leader's complaints.

    Resolved issues are archived: they're excluded from the default (active)
    list and only returned when archived=True, so the leader's main dashboard
    only ever shows things still needing attention.
    """
    all_records = session.exec(select(Complaint).where(Complaint.concerned_leader_id == leader.id)).all()

    if submission_type == "suggestion":
        items = [
            c for c in all_records
            if c.submission_type == SubmissionType.suggestion
            and c.pipeline_status == PipelineStatus.done
            and c.is_valid_submission is True
            and c.duplicate_of is None
        ]
    else:
        items = [c for c in _valid_complaints(all_records) if c.duplicate_of is None]

    if archived:
        items = [c for c in items if c.status == Status.resolved]
    else:
        items = [c for c in items if c.status != Status.resolved]

    days = _TIME_RANGE_DAYS.get(time_range)
    if days:
        def _aware(dt):
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        items = [c for c in items if c.created_at and _aware(c.created_at) >= cutoff]

    items.sort(key=lambda c: -(c.created_at.timestamp() if c.created_at else 0))

    issues_data = [
        {
            "id":                         str(c.id),
            "category":                   c.category.value if c.category else "other",
            "location_area":              c.location_area,
            "location_pincode":           c.location_pincode,
            "urgency_level":              c.urgency_level.value if c.urgency_level else None,
            "urgency_reasoning":          c.urgency_reasoning,
            "extracted_location":         c.extracted_location,
            "extracted_issue_summary":    c.extracted_issue_summary,
            "extracted_affected_parties": c.extracted_affected_parties,
            "extracted_ask":              c.extracted_ask,
            "report_count":               c.report_count,
            "status":                     c.status.value,
            "created_at":                 c.created_at.isoformat() if c.created_at else None,
            "raw_text":                   c.raw_text,
            "citizen_name":               c.citizen_name,
            "citizen_last_name":          c.citizen_last_name,
            "citizen_phone":              mask_phone(c.citizen_phone),  # FR12 — revealed via POST /complaints/{id}/reveal-phone
            "pipeline_status":            c.pipeline_status.value if c.pipeline_status else None,
            "is_valid_submission":        c.is_valid_submission,
            **build_issue_facts(c, session),
        }
        for c in items
    ]

    return {"issues": issues_data, "total_matched": len(issues_data)}


def build_report_facts(matching: list, session: Session, submission_type: str, time_range: str) -> dict:
    """
    Aggregates facts across ALL matching items in the time range — never a
    top-N slice — so the AI narrative (see llm/prompts/summarize.py) reflects
    the whole picture. Reused by both the live endpoint below and
    eval/score_actionability.py, so it takes plain data (no FastAPI
    request/session coupling beyond the session itself, needed for
    build_issue_facts's cluster-size lookups).
    """
    now = datetime.now(timezone.utc)

    def _aware(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    prev_start, cur_start = _period_bounds(time_range, now)
    if cur_start:
        current  = [c for c in matching if _aware(c.created_at) >= cur_start]
        previous = [c for c in matching if prev_start <= _aware(c.created_at) < cur_start]
    else:
        current, previous = matching, []

    category_tally      = _tally(current, "category")
    category_tally_prev = _tally(previous, "category")
    area_tally           = _tally(current, "location_area")
    urgency_tally        = _tally(current, "urgency_level") if submission_type == "complaint" else {}

    category_deltas = {
        cat: category_tally.get(cat, 0) - category_tally_prev.get(cat, 0)
        for cat in (set(category_tally) | set(category_tally_prev))
    } if previous else {}

    critical_items = []
    if submission_type == "complaint":
        def _spotlight(urgency_level, cap):
            picked = [c for c in current if c.urgency_level == urgency_level and c.status != Status.resolved]
            picked.sort(key=lambda c: -(c.report_count or 1))
            for c in picked[:cap]:
                f = build_issue_facts(c, session)
                critical_items.append({
                    "category": c.category.value if c.category else "other",
                    "location": f["location"],
                    "urgency": urgency_level.value,
                    "days_open": f["days_open"],
                    "report_count": f["report_count"],
                    "issue_summary": c.extracted_issue_summary or c.raw_text[:80],
                })
        _spotlight(UrgencyLevel.critical, 8)
        if not critical_items:
            # Quiet period for critical items — surface "high" instead so the
            # briefing still has something concrete rather than an empty section.
            _spotlight(UrgencyLevel.high, 5)

    # Recurring: total reports at a (category, location) spot >= 3, across the
    # WHOLE current set (not just the spotlighted critical items).
    recurring = []
    seen_spots = set()
    for c in current:
        f = build_issue_facts(c, session)
        key = (c.category, f["location"])
        if key in seen_spots:
            continue
        total_at_spot = f["cluster_size"] + (c.report_count or 1)
        if total_at_spot >= 3:
            seen_spots.add(key)
            recurring.append({
                "category": c.category.value if c.category else "other",
                "location": f["location"],
                "report_count": total_at_spot,
            })
    recurring.sort(key=lambda r: -r["report_count"])
    recurring = recurring[:8]

    # Systemic patterns: same category recurring across MULTIPLE DIFFERENT
    # areas (distinct from `recurring` above, which is the same exact spot)
    # — this is the "citywide process problem" signal vs. a single hotspot.
    category_areas: dict = {}
    for c in current:
        if not c.location_area or c.location_area.strip().lower() == "not specified":
            continue
        cat = c.category.value if c.category else "other"
        category_areas.setdefault(cat, set()).add(c.location_area)
    systemic_categories = sorted(
        [{"category": cat, "area_count": len(areas)} for cat, areas in category_areas.items() if len(areas) >= 3],
        key=lambda s: -s["area_count"],
    )

    top_supported = []
    if submission_type == "suggestion":
        supported = sorted(current, key=lambda c: -(c.report_count or 1))[:6]
        for c in supported:
            f = build_issue_facts(c, session)
            top_supported.append({
                "category": c.category.value if c.category else "other",
                "location": f["location"],
                "report_count": f["report_count"],
                "issue_summary": c.extracted_issue_summary or c.raw_text[:80],
            })

    return {
        "submission_type": submission_type,
        "range_label": _RANGE_LABELS.get(time_range, time_range),
        "total_current": len(current),
        "total_previous": len(previous) if previous else None,
        "category_tally": category_tally,
        "area_tally": area_tally,
        "urgency_tally": urgency_tally,
        "category_deltas": category_deltas,
        "critical_items": critical_items,
        "recurring": recurring,
        "systemic_categories": systemic_categories,
        "top_supported": top_supported,
    }


@router.get("/summary-report")
def get_summary_report(
    session:    Session = Depends(get_session),
    leader:     Leader  = Depends(get_current_leader),
    time_range: str     = Query("7d", description="24h | 7d | 15d | 30d | 6mo | 1y"),
    submission_type: str = Query("complaint", description="complaint | suggestion"),
    refresh:    bool    = Query(False, description="Force regenerate — bypass cache"),
):
    """
    A genuine executive-briefing narrative covering ALL matching items in
    the time range — not a top-10 slice, not a per-issue listing. See
    llm/prompts/summarize.py for why this is structured as synthesis.
    """
    now = datetime.now(timezone.utc)
    all_records = session.exec(select(Complaint).where(Complaint.concerned_leader_id == leader.id)).all()

    if submission_type == "suggestion":
        matching = [
            c for c in all_records
            if c.submission_type == SubmissionType.suggestion
            and c.pipeline_status == PipelineStatus.done
            and c.is_valid_submission is True
            and c.duplicate_of is None
        ]
    else:
        matching = [c for c in _valid_complaints(all_records) if c.duplicate_of is None]

    facts = build_report_facts(matching, session, submission_type, time_range)

    # Cache key fingerprints the exact matching id set, so any DB change
    # (new submission, status update) invalidates it automatically.
    fingerprint = tuple(sorted(str(c.id) for c in matching))
    cache_key = (time_range, submission_type, fingerprint)

    cached = _report_cache.get(cache_key)
    if cached and not refresh:
        age = (now - cached["generated_at"]).total_seconds() / 60
        if age < _CACHE_TTL_MINUTES:
            return {
                "report": cached["report"], "generated_at": cached["generated_at"].isoformat(),
                "cached": True, "cache_age_minutes": round(age, 1), "total_in_range": facts["total_current"],
            }

    if facts["total_current"] == 0:
        kind = "complaints" if submission_type == "complaint" else "suggestions"
        report_text = f"**SNAPSHOT ({facts['range_label']})**\n• 0 {kind} in this period."
    else:
        user_prompt = build_verdict_user_prompt(facts)
        raw_response = call_llm_text(VERDICT_SYSTEM_PROMPT, user_prompt)
        verdict = raw_response.strip() if raw_response else None
        report_text = render_report(facts, verdict)

    _report_cache[cache_key] = {"report": report_text, "generated_at": now}

    return {
        "report": report_text,
        "generated_at": now.isoformat(),
        "cached": False,
        "cache_age_minutes": 0,
        "total_in_range": facts["total_current"],
    }
