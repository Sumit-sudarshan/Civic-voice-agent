import time
import logging
import ollama
import numpy as np
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.config import settings
from app.models.db_models import Complaint, Category, ComplaintReport, Status

logger = logging.getLogger(__name__)

# Embeddings run on local Ollama by design — the PII-bearing complaint text
# these vectors are derived from never leaves the VM. See MVP_Design.md §3.1.
# Part of the async finalize pipeline (never the sync conversational loop),
# so it gets that budget: ~20s timeout, 3 retries. See NFR7/NFR8.
client = ollama.Client(host=settings.OLLAMA_HOST, timeout=settings.ASYNC_LLM_TIMEOUT_S)

def embed(text: str) -> List[float]:
    """
    Generate embeddings for text using the local Ollama embedding model.
    Retries on failure (bounded, with backoff) before giving up — the caller
    (finalize_submission) degrades gracefully to embedding=None (dedup
    skipped, submission still saved) only once every attempt here fails.
    """
    total_attempts = settings.ASYNC_LLM_RETRIES + 1
    for attempt in range(total_attempts):
        try:
            response = client.embeddings(model=settings.EMBEDDING_MODEL, prompt=text)
            return response["embedding"]
        except Exception as e:
            is_last_attempt = attempt == total_attempts - 1
            logger.warning(f"Embedding call error on attempt {attempt + 1}/{total_attempts}: {e}")
            if is_last_attempt:
                raise
            if attempt < len(settings.ASYNC_LLM_BACKOFF_S):
                time.sleep(settings.ASYNC_LLM_BACKOFF_S[attempt])

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(vec_a)
    b = np.array(vec_b)
    if np.linalg.norm(a) == 0 or np.linalg.norm(b) == 0:
        return 0.0
    return np.dot(a, b).item() / (np.linalg.norm(a) * np.linalg.norm(b))

def _prefilter_conditions(
    category: Category,
    location_area: Optional[str],
    location_address: Optional[str],
    days: int,
):
    """
    Shared structural prefilter for dedup candidates: same category and area,
    recent, valid, still open. Excludes resolved complaints — a fixed issue is
    not a valid merge target; a new report at that spot is a recurrence,
    handled separately by find_reopened(). When a structured `location_address`
    is available, narrow to an exact match first — it's a citizen-confirmed
    exact field, so it's a much tighter and more reliable filter than leaving
    the whole area to embedding similarity.
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    conditions = [
        Complaint.category == category,
        Complaint.location_area == location_area,
        Complaint.created_at >= cutoff_date,
        Complaint.is_valid_submission == True,
        Complaint.status != Status.resolved,
    ]
    if location_address:
        conditions.append(Complaint.location_address == location_address)
    return conditions

def get_candidates(
    session: Session,
    category: Category,
    location_area: Optional[str],
    location_address: Optional[str] = None,
    days: int = 14,
) -> List[Complaint]:
    """Retrieve recent, still-open complaints of the same category and area."""
    conditions = _prefilter_conditions(category, location_area, location_address, days)
    statement = select(Complaint).where(*conditions)
    return session.exec(statement).all()

def find_duplicate(
    session: Session,
    category: Category,
    location_area: Optional[str],
    text_embedding: List[float],
    location_address: Optional[str] = None,
    threshold: float = 0.85,
    days: int = 14,
) -> Optional[Complaint]:
    """
    Find an existing open duplicate complaint using pgvector cosine distance,
    ranked in SQL (ORDER BY embedding <=> query LIMIT 1) instead of pulling
    candidates into Python and looping. Same prefilter as get_candidates();
    threshold is a similarity (0.85 default = 0.15 cosine distance).
    """
    conditions = _prefilter_conditions(category, location_area, location_address, days)
    distance = Complaint.embedding.cosine_distance(text_embedding)
    statement = (
        select(Complaint)
        .where(*conditions, Complaint.embedding.is_not(None), distance <= (1 - threshold))
        .order_by(distance)
        .limit(1)
    )
    return session.exec(statement).first()

def find_reopened(
    session: Session,
    category: Category,
    location_area: Optional[str],
    location_address: Optional[str],
    days: int = 90,
) -> Optional[Complaint]:
    """
    Check whether this exact (category, location_area, location_address) spot
    was already marked resolved recently. Structural match only (no embedding
    needed) — the citizen-confirmed structured location is exact, so
    recurrence at the same spot is a reliable signal on its own regardless of
    how the new report is worded. Returns the most recently resolved
    complaint at that spot, if any.
    """
    if not location_address:
        return None

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    statement = (
        select(Complaint)
        .where(
            Complaint.category == category,
            Complaint.location_area == location_area,
            Complaint.location_address == location_address,
            Complaint.status == Status.resolved,
            Complaint.resolved_at != None,  # noqa: E711
            Complaint.resolved_at >= cutoff_date,
        )
        .order_by(Complaint.resolved_at.desc())
    )
    return session.exec(statement).first()

def merge_complaint(session: Session, existing_complaint: Complaint, raw_text: str, citizen_name: str, citizen_phone: str) -> Complaint:
    """Merge a new report into an existing complaint."""
    existing_complaint.report_count += 1
    existing_complaint.updated_at = datetime.now(timezone.utc)

    report = ComplaintReport(
        complaint_id=existing_complaint.id,
        raw_text=raw_text,
        citizen_name=citizen_name,
        citizen_phone=citizen_phone
    )

    session.add(existing_complaint)
    session.add(report)
    session.commit()
    session.refresh(existing_complaint)

    return existing_complaint
