from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
import uuid

from app.db.session import get_session
from app.models.schemas import ComplaintOut, ExtractionFeedbackIn
from app.models.db_models import Complaint, ExtractionFeedback, Leader, PhoneRevealLog, Status, Category, UrgencyLevel, SubmissionType
from app.auth.deps import get_current_leader, get_optional_current_leader, get_current_user, CurrentUser
from app.utils.validators import mask_phone

router = APIRouter(prefix="/complaints", tags=["Complaints"])

# Field-level correction allowlist for the feedback loop (submit_extraction_
# feedback below). Deliberately a fixed, explicit map — never setattr() on an
# arbitrary client-supplied field name — since this endpoint's citizen path
# is unauthenticated (matches GET /complaints/{id}'s existing "UUID is the
# bearer credential" trust model) and would otherwise let anyone holding a
# complaint's UUID overwrite any column on it. None as the value means
# free-text; an Enum class means the corrected value must be one of its
# members (validated, not just trusted).
_CORRECTABLE_FIELDS: Dict[str, Optional[type]] = {
    "category": Category,
    "urgency_level": UrgencyLevel,
    "location_area": None,
    "location_address": None,
    "extracted_issue_summary": None,
    "extracted_affected_parties": None,
    "extracted_ask": None,
}
_MAX_CORRECTION_LEN = 300


def _apply_corrections(complaint: Complaint, corrections: Dict[str, str]) -> List[str]:
    """Validates and applies a {field: corrected_value} map to `complaint` in
    place. Raises HTTPException(400) on an unknown field or an invalid enum
    value rather than silently skipping it — a rejected correction should be
    visible to whoever submitted it, not swallowed. Returns the field names
    actually applied, for the human_corrected_fields audit trail."""
    applied = []
    for field, raw_value in corrections.items():
        if field not in _CORRECTABLE_FIELDS:
            raise HTTPException(status_code=400, detail=f"'{field}' cannot be corrected via feedback")
        enum_cls = _CORRECTABLE_FIELDS[field]
        value = (raw_value or "").strip()
        if not value:
            continue  # an empty correction for this field is a no-op, not an error
        if enum_cls is not None:
            try:
                parsed = enum_cls(value.lower())
            except ValueError:
                valid = ", ".join(m.value for m in enum_cls)
                raise HTTPException(status_code=400, detail=f"'{field}' must be one of: {valid}")
            setattr(complaint, field, parsed)
        else:
            setattr(complaint, field, value[:_MAX_CORRECTION_LEN])
        applied.append(field)
    return applied


def _masked(complaint: Complaint) -> ComplaintOut:
    out = ComplaintOut.model_validate(complaint)
    return out.model_copy(update={"citizen_phone": mask_phone(complaint.citizen_phone)})

# Same cutoff convention as /stats/trends and /stats/summary-report, so a
# citizen-facing time_range value means the identical window everywhere.
_TIME_RANGE_DAYS = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "6mo": 182, "1y": 365}


@router.get("", response_model=List[ComplaintOut])
def get_complaints(
    session: Session = Depends(get_session),
    leader: Leader = Depends(get_current_leader),
    q: Optional[str] = None,
    category: Optional[Category] = None,
    urgency: Optional[UrgencyLevel] = None,
    status: Optional[Status] = None,
    area: Optional[str] = None,
    time_range: Optional[str] = Query(None, description="24h | 7d | 15d | 30d | 6mo | 1y"),
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None
):
    statement = select(Complaint).where(
        Complaint.submission_type == SubmissionType.complaint,
        # is_valid_submission is None while still pending/processing (must stay visible with a spinner)
        # and False once the gatekeeper rejects it (spam/abuse/vague/etc — must stay OFF the leader dashboard).
        Complaint.is_valid_submission.is_not(False),
        # FR9/FR10 — a leader only ever sees complaints routed to their own jurisdiction.
        Complaint.concerned_leader_id == leader.id,
    )

    if q:
        statement = statement.where(Complaint.raw_text.contains(q))
    if category:
        statement = statement.where(Complaint.category == category)
    if urgency:
        statement = statement.where(Complaint.urgency_level == urgency)
    if status:
        statement = statement.where(Complaint.status == status)
    if area:
        statement = statement.where(Complaint.location_area == area)
    days = _TIME_RANGE_DAYS.get(time_range)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        statement = statement.where(Complaint.created_at >= cutoff)
    if date_from:
        statement = statement.where(Complaint.created_at >= date_from)
    if date_to:
        statement = statement.where(Complaint.created_at <= date_to)

    return [_masked(c) for c in session.exec(statement).all()]


