"""
Tests for the feedback loop actually writing back to the record (real gap:
previously `correction` was free-text prose no code ever read — a citizen
who wrote "the location is actually Sector 7, not Sector 4" had, in effect,
corrected nothing; see api/complaints.py's submit_extraction_feedback).

Two layers are covered:
  1. `_apply_corrections` — the pure field-application logic: allowlisted
     fields only, enum values validated, unknown fields/values rejected
     loudly (never silently skipped), empty values are a no-op.
  2. The full HTTP endpoint — citizen corrections apply unauthenticated
     (matching GET /complaints/{id}'s existing "the UUID is the bearer
     credential" trust model), while a leader-sourced correction requires a
     REAL, matching leader session — spoofing source="leader" from an
     anonymous request must be rejected, since corrections now mutate the
     live record instead of just logging a note.
"""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_session
from app.auth.deps import get_optional_current_leader
from app.models.db_models import Complaint, Leader, SubmissionType, Category, UrgencyLevel, Status, PipelineStatus
from app.api.complaints import _apply_corrections


# ── 1. _apply_corrections — pure logic, no HTTP ─────────────────────────────

def _make_complaint(**overrides):
    defaults = dict(
        submission_type=SubmissionType.complaint,
        raw_text="Garbage pile near the market",
        citizen_name="Test", citizen_phone="9876543210",
        category=Category.roads, urgency_level=UrgencyLevel.low,
        location_area="Old Area", extracted_issue_summary="old summary",
        status=Status.open, pipeline_status=PipelineStatus.done,
    )
    defaults.update(overrides)
    return Complaint(**defaults)


def test_valid_category_correction_is_applied():
    c = _make_complaint()
    applied = _apply_corrections(c, {"category": "sanitation"})
    assert c.category == Category.sanitation
    assert applied == ["category"]


def test_invalid_category_value_is_rejected():
    c = _make_complaint()
    with pytest.raises(HTTPException) as exc_info:
        _apply_corrections(c, {"category": "spaceship"})
    assert exc_info.value.status_code == 400
    assert c.category == Category.roads, "an invalid value must not partially apply"


def test_unknown_field_is_rejected_not_silently_ignored():
    c = _make_complaint()
    with pytest.raises(HTTPException) as exc_info:
        _apply_corrections(c, {"citizen_phone": "0000000000"})
    assert exc_info.value.status_code == 400
    assert c.citizen_phone == "9876543210", "an off-allowlist field must never be mutated"


def test_free_text_field_is_applied_and_trimmed():
    c = _make_complaint()
    applied = _apply_corrections(c, {"location_area": "  Cotton Green  "})
    assert c.location_area == "Cotton Green"
    assert applied == ["location_area"]


def test_empty_value_is_a_no_op_not_an_error():
    c = _make_complaint()
    applied = _apply_corrections(c, {"location_area": "   "})
    assert applied == []
    assert c.location_area == "Old Area", "an empty correction must not clobber the existing value"


def test_multiple_fields_applied_in_one_call():
    c = _make_complaint()
    applied = _apply_corrections(c, {"extracted_issue_summary": "new summary", "urgency_level": "critical"})
    assert c.extracted_issue_summary == "new summary"
    assert c.urgency_level == UrgencyLevel.critical
    assert set(applied) == {"extracted_issue_summary", "urgency_level"}


def test_correction_length_is_capped():
    c = _make_complaint()
    _apply_corrections(c, {"extracted_ask": "x" * 1000})
    assert len(c.extracted_ask) == 300


# ── 2. Full HTTP endpoint ────────────────────────────────────────────────────

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

TEST_LEADER_ID = uuid.uuid4()
OTHER_LEADER_ID = uuid.uuid4()


def _session_override():
    with Session(engine) as session:
        yield session


client = TestClient(app)


@pytest.fixture(autouse=True)
def _db():
    # Save/restore rather than a permanent module-level assignment: other
    # test files (test_api.py) also override get_session on this same
    # shared `app` object, and a bare module-level clobber here — even
    # though test_api.py does exactly that — caused test_api.py's own
    # tests to fail against an empty, never-migrated engine when both files
    # were collected together. test_phase8_security.py's per-test-scoped
    # pattern (set, run, pop) is the safe convention; this follows it, with
    # an explicit restore (not just pop) so it can never matter which file
    # happens to run first or last.
    previous_override = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _session_override
    SQLModel.metadata.create_all(engine)
    yield
    app.dependency_overrides.pop(get_optional_current_leader, None)
    if previous_override is not None:
        app.dependency_overrides[get_session] = previous_override
    else:
        app.dependency_overrides.pop(get_session, None)
    SQLModel.metadata.drop_all(engine)


