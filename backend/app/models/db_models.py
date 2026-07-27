import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel, Column
from pgvector.sqlalchemy import Vector
from enum import Enum

# nomic-embed-text produces 768-dimensional embeddings.
EMBEDDING_DIM = 768

class SubmissionType(str, Enum):
    complaint = "complaint"
    suggestion = "suggestion"

class Category(str, Enum):
    roads = "roads"
    water = "water"
    electricity = "electricity"
    sanitation = "sanitation"
    education = "education"
    healthcare = "healthcare"
    safety = "safety"
    other = "other"

class UrgencyLevel(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"

class Status(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"

class PipelineStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    failed = "failed"

class Leader(SQLModel, table=True):
    """
    Corporator-level leader record (FR8). Jurisdiction is city + free-text
    pincode, set at signup — no manual approval gate, no MLA/MP hierarchy.
    Real leader/jurisdiction data lands later; MVP ships against a small
    dummy set (~5 leaders x 5 cities, see db/seed.py). auth_user_id links to
    Supabase Auth once Phase 3 wires up leader login; nullable until then.
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    auth_user_id: Optional[uuid.UUID] = Field(default=None, index=True)
    name: str
    phone: str
    email: str
    city: str
    pincode: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Complaint(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    submission_type: SubmissionType

    raw_text: str
    language_detected: Optional[str] = "en"

    citizen_name: str
    citizen_last_name: Optional[str] = None
    citizen_phone: str

    # Structured location, gathered conversationally (colony/landmark, area,
    # pincode) rather than from a fixed dropdown. Ground truth for dedup/
    # clustering/routing — location_area + location_address is an exact-match
    # key precisely because the LLM's own paraphrased extraction can't be
    # trusted to match identically across independent submissions of the same
    # spot. location_pincode is stored for display only (not part of the
    # dedup key), since it's explicitly allowed to be "not specified".
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

    status: Status = Field(default=Status.open)
    pipeline_status: PipelineStatus = Field(default=PipelineStatus.done)
    is_valid_submission: Optional[bool] = None
    needs_human_review: Optional[bool] = None
    review_reason: Optional[str] = None
    # Comma-separated list of field names a citizen or leader has directly
    # corrected via the feedback loop (see api/complaints.py's
    # submit_extraction_feedback) — distinct from needs_human_review, which
    # means "an AI pipeline stage failed", not "a human already fixed this".
    human_corrected_fields: Optional[str] = None

    duplicate_of: Optional[uuid.UUID] = Field(default=None, foreign_key="complaint.id")
    report_count: int = Field(default=1)
    resolved_at: Optional[datetime] = None
    # Set when a new report matches a RESOLVED complaint at the same
    # (category, location_area, location_address) — i.e. the issue recurred
    # after being fixed. Kept as its own open complaint (not merged) so it
    # stays visible.
    reopened_from: Optional[uuid.UUID] = Field(default=None, foreign_key="complaint.id")

    # Real pgvector column (nomic-embed-text = 768 dims). No ANN index at
    # this scale — plain vector column, exact cosine search via `<=>`. See
    # MVP_Design.md §3.1 / MVP_roadmap.md Phase 1.
    embedding: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(EMBEDDING_DIM)))

    # Leader (FR9) this complaint is routed to, chosen by the citizen from
    # the city/pincode-filtered dropdown. Owner is the submitting citizen's
    # Supabase auth.uid(). Both nullable until Phase 3 wires up auth/FR9.
    concerned_leader_id: Optional[uuid.UUID] = Field(default=None, foreign_key="leader.id")
    owner_user_id: Optional[uuid.UUID] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ComplaintReport(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    complaint_id: uuid.UUID = Field(foreign_key="complaint.id")
    raw_text: str
    citizen_name: str
    citizen_phone: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExtractionFeedback(SQLModel, table=True):
    """
    Human thumbs-up/down on how the agent understood a submission — the
    "feedback as evolving ground truth" signal for evaluation. Captured from two
    sources:
      * source="citizen": right after the pipeline finishes (intake chat flow),
        an overall "did we understand you correctly?" (aspect="overall").
      * source="leader": occasionally, on the leader dashboard, a single rotating
        spot-check about one facet — aspect in {"labelling", "summary",
        "affected_and_ask"}.
    Capture only: rows accumulate here, ready to be sampled into a ground-truth
    set later. No auto-export pipeline is built on top of it yet (out of scope).
    """
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    complaint_id: uuid.UUID = Field(foreign_key="complaint.id")
    is_correct: bool
    correction: Optional[str] = None
    source: str = "citizen"          # "citizen" | "leader"
    aspect: Optional[str] = None     # citizen: "overall"; leader: which facet was checked
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PhoneRevealLog(SQLModel, table=True):
    """FR12 audit trail: every time a leader reveals a masked citizen phone
    number, who did it and when is recorded here — never deleted."""
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    complaint_id: uuid.UUID = Field(foreign_key="complaint.id")
    leader_id: uuid.UUID = Field(foreign_key="leader.id")
    revealed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
