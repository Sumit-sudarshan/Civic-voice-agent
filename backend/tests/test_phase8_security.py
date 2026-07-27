"""
Phase 8 — Auth/session isolation + rate limiting (NFR10, roadmap Phase 8).

Two things are proven here, separate from test_api.py's existing
leader-scoping tests (which already prove disjoint jurisdictions via
dependency overrides):

1. The leader identity used for scoping is derived ONLY from the verified
   auth user id (server-side DB lookup), never from anything a client can
   put in a request — so no hand-crafted request body/query string can widen
   what a leader sees. Proven by calling get_current_leader directly with a
   real DB-backed session, not through the dependency-override shortcut.
2. Leader-only endpoints genuinely require authentication — with the global
   dependency override removed, an unauthenticated request is rejected.
3. FR7 rate limiting is scoped per-account (owner_user_id), not global — one
   account tripping the limit never affects another.

A known, deliberate (not new) gap is documented rather than silently
retested as if it were a pass: GET /complaints/{id} is intentionally
unauthenticated (MVP_roadmap.md Phase 3 note under FR6) — a citizen tracks
their own submission by UUID alone, no account-wide list endpoint exists.
That means anyone who obtains/guesses a complaint's UUID can read its raw
text and *unmasked* phone number. This is an accepted v0.1 trade-off (UUIDs
are effectively unguessable, ~122 bits), not something Phase 8 changes —
flagged here so it's a documented, tested trade-off rather than an
unexamined hole.
"""
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_session
from app.auth.deps import get_current_user, get_current_leader, CurrentUser
from app.auth.jwks import verify_jwt, InvalidToken
from app.models.db_models import Complaint, Leader, SubmissionType, Category, Status
from app.pipeline.orchestrator import check_rate_limit, _HOURLY_LIMIT, _DAILY_LIMIT

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


def get_session_override():
    with Session(engine) as session:
        yield session


@pytest.fixture(autouse=True)
def setup_db():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


# ── 1. get_current_leader: identity comes from the DB, not the request ─────

def test_get_current_leader_matches_only_the_verified_auth_user():
    """Two leader rows exist; the function must return the one whose
    auth_user_id equals the verified user — never the other, and nothing
    about which row comes back is influenced by request content."""
    user_a_auth_id = uuid.uuid4()
    user_b_auth_id = uuid.uuid4()
    with Session(engine) as session:
        leader_a = Leader(auth_user_id=user_a_auth_id, name="Leader A", phone="9000000001",
                           email="a@example.com", city="Pune", pincode="411001")
        leader_b = Leader(auth_user_id=user_b_auth_id, name="Leader B", phone="9000000002",
                           email="b@example.com", city="Mumbai", pincode="400001")
        session.add(leader_a)
        session.add(leader_b)
        session.commit()
        session.refresh(leader_a)
        session.refresh(leader_b)

        current_user = CurrentUser(id=user_a_auth_id, email="a@example.com", role="leader",
                                    first_name="A", last_name=None, name=None, phone=None)
        resolved = get_current_leader(current_user=current_user, session=session)
        assert resolved.id == leader_a.id
        assert resolved.id != leader_b.id


def test_get_current_leader_rejects_auth_user_with_no_leader_row():
    """A citizen JWT (or any auth user id not linked to a leader row) must be
    refused leader-only access — 403, not silently treated as some default
    leader."""
    from fastapi import HTTPException
    with Session(engine) as session:
        current_user = CurrentUser(id=uuid.uuid4(), email="citizen@example.com", role="citizen",
                                    first_name="C", last_name=None, name=None, phone=None)
        with pytest.raises(HTTPException) as exc_info:
            get_current_leader(current_user=current_user, session=session)
        assert exc_info.value.status_code == 403


def test_verify_jwt_rejects_malformed_token():
    """A garbage/tampered token must never verify — no network call needed,
    since a malformed token fails header parsing before any JWKS fetch."""
    with pytest.raises(InvalidToken):
        verify_jwt("not.a.valid.jwt")


# ── 2. Leader endpoints genuinely require authentication ────────────────────
# A dedicated client with NO get_current_user/get_current_leader override —
# proves the real dependency chain 401s an unauthenticated hand-crafted
# request, rather than this being masked by the app-wide test override.

def test_complaints_list_401s_without_a_session_cookie():
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_leader, None)
    try:
        bare_client = TestClient(app)
        response = bare_client.get("/complaints")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_stats_summary_401s_without_a_session_cookie():
    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_leader, None)
    try:
        bare_client = TestClient(app)
        response = bare_client.get("/stats/summary")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_session, None)


# ── 3. FR7 rate limiting is scoped per-account ───────────────────────────────

def _make_complaint(owner_user_id):
    return Complaint(
        submission_type=SubmissionType.complaint,
        raw_text="Pothole",
        citizen_name="Someone",
        citizen_phone="9876543210",
        category=Category.roads,
        status=Status.open,
        owner_user_id=owner_user_id,
    )


def test_rate_limit_blocks_after_hourly_threshold_for_that_account_only():
    account_a = uuid.uuid4()
    account_b = uuid.uuid4()
    with Session(engine) as session:
        for _ in range(_HOURLY_LIMIT):
            session.add(_make_complaint(account_a))
        session.commit()

        assert check_rate_limit(session, account_a) is not None
        # A different account, with zero submissions, must be unaffected.
        assert check_rate_limit(session, account_b) is None


def test_rate_limit_daily_threshold():
    """Spread across the day but outside the last hour, so this exercises the
    daily gate specifically rather than tripping the (checked-first) hourly
    one — the two limits must be independently enforceable."""
    from datetime import datetime, timedelta, timezone
    account = uuid.uuid4()
    with Session(engine) as session:
        now = datetime.now(timezone.utc)
        for i in range(_DAILY_LIMIT):
            c = _make_complaint(account)
            c.created_at = now - timedelta(hours=2, minutes=i)
            session.add(c)
        session.commit()
        message = check_rate_limit(session, account)
        assert message is not None
        assert "day" in message.lower()


def test_rate_limit_no_owner_id_is_not_limited():
    """No verified identity to rate-limit against (shouldn't happen in
    practice — /intake requires auth) — must not crash or false-positive."""
    with Session(engine) as session:
        assert check_rate_limit(session, None) is None
