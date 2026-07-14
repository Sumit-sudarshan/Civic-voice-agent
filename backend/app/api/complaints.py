from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional
from datetime import datetime, timedelta, timezone
import uuid

from app.db.session import get_session
from app.models.schemas import ComplaintOut, ExtractionFeedbackIn
from app.models.db_models import Complaint, ExtractionFeedback, Status, Category, UrgencyLevel, SubmissionType

router = APIRouter(prefix="/complaints", tags=["Complaints"])

# Same cutoff convention as /stats/trends and /stats/summary-report, so a
# citizen-facing time_range value means the identical window everywhere.
_TIME_RANGE_DAYS = {"24h": 1, "7d": 7, "15d": 15, "30d": 30, "6mo": 182, "1y": 365}


@router.get("", response_model=List[ComplaintOut])
def get_complaints(
    session: Session = Depends(get_session),
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

    return session.exec(statement).all()


@router.get("/{id}", response_model=ComplaintOut)
def get_complaint(id: uuid.UUID, session: Session = Depends(get_session)):
    complaint = session.get(Complaint, id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


@router.patch("/{id}/status", response_model=ComplaintOut)
def update_status(id: uuid.UUID, status: Status, session: Session = Depends(get_session)):
    complaint = session.get(Complaint, id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    complaint.status = status
    complaint.resolved_at = datetime.now(timezone.utc) if status == Status.resolved else None
    complaint.updated_at = datetime.now(timezone.utc)
    session.add(complaint)
    session.commit()
    session.refresh(complaint)
    return complaint


@router.post("/{id}/feedback", status_code=201)
def submit_extraction_feedback(
    id: uuid.UUID, feedback: ExtractionFeedbackIn, session: Session = Depends(get_session)
):
    """
    Capture the citizen's 'did the agent understand me correctly?' answer once
    the pipeline has finished analysing their submission (eval Layer 2 — feedback
    as evolving ground truth). Capture only: the row is stored, not yet exported
    anywhere.
    """
    complaint = session.get(Complaint, id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")

    row = ExtractionFeedback(
        complaint_id=id,
        is_correct=feedback.is_correct,
        correction=(feedback.correction or None),
        source=feedback.source or "citizen",
        aspect=feedback.aspect or ("overall" if (feedback.source or "citizen") == "citizen" else None),
    )
    session.add(row)
    session.commit()
    return {"ok": True, "feedback_id": str(row.id)}
