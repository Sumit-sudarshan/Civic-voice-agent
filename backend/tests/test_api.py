import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool
import uuid

from app.main import app
from app.db.session import get_session
from app.models.db_models import Complaint, SubmissionType, Category, UrgencyLevel, Status, PipelineStatus

# Create a test database. StaticPool keeps a single shared connection alive
# across threads — FastAPI's TestClient dispatches sync endpoints via a
# worker threadpool, and plain ":memory:" SQLite gives each thread its own
# independent (and therefore empty) database without this.
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

def get_session_override():
    with Session(engine) as session:
        yield session

app.dependency_overrides[get_session] = get_session_override
client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)

def test_settings_categories():
    response = client.get("/settings/categories")
    assert response.status_code == 200
    assert "roads" in response.json()

def test_intake_message_submitted(monkeypatch):
    """
    Verifies the /intake/message route wires correctly to process_turn.
    The dialogue/gatekeeper logic itself is unit-tested directly against
    process_turn in test_orchestrator.py/test_gatekeeper.py — here we're only
    confirming the API layer passes the request through and shapes the
    response correctly.
    """
    from app.models.schemas import ChatTurnResponse

    fake_id = uuid.uuid4()

    def mock_process_turn(payload, session, background_tasks=None):
        return ChatTurnResponse(
            kind="submitted",
            detected_language="en",
            new_message_english="Huge pothole on MG Road",
            submission_type="complaint",
            complaint_id=fake_id,
            pipeline_status="pending",
            confirmation_text="Thanks — your complaint has been submitted.",
        )

    monkeypatch.setattr("app.api.intake.process_turn", mock_process_turn)

    response = client.post("/intake/message", json={
        "new_message": "Huge pothole on MG Road",
        "history": [],
        "citizen_first_name": "Test User",
        "citizen_phone": "123",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["kind"] == "submitted"
    assert data["complaint_id"] == str(fake_id)

def test_get_and_patch_complaint():
    with Session(engine) as session:
        c = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Pothole here",
            citizen_name="Test User",
            citizen_phone="123",
            category=Category.roads,
            status=Status.open,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        c_id = str(c.id)

    response2 = client.get(f"/complaints/{c_id}")
    assert response2.status_code == 200
    assert response2.json()["id"] == c_id

    response3 = client.patch(f"/complaints/{c_id}/status?status=in_progress")
    assert response3.status_code == 200
    assert response3.json()["status"] == "in_progress"

def test_stats_summary():
    with Session(engine) as session:
        c1 = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Test",
            citizen_name="Bob",
            citizen_phone="1",
            category=Category.roads,
            status=Status.open,
            urgency_level=UrgencyLevel.critical,
            pipeline_status=PipelineStatus.done,
            is_valid_submission=True,
        )
        s1 = Complaint(
            submission_type=SubmissionType.suggestion,
            raw_text="Test",
            citizen_name="Alice",
            citizen_phone="2",
            category=Category.other,
            status=Status.open,
        )
        session.add(c1)
        session.add(s1)
        session.commit()

    response = client.get("/stats/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_issues"] == 1
    assert data["suggestions"] == 1
    assert data["critical"] == 1
    assert data["open"] == 1
