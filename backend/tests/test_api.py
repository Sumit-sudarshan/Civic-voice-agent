import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
import uuid

from app.main import app
from app.db.session import get_session
from app.auth.deps import get_current_user, get_current_leader, CurrentUser
from app.models.db_models import Complaint, Leader, SubmissionType, Category, UrgencyLevel, Status, PipelineStatus

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

def get_current_user_override():
    return CurrentUser(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        email="test-citizen@example.com", role="citizen",
        first_name="Test", last_name="User", name=None, phone="123",
    )

TEST_LEADER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000ff")

def get_current_leader_override():
    return Leader(
        id=TEST_LEADER_ID,
        auth_user_id=uuid.UUID("00000000-0000-0000-0000-0000000000fe"),
        name="Test Leader", phone="9876500000", email="leader@example.com",
        city="Pune", pincode="411001",
    )

app.dependency_overrides[get_session] = get_session_override
app.dependency_overrides[get_current_user] = get_current_user_override
app.dependency_overrides[get_current_leader] = get_current_leader_override
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

    def mock_process_turn(payload, session, background_tasks=None, owner_user_id=None):
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
        "citizen_phone": "9876543210",
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
            citizen_phone="9876543210",
            category=Category.roads,
            status=Status.open,
            concerned_leader_id=TEST_LEADER_ID,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        c_id = str(c.id)

    # Citizen-facing lookup (FR6) — unauthenticated, unmasked, own phone.
    response2 = client.get(f"/complaints/{c_id}")
    assert response2.status_code == 200
    assert response2.json()["id"] == c_id
    assert response2.json()["citizen_phone"] == "9876543210"

    # Leader-scoped status change (FR11) — gated on jurisdiction ownership.
    response3 = client.patch(f"/complaints/{c_id}/status?status=in_progress")
    assert response3.status_code == 200
    assert response3.json()["status"] == "in_progress"


def test_patch_status_blocked_for_other_leaders_complaint():
    """A leader cannot change the status of a complaint outside their jurisdiction."""
    with Session(engine) as session:
        c = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Different leader's issue",
            citizen_name="Other Citizen",
            citizen_phone="9876500001",
            category=Category.water,
            status=Status.open,
            concerned_leader_id=uuid.uuid4(),  # some other leader
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        c_id = str(c.id)

    response = client.patch(f"/complaints/{c_id}/status?status=in_progress")
    assert response.status_code == 404


def test_complaints_list_masks_phone_and_scopes_to_leader():
    with Session(engine) as session:
        mine = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="My jurisdiction's issue",
            citizen_name="Citizen A",
            citizen_phone="9876543210",
            category=Category.roads,
            status=Status.open,
            is_valid_submission=True,
            concerned_leader_id=TEST_LEADER_ID,
        )
        someone_elses = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Another leader's issue",
            citizen_name="Citizen B",
            citizen_phone="9123456789",
            category=Category.roads,
            status=Status.open,
            is_valid_submission=True,
            concerned_leader_id=uuid.uuid4(),
        )
        session.add(mine)
        session.add(someone_elses)
        session.commit()

    response = client.get("/complaints")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["citizen_phone"] == "98******10"


def test_reveal_phone_logs_and_returns_real_number():
    with Session(engine) as session:
        c = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Needs a phone reveal",
            citizen_name="Citizen C",
            citizen_phone="9988776655",
            category=Category.roads,
            status=Status.open,
            concerned_leader_id=TEST_LEADER_ID,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        c_id = str(c.id)

    response = client.post(f"/complaints/{c_id}/reveal-phone")
    assert response.status_code == 200
    assert response.json()["phone"] == "9988776655"

    from app.models.db_models import PhoneRevealLog
    with Session(engine) as session:
        logs = session.exec(select(PhoneRevealLog).where(PhoneRevealLog.complaint_id == uuid.UUID(c_id))).all()
        assert len(logs) == 1
        assert logs[0].leader_id == TEST_LEADER_ID


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
            concerned_leader_id=TEST_LEADER_ID,
        )
        s1 = Complaint(
            submission_type=SubmissionType.suggestion,
            raw_text="Test",
            citizen_name="Alice",
            citizen_phone="2",
            category=Category.other,
            status=Status.open,
            concerned_leader_id=TEST_LEADER_ID,
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