def _seed_complaint(concerned_leader_id=None) -> uuid.UUID:
    with Session(engine) as session:
        c = Complaint(
            submission_type=SubmissionType.complaint,
            raw_text="Garbage pile near the market",
            citizen_name="Sumit", citizen_phone="9876543210",
            category=Category.roads, location_area="Old Area",
            status=Status.open, pipeline_status=PipelineStatus.done,
            concerned_leader_id=concerned_leader_id,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        return c.id


def _get_complaint(complaint_id: uuid.UUID) -> Complaint:
    with Session(engine) as session:
        return session.get(Complaint, complaint_id)


def test_citizen_correction_applies_unauthenticated():
    """Matches GET /complaints/{id}'s existing trust model — no login
    required, the complaint's own UUID is enough."""
    complaint_id = _seed_complaint()

    resp = client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False,
        "corrections": {"location_area": "Cotton Green"},
    })

    assert resp.status_code == 201
    assert resp.json()["corrected_fields"] == ["location_area"]
    row = _get_complaint(complaint_id)
    assert row.location_area == "Cotton Green"
    assert row.human_corrected_fields == "location_area"


def test_is_correct_true_never_applies_corrections_even_if_sent():
    complaint_id = _seed_complaint()

    resp = client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": True,
        "corrections": {"location_area": "Should Not Apply"},
    })

    assert resp.status_code == 201
    row = _get_complaint(complaint_id)
    assert row.location_area == "Old Area", "corrections must only ever apply on is_correct=False"


def test_leader_sourced_feedback_without_a_session_is_rejected():
    """Spoofing source='leader' from an anonymous request must not be able
    to mutate the record — this is the authorization gap that opened up the
    moment corrections started having a real effect."""
    complaint_id = _seed_complaint(concerned_leader_id=TEST_LEADER_ID)
    app.dependency_overrides[get_optional_current_leader] = lambda: None

    resp = client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False, "source": "leader",
        "corrections": {"location_area": "Should Not Apply"},
    })

    assert resp.status_code == 403
    row = _get_complaint(complaint_id)
    assert row.location_area == "Old Area"


def test_leader_sourced_feedback_for_a_different_leaders_complaint_is_rejected():
    complaint_id = _seed_complaint(concerned_leader_id=TEST_LEADER_ID)
    app.dependency_overrides[get_optional_current_leader] = lambda: Leader(
        id=OTHER_LEADER_ID, name="Other Leader", phone="9000000000",
        email="other@example.com", city="Pune", pincode="411001",
    )

    resp = client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False, "source": "leader",
        "corrections": {"location_area": "Should Not Apply"},
    })

    assert resp.status_code == 403
    row = _get_complaint(complaint_id)
    assert row.location_area == "Old Area"


def test_leader_sourced_feedback_with_a_matching_session_applies():
    complaint_id = _seed_complaint(concerned_leader_id=TEST_LEADER_ID)
    app.dependency_overrides[get_optional_current_leader] = lambda: Leader(
        id=TEST_LEADER_ID, name="Test Leader", phone="9876500000",
        email="leader@example.com", city="Pune", pincode="411001",
    )

    resp = client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False, "source": "leader", "aspect": "location",
        "corrections": {"location_area": "Cotton Green"},
    })

    assert resp.status_code == 201
    row = _get_complaint(complaint_id)
    assert row.location_area == "Cotton Green"
    assert row.human_corrected_fields == "location_area"


def test_invalid_field_in_request_returns_400_and_applies_nothing():
    complaint_id = _seed_complaint()

    resp = client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False,
        "corrections": {"citizen_phone": "0000000000"},
    })

    assert resp.status_code == 400
    row = _get_complaint(complaint_id)
    assert row.citizen_phone == "9876543210"


def test_repeated_corrections_accumulate_in_the_audit_trail():
    complaint_id = _seed_complaint()

    client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False, "corrections": {"location_area": "Cotton Green"},
    })
    client.post(f"/complaints/{complaint_id}/feedback", json={
        "is_correct": False, "corrections": {"category": "sanitation"},
    })

    row = _get_complaint(complaint_id)
    assert row.human_corrected_fields == "category,location_area"


def test_unknown_complaint_id_returns_404():
    resp = client.post(f"/complaints/{uuid.uuid4()}/feedback", json={"is_correct": True})
    assert resp.status_code == 404
