from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Optional
import uuid

from app.db.session import get_session
from app.models.schemas import ComplaintOut
from app.models.db_models import Complaint, Leader, SubmissionType, Category, Status
from app.auth.deps import get_current_leader
from app.utils.validators import mask_phone

router = APIRouter(prefix="/suggestions", tags=["Suggestions"])


@router.get("", response_model=List[ComplaintOut])
def get_suggestions(
    session: Session = Depends(get_session),
    leader: Leader = Depends(get_current_leader),
    category: Optional[Category] = None,
    status: Optional[Status] = None,
    area: Optional[str] = None,
):
    statement = select(Complaint).where(
        Complaint.submission_type == SubmissionType.suggestion,
        Complaint.concerned_leader_id == leader.id,
    )

    if category:
        statement = statement.where(Complaint.category == category)
    if status:
        statement = statement.where(Complaint.status == status)
    if area:
        statement = statement.where(Complaint.location_area == area)

    results = session.exec(statement).all()
    return [
        ComplaintOut.model_validate(c).model_copy(update={"citizen_phone": mask_phone(c.citizen_phone)})
        for c in results
    ]


@router.get("/{id}", response_model=ComplaintOut)
def get_suggestion(id: uuid.UUID, session: Session = Depends(get_session)):
    suggestion = session.get(Complaint, id)
    if not suggestion or suggestion.submission_type != SubmissionType.suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return suggestion


@router.patch("/{id}/status", response_model=ComplaintOut)
def update_suggestion_status(id: uuid.UUID, status: Status, session: Session = Depends(get_session)):
    suggestion = session.get(Complaint, id)
    if not suggestion or suggestion.submission_type != SubmissionType.suggestion:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    suggestion.status = status
    session.add(suggestion)
    session.commit()
    session.refresh(suggestion)
    return suggestion
