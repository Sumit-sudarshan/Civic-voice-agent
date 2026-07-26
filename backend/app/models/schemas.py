from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Literal
import uuid
from datetime import datetime
from .db_models import SubmissionType, Category, UrgencyLevel, Status, PipelineStatus
from app.utils.validators import validate_phone

class ExtractionFeedbackIn(BaseModel):
    """Human 'did the agent get this right?' answer. Posted by the citizen after
    the pipeline finishes (source defaults to 'citizen', aspect 'overall'), or by
    the leader as an occasional facet spot-check (source='leader', aspect one of
    'labelling'/'summary'/'affected_and_ask'). correction is optional free text."""
    is_correct: bool
    correction: Optional[str] = None
    source: str = "citizen"
    aspect: Optional[str] = None


class ComplaintOut(BaseModel):
    id: uuid.UUID
    submission_type: SubmissionType
    raw_text: str
    language_detected: Optional[str] = None
    citizen_name: str
    citizen_last_name: Optional[str] = None
    citizen_phone: str

    location_address: Optional[str] = None
    location_area: Optional[str] = None
    location_pincode: Optional[str] = None

    category: Optional[Category] = None
    urgency_level: Optional[UrgencyLevel] = None
    urgency_reasoning: Optional[str] = None
    extracted_location: Optional[str] = None
    extracted_issue_summary: Optional[str] = None
    extracted_affected_parties: Optional[str] = None
    extracted_ask: Optional[str] = None

    status: Status
    pipeline_status: PipelineStatus = PipelineStatus.done
    is_valid_submission: Optional[bool] = None
    needs_human_review: Optional[bool] = None
    review_reason: Optional[str] = None

    duplicate_of: Optional[uuid.UUID] = None
    report_count: int
    resolved_at: Optional[datetime] = None
    reopened_from: Optional[uuid.UUID] = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ComplaintInternal(ComplaintOut):
    embedding: Optional[List[float]] = None


# ---------------------------------------------------------------------------
# Conversational intake — the chat replaces the old structured ComplaintCreate
# form. The backend is stateless: the frontend resends the running turn
# history (already English-normalized from prior responses) plus the newest
# citizen message on every call.
# ---------------------------------------------------------------------------

class ChatTurnRecord(BaseModel):
    speaker: Literal["citizen", "bot"]
    english_text: str
    # Only set for bot turns — lets the backend count how many times a given
    # question has already been asked, without server-side session state.
    question_key: Optional[str] = None

class ChatMessageRequest(BaseModel):
    new_message: str
    history: List[ChatTurnRecord] = Field(default_factory=list)
    # Set once from turn 1's gatekeeper outcome and resent unchanged thereafter
    # (None while a too_vague_to_process opening message still has the
    # complaint-vs-suggestion question deferred). This is the one small piece
    # of client-held state that lets gatekeeper's relatively expensive 7-way
    # call run once per conversation instead of every turn.
    submission_type_hint: Optional[Literal["complaint", "suggestion"]] = None
    citizen_first_name: str
    citizen_last_name: Optional[str] = None
    citizen_phone: str
    # FR9 — citizen-picked corporator from the city/pincode-filtered dropdown.
    # Editable per conversation, so resent (possibly changed) every turn;
    # whatever it is on the turn that actually creates the Complaint row wins.
    concerned_leader_id: Optional[uuid.UUID] = None

    _validate_phone = field_validator("citizen_phone")(validate_phone)

class LocationSlotsOut(BaseModel):
    address: Optional[str] = None
    area: Optional[str] = None
    pincode: Optional[str] = None

class ChatTurnResponse(BaseModel):
    kind: Literal["rejected", "question", "submitted", "rate_limited"]
    detected_language: str
    # English-normalized version of the citizen's just-submitted message —
    # the frontend stores THIS (not the original-language text) as this
    # turn's `english_text` when appending to history for the next call, so
    # the transcript the backend builds stays English throughout regardless
    # of what language the citizen actually typed in.
    new_message_english: str

    # kind == "rejected"
    rejection_reason: Optional[str] = None

    # kind == "rate_limited"
    rate_limit_message: Optional[str] = None

    # kind == "question"
    question_key: Optional[str] = None
    question_text: Optional[str] = None            # localized, ready to display
    question_text_english: Optional[str] = None     # for the frontend to store & replay in history
    slots_so_far: Optional[LocationSlotsOut] = None  # display-only

    # kind == "submitted"
    submission_type: Optional[Literal["complaint", "suggestion"]] = None
    complaint_id: Optional[uuid.UUID] = None
    pipeline_status: Optional[str] = None
    confirmation_text: Optional[str] = None

    # carried through unchanged so the frontend can resend it on the next turn
    submission_type_hint: Optional[Literal["complaint", "suggestion"]] = None
