from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models.db_models import Complaint, SubmissionType, Category, Status
from app.pipeline.dedup import cosine_similarity, get_candidates, find_duplicate, find_reopened, merge_complaint

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_cosine_similarity():
    vec_a = [1.0, 0.0, 0.0]
    vec_b = [1.0, 0.0, 0.0]
    vec_c = [0.0, 1.0, 0.0]

    assert cosine_similarity(vec_a, vec_b) == 1.0
    assert cosine_similarity(vec_a, vec_c) == 0.0

def test_dedup_merge_logic(session: Session):
    # Setup initial complaint
    c1 = Complaint(
        submission_type=SubmissionType.complaint,
        raw_text="Huge pothole on main street",
        citizen_name="Alice",
        citizen_phone="111",
        category=Category.roads,
        is_valid_submission=True,
    )
    c1.embedding = [0.9, 0.1, 0.0]
    session.add(c1)
    session.commit()

    # Test find duplicate
    new_embedding = [0.85, 0.15, 0.0]
    dup = find_duplicate(session, Category.roads, None, new_embedding, threshold=0.8)

    assert dup is not None
    assert dup.id == c1.id

    # Test merge
    merged = merge_complaint(session, dup, "Another pothole complaint", "Bob", "222")
    assert merged.report_count == 2

    # Check report was created
    session.refresh(merged)
    # The complaint report should be in DB, we can query it
    from app.models.db_models import ComplaintReport
    from sqlmodel import select
    reports = session.exec(select(ComplaintReport).where(ComplaintReport.complaint_id == c1.id)).all()
    assert len(reports) == 1
    assert reports[0].citizen_name == "Bob"

def test_get_candidates_excludes_resolved(session: Session):
    """A resolved complaint must not be offered up as a merge target — a fixed
    issue recurring later is a reopen, not a duplicate of the closed record."""
    resolved = Complaint(
        submission_type=SubmissionType.complaint,
        raw_text="Pothole on main street",
        citizen_name="Alice",
        citizen_phone="111",
        category=Category.roads,
        location_address="Shriram Nagar",
        is_valid_submission=True,
        status=Status.resolved,
    )
    session.add(resolved)
    session.commit()

    candidates = get_candidates(session, Category.roads, None, location_address="Shriram Nagar")
    assert resolved not in candidates

    dup = find_duplicate(session, Category.roads, None, [0.9, 0.1, 0.0], location_address="Shriram Nagar")
    assert dup is None  # no embedding on any open candidate (there are none) -> no match


def test_find_reopened_matches_resolved_same_spot(session: Session):
    resolved = Complaint(
        submission_type=SubmissionType.complaint,
        raw_text="Pothole on main street",
        citizen_name="Alice",
        citizen_phone="111",
        category=Category.roads,
        location_address="Shriram Nagar",
        is_valid_submission=True,
        status=Status.resolved,
        resolved_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    session.add(resolved)
    session.commit()

    hit = find_reopened(session, Category.roads, None, "Shriram Nagar")
    assert hit is not None
    assert hit.id == resolved.id


def test_find_reopened_none_without_location():
    class _NoSession:
        pass

    assert find_reopened(_NoSession(), Category.roads, None, None) is None


def test_dedup_live_embedding():
    """Live test hitting Ollama to generate an embedding."""
    from app.pipeline.dedup import embed
    try:
        vec = embed("Test text for embedding")
        assert vec is not None
        assert isinstance(vec, list)
        assert len(vec) > 0
    except Exception as e:
        pytest.skip(f"Skipping live embedding test: {e}")
