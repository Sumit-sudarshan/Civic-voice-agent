import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models.db_models import Complaint, SubmissionType, Category

@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session

def test_create_and_read_complaint(session: Session):
    complaint = Complaint(
        submission_type=SubmissionType.complaint,
        raw_text="Pothole on MG Road",
        citizen_name="Test User",
        citizen_phone="0000000000",
        category=Category.roads
    )
    # Test embedding setter logic
    complaint.embedding = [0.1, 0.2, 0.3]
    
    session.add(complaint)
    session.commit()
    session.refresh(complaint)
    
    assert complaint.id is not None
    assert complaint.raw_text == "Pothole on MG Road"
    assert complaint.embedding == [0.1, 0.2, 0.3]
    assert complaint.embedding_json == "[0.1, 0.2, 0.3]"
