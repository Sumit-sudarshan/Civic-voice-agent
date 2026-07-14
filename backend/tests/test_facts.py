import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.db_models import Complaint, SubmissionType, Category, UrgencyLevel, Status
from app.pipeline.facts import (
    assign_tier,
    build_issue_facts,
    compute_cluster_size,
    TIER_ACT_TODAY,
    TIER_ESCALATE,
    TIER_THIS_WEEK,
    TIER_WATCH,
    TIER_ROUTINE,
)


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make(session, **overrides):
    now = datetime.now(timezone.utc)
    defaults = dict(
        submission_type=SubmissionType.complaint,
        raw_text="pothole",
        citizen_name="A",
        citizen_phone="1",
        category=Category.roads,
        location_address="Shriram Nagar",
        location_area="Cotton Green",
        status=Status.open,
        is_valid_submission=True,
        report_count=1,
        created_at=now,
    )
    defaults.update(overrides)
    c = Complaint(**defaults)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


# --- assign_tier precedence table ---

def test_tier_critical_always_wins():
    assert assign_tier(UrgencyLevel.critical, reopened=False, report_count=1) == TIER_ACT_TODAY
    assert assign_tier(UrgencyLevel.critical, reopened=True, report_count=5) == TIER_ACT_TODAY


def test_tier_reopened_overrides_lower_urgency():
    assert assign_tier(UrgencyLevel.medium, reopened=True, report_count=1) == TIER_ESCALATE
    assert assign_tier(UrgencyLevel.low, reopened=True, report_count=1) == TIER_ESCALATE


def test_tier_recurring_report_count_overrides_lower_urgency():
    assert assign_tier(UrgencyLevel.medium, reopened=False, report_count=3) == TIER_ESCALATE
    assert assign_tier(UrgencyLevel.medium, reopened=False, report_count=2) == TIER_WATCH


def test_tier_high_without_escalation_signal():
    assert assign_tier(UrgencyLevel.high, reopened=False, report_count=1) == TIER_THIS_WEEK


def test_tier_medium_and_low_defaults():
    assert assign_tier(UrgencyLevel.medium, reopened=False, report_count=1) == TIER_WATCH
    assert assign_tier(UrgencyLevel.low, reopened=False, report_count=1) == TIER_ROUTINE
    assert assign_tier(None, reopened=False, report_count=1) == TIER_ROUTINE


# --- compute_cluster_size / build_issue_facts ---

def test_cluster_size_counts_same_spot_only(session):
    target = _make(session, location_address="Shriram Nagar", location_area="Cotton Green", category=Category.roads)
    _make(session, location_address="Shriram Nagar", location_area="Cotton Green", category=Category.roads)  # same spot
    _make(session, location_address="Vrindavan Colony", location_area="Cotton Green", category=Category.roads)  # different address
    _make(session, location_address="Shriram Nagar", location_area="Bandra", category=Category.roads)  # different area
    _make(session, location_address="Shriram Nagar", location_area="Cotton Green", category=Category.water)  # different category
    resolved = _make(
        session, location_address="Shriram Nagar", location_area="Cotton Green", category=Category.roads,
        status=Status.resolved,
    )

    assert compute_cluster_size(session, target) == 1  # only the genuine same-spot open one


def test_cluster_size_zero_without_structured_location(session):
    target = _make(session, location_address=None)
    assert compute_cluster_size(session, target) == 0


def test_build_issue_facts_reopened_flag(session):
    resolved = _make(session, status=Status.resolved)
    reopened_complaint = _make(session, reopened_from=resolved.id, urgency_level=UrgencyLevel.medium)

    facts = build_issue_facts(reopened_complaint, session)
    assert facts["reopened_after_resolution"] is True
    assert facts["tier"] == TIER_ESCALATE


def test_build_issue_facts_days_open(session):
    old = _make(
        session,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
        urgency_level=UrgencyLevel.low,
    )
    facts = build_issue_facts(old, session)
    assert facts["days_open"] == 5