@router.get("/mine", response_model=List[ComplaintOut])
def get_my_complaints(
    session: Session = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    FR6 — a citizen's own submissions (complaints AND suggestions), scoped by
    the verified `owner_user_id` from their session, not a client-supplied
    value. Closes the standing gap noted since Phase 3: `owner_user_id` was
    recorded on every submission from day one, but no endpoint ever read it
    back — the frontend instead relied on a per-browser localStorage tracker
    (still present, unaffected), which loses a citizen's history on a new
    device or a cleared browser. Unmasked (it's the citizen's own phone
    number), same as the existing single-id lookup below.
    """
    statement = (
        select(Complaint)
        .where(Complaint.owner_user_id == current_user.id)
        .order_by(Complaint.created_at.desc())
    )
    return session.exec(statement).all()


@router.get("/{id}", response_model=ComplaintOut)
def get_complaint(id: uuid.UUID, session: Session = Depends(get_session)):
    """
    Citizen's own submission-status lookup (FR6) — deliberately not
    leader-gated: a citizen tracks their own complaint by id alone (no
    account-wide list endpoint exists), and the phone shown is their own, so
    no masking applies here either.
    """
    complaint = session.get(Complaint, id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.patch("/{id}/status", response_model=ComplaintOut)
def update_status(
    id: uuid.UUID, status: Status,
    session: Session = Depends(get_session),
    leader: Leader = Depends(get_current_leader),
):
    complaint = session.get(Complaint, id)
    if not complaint or complaint.concerned_leader_id != leader.id:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = status
    complaint.resolved_at = datetime.now(timezone.utc) if status == Status.resolved else None
    complaint.updated_at = datetime.now(timezone.utc)
    session.add(complaint)
    session.commit()
    session.refresh(complaint)
    return _masked(complaint)


@router.post("/{id}/reveal-phone")
def reveal_phone(
    id: uuid.UUID,
    session: Session = Depends(get_session),
    leader: Leader = Depends(get_current_leader),
):
    """FR12: unmasks a citizen's phone number for this one complaint, logging
    who revealed it and when — never a bulk/unaudited unmask."""
    complaint = session.get(Complaint, id)
    if not complaint or complaint.concerned_leader_id != leader.id:
        raise HTTPException(status_code=404, detail="Complaint not found")

    session.add(PhoneRevealLog(complaint_id=id, leader_id=leader.id))
    session.commit()
    return {"phone": complaint.citizen_phone}


@router.post("/{id}/feedback", status_code=201)
def submit_extraction_feedback(
    id: uuid.UUID, feedback: ExtractionFeedbackIn, session: Session = Depends(get_session),
    leader: Optional[Leader] = Depends(get_optional_current_leader),
):
    """
    Capture the citizen's or leader's 'did the agent understand me correctly?'
    answer, AND — this is the part that previously didn't exist — actually
    apply any structured `corrections` to the live Complaint row. The
    ExtractionFeedback row is still written unconditionally (eval Layer 2's
    "evolving ground truth" use case is unchanged), but a correction no
    longer dead-ends as unread prose in a separate table: the record itself
    gets fixed, so the leader dashboard reflects the human-verified value on
    the very next read, not just some future eval export.

    Authorization: the citizen path is intentionally unauthenticated, matching
    GET /complaints/{id}'s existing "the UUID is the bearer credential"
    model — a citizen can already read and is now trusted to correct their
    own submission. A leader-sourced correction (source="leader") is
    different: it claims the authority of an official review, so it MUST
    come from a real, currently-logged-in leader who owns this complaint —
    spoofing source="leader" from an anonymous request is rejected outright,
    since corrections now have a real effect, not just an eval-log entry.
    """
    complaint = session.get(Complaint, id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    source = feedback.source or "citizen"
    if source == "leader":
        if leader is None or complaint.concerned_leader_id != leader.id:
            raise HTTPException(status_code=403, detail="Leader-sourced feedback requires a matching leader session")

    row = ExtractionFeedback(
        complaint_id=id,
        is_correct=feedback.is_correct,
        correction=(feedback.correction or None),
        source=source,
        aspect=feedback.aspect or ("overall" if source == "citizen" else None),
    )
    session.add(row)

    applied_fields: List[str] = []
    if not feedback.is_correct and feedback.corrections:
        applied_fields = _apply_corrections(complaint, feedback.corrections)
        if applied_fields:
            existing = {f for f in (complaint.human_corrected_fields or "").split(",") if f}
            complaint.human_corrected_fields = ",".join(sorted(existing | set(applied_fields)))
            complaint.updated_at = datetime.now(timezone.utc)
            session.add(complaint)

    session.commit()
    return {"ok": True, "feedback_id": str(row.id), "corrected_fields": applied_fields}
