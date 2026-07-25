import pytest
from sqlmodel import Session, select
from app.db.session import engine, create_db_and_tables
from app.models.db_models import Complaint, ComplaintReport, SubmissionType, Category, EMBEDDING_DIM


def _vec(*head: float) -> list[float]:
    """768-dim vector (pgvector enforces exact dimension) with the given
    leading values and zeros elsewhere — trailing zeros are shared by both
    sides of any comparison in these tests, so they don't affect cosine sim."""
    return list(head) + [0.0] * (EMBEDDING_DIM - len(head))


@pytest.fixture(name="session")
def session_fixture():
    """
    Runs against the real Supabase Postgres (no local DB in this design —
    see MVP_Design.md §3.1) since dedup queries now use real pgvector
    operators that SQLite can't execute. Cleans up any rows the test created
    so seed/demo data is never touched.
    """
    create_db_and_tables()
    with Session(engine) as session:
        before_ids = set(session.exec(select(Complaint.id)).all())
        yield session
        session.rollback()
        # Two passes: no relationship() is defined between Complaint and
        # ComplaintReport, so the ORM won't auto-order the deletes — flush
        # child-row deletes before deleting the parent to satisfy the FK.
        new_complaints = [c for c in session.exec(select(Complaint)).all() if c.id not in before_ids]
        for c in new_complaints:
            for r in session.exec(select(ComplaintReport).where(ComplaintReport.complaint_id == c.id)).all():
                session.delete(r)
        session.flush()
        for c in new_complaints:
            session.delete(c)
        session.commit()


def test_create_and_read_complaint(session: Session):
    complaint = Complaint(
        submission_type=SubmissionType.complaint,
        raw_text="Pothole on MG Road",
        citizen_name="Test User",
        citizen_phone="0000000000",
        category=Category.roads,
    )
    complaint.embedding = _vec(0.1, 0.2, 0.3)

    session.add(complaint)
    session.commit()
    session.refresh(complaint)

    assert complaint.id is not None
    assert complaint.raw_text == "Pothole on MG Road"
    assert complaint.embedding == _vec(0.1, 0.2, 0.3)
