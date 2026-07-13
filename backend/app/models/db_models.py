import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel
from enum import Enum

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

    duplicate_of: Optional[uuid.UUID] = Field(default=None, foreign_key="complaint.id")
    report_count: int = Field(default=1)
    resolved_at: Optional[datetime] = None
    # Set when a new report matches a RESOLVED complaint at the same
    # (category, location_area, location_address) — i.e. the issue recurred
    # after being fixed. Kept as its own open complaint (not merged) so it
    # stays visible.
    reopened_from: Optional[uuid.UUID] = Field(default=None, foreign_key="complaint.id")

    # SQLite doesn't natively support vectors/arrays. We store embeddings as JSON strings.
    embedding_json: Optional[str] = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def embedding(self) -> Optional[List[float]]:
        if self.embedding_json:
            return json.loads(self.embedding_json)
        return None

    @embedding.setter
    def embedding(self, value: Optional[List[float]]):
        if value is not None:
            self.embedding_json = json.dumps(value)
        else:
            self.embedding_json = None

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
