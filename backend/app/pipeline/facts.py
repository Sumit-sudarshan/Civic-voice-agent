"""
Computes the per-issue facts that drive the leader-facing summary: an
action tier and the structured signals behind it. Everything here is plain
Python over the DB — no LLM. The LLM's only job (see llm/prompts/summarize.py)
is to phrase a one-line justification from these facts, never to invent or
judge the tier itself, so the tier stays independently auditable/testable.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlmodel import Session, select
from app.models.db_models import Complaint, Status, UrgencyLevel

TIER_ACT_TODAY = "ACT TODAY"
TIER_ESCALATE = "ESCALATE"
TIER_THIS_WEEK = "THIS WEEK"
TIER_WATCH = "WATCH"
TIER_ROUTINE = "ROUTINE"

RECURRING_REPORT_THRESHOLD = 3


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def compute_cluster_size(session: Session, complaint: Complaint) -> int:
    """
    Count OTHER open, non-duplicate complaints at the exact same
    (category, location_area, location_address). Relies on the structured
    location slots gathered conversationally — without a specific-enough
    address, this can't distinguish two unrelated issues in the same area.
    location_pincode is deliberately NOT part of this key: it's explicitly
    allowed to be missing, so requiring it to match would silently break
    clustering for any pair where only one citizen supplied it.
    """
    if not complaint.location_address or complaint.location_address.strip().lower() == "not specified":
        return 0

    statement = select(Complaint).where(
        Complaint.category == complaint.category,
        Complaint.location_area == complaint.location_area,
        Complaint.location_address == complaint.location_address,
        Complaint.status != Status.resolved,
        Complaint.duplicate_of == None,  # noqa: E711
        Complaint.id != complaint.id,
    )
    return len(session.exec(statement).all())


def assign_tier(urgency: Optional[UrgencyLevel], reopened: bool, report_count: int) -> str:
    """Deterministic tier assignment — same precedence used consistently everywhere."""
    if urgency == UrgencyLevel.critical:
        return TIER_ACT_TODAY
    if reopened or report_count >= RECURRING_REPORT_THRESHOLD:
        return TIER_ESCALATE
    if urgency == UrgencyLevel.high:
        return TIER_THIS_WEEK
    if urgency == UrgencyLevel.medium:
        return TIER_WATCH
    return TIER_ROUTINE


def build_issue_facts(complaint: Complaint, session: Session) -> dict:
    """Assemble the fact record for one issue — the only input the LLM sees for its Why-line."""
    now = datetime.now(timezone.utc)
    days_open = max(0, (now - _aware(complaint.created_at)).days)
    report_count = complaint.report_count or 1
    reopened = complaint.reopened_from is not None
    cluster_size = compute_cluster_size(session, complaint)

    return {
        "tier": assign_tier(complaint.urgency_level, reopened, report_count),
        "days_open": days_open,
        "report_count": report_count,
        "reopened_after_resolution": reopened,
        "cluster_size": cluster_size,
        "location": _compose_location(complaint),
    }


def _compose_location(complaint: Complaint) -> str:
    """
    extracted_location is now the one polished, fully-combined location
    string (synthesized by the extraction stage from the citizen-confirmed
    location_address/location_area/location_pincode slots plus any extra
    free-text detail) — it IS the ground-truth-quality value here, not a
    distrusted LLM guess to be supplemented by a separate dropdown field, so
    it's used directly. Falls back to a raw concatenation of the structured
    slots if extraction failed for some reason (e.g. an LLM stage error).
    """
    detail = complaint.extracted_location
    if detail and detail.strip().lower() != "not specified":
        return detail

    parts = [p for p in (complaint.location_address, complaint.location_area) if p and p.strip().lower() != "not specified"]
    if parts:
        return ", ".join(parts)
    return "location not specified"
