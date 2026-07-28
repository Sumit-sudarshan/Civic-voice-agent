"""
Real end-to-end test against the LIVE deployed system: the actual Cloudflare
tunnel URL (FastAPI + Nginx on the VM) and the actual Supabase project — not
TestClient, not mocks. Proves the full wiring works for real: Supabase Auth
JWT issuance -> this app's own JWKS verification -> leader-jurisdiction
scoping -> phone masking, all through the real deployed HTTP path.

Two deliberate scope decisions, so this stays fast and deterministic instead
of flaky:

1. Test accounts are created via the Supabase Admin API (`email_confirm:
   true`, service-role key) rather than the public signup endpoint. The
   public signup endpoint sends a real confirmation email, and Supabase's
   free-tier outgoing-email cap is shared across the whole project — a few
   scripted signups exhausts it for every real user for the rest of the hour
   (this is the exact "email rate limit exceeded" error hit during manual
   testing). Same workaround already used for the one-off Phase 8 smoke test.

2. Login goes straight to Supabase's own token endpoint
   (`/auth/v1/token?grant_type=password`), not this app's `/auth/login`
   wrapper. `/auth/login` now requires a real reCAPTCHA Enterprise token,
   which can only be produced by a real browser executing Google's JS
   against the live site key — not something a backend script can fake
   without weakening the reCAPTCHA key itself for real users. This test
   therefore verifies every protected route's real JWT-verification and
   scoping logic (the actual security boundary) using a genuinely
   Supabase-issued token, just obtained one hop earlier than a citizen would.
   reCAPTCHA's own verification logic is unit-tested separately
   (test_recaptcha.py) and does not need live network calls to prove.

The chat/LLM conversation itself is intentionally NOT driven live here
(non-deterministic, and would burn OpenRouter/Groq quota on every CI run for
no additional signal) — that logic is covered by the mocked orchestrator
tests. This test's job is the parts only the real deployed stack can prove:
that a JWT issued by the real Supabase project is accepted by the real
deployed FastAPI app, and that leader-jurisdiction scoping + phone masking
are actually enforced end-to-end, not just in an in-process TestClient.

Skips cleanly (not a failure) if the live URL is unreachable or Supabase
admin credentials aren't configured — this is an opt-in live check, not part
of the default fast local suite.
"""
import os
import secrets
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlmodel import Session, create_engine

from app.config import settings
from app.models.db_models import Complaint, Leader, SubmissionType, Status, PipelineStatus

BASE_URL = os.environ.get("E2E_BASE_URL", "https://approve-videos-webcams-directories.trycloudflare.com")
_ADMIN_HEADERS = {
    "apikey": settings.SECRET_KEY,
    "Authorization": f"Bearer {settings.SECRET_KEY}",
    "Content-Type": "application/json",
}


def _live_stack_available() -> bool:
    if not (settings.SECRET_KEY and settings.PUBLISHABLE_KEY and settings.SUPABASE_URL):
        return False
    try:
        return httpx.get(f"{BASE_URL}/health", timeout=10).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not _live_stack_available(),
        reason="Live E2E: needs the deployed tunnel URL reachable and Supabase admin credentials configured",
    ),
]


def _create_supabase_user(email: str, password: str, metadata: dict) -> str:
    resp = httpx.post(
        f"{settings.SUPABASE_URL}/auth/v1/admin/users",
        headers=_ADMIN_HEADERS,
        json={"email": email, "password": password, "email_confirm": True, "user_metadata": metadata},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def _delete_supabase_user(user_id: str) -> None:
    httpx.delete(f"{settings.SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=_ADMIN_HEADERS, timeout=20)


def _get_session_token(email: str, password: str) -> str:
    resp = httpx.post(
        f"{settings.SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": settings.PUBLISHABLE_KEY, "Content-Type": "application/json"},
        json={"email": email, "password": password},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


@pytest.fixture
def db_engine():
    return create_engine(settings.DATABASE_URL, pool_pre_ping=True)


def test_signup_login_leader_lookup_and_dashboard_scoping_against_live_deployment(db_engine):
    suffix = secrets.token_hex(4)
    citizen_email = f"e2e-citizen-{suffix}@example.com"
    leader_email = f"e2e-leader-{suffix}@example.com"
    password = "TestPass123!"
    city, pincode = f"E2ECity{suffix}", "560001"
    real_phone = "9876543210"

    citizen_auth_id = _create_supabase_user(citizen_email, password, {"role": "citizen", "first_name": "E2E"})
    leader_auth_id = _create_supabase_user(leader_email, password, {"role": "leader", "name": "E2E Leader"})
    leader_row_id = uuid.uuid4()
    complaint_id = uuid.uuid4()

    try:
        # --- Leader jurisdiction row (normally written by /auth/leader/signup
        # alongside the Supabase account; inserted directly here since this
        # test bypasses that endpoint for the reasons in the module docstring).
        with Session(db_engine) as session:
            session.add(Leader(
                id=leader_row_id, auth_user_id=uuid.UUID(leader_auth_id),
                name="E2E Leader", phone="9000000000", email=leader_email,
                city=city, pincode=pincode,
            ))
            session.commit()

        citizen_token = _get_session_token(citizen_email, password)
        leader_token = _get_session_token(leader_email, password)

        # --- Real JWT verification against the live deployed app ---
        r = httpx.get(f"{BASE_URL}/auth/me", cookies={"civic_session": citizen_token}, timeout=15)
        assert r.status_code == 200 and r.json()["role"] == "citizen"

        r = httpx.get(f"{BASE_URL}/auth/me", cookies={"civic_session": leader_token}, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "leader"
        assert r.json()["leader"]["city"] == city

        # --- FR9: citizen-facing leader lookup finds our jurisdiction ---
        r = httpx.get(f"{BASE_URL}/leaders", params={"city": city, "pincode": pincode}, timeout=15)
        assert r.status_code == 200
        assert any(entry["id"] == str(leader_row_id) for entry in r.json())

        # --- Seed a complaint directly (bypasses the live, non-deterministic
        # LLM chat — see module docstring) scoped to this leader ---
        with Session(db_engine) as session:
            now = datetime.now(timezone.utc)
            session.add(Complaint(
                id=complaint_id, submission_type=SubmissionType.complaint,
                raw_text="E2E test complaint - pothole", citizen_name="E2E", citizen_phone=real_phone,
                location_area=f"E2E Area {suffix}", status=Status.open, pipeline_status=PipelineStatus.done,
                is_valid_submission=True, concerned_leader_id=leader_row_id, created_at=now, updated_at=now,
            ))
            session.commit()

        # --- Real leader-jurisdiction scoping + FR12 phone masking, through
        # the live deployed API ---
        r = httpx.get(f"{BASE_URL}/stats/issues", cookies={"civic_session": leader_token}, timeout=15)
        assert r.status_code == 200
        matches = [c for c in r.json()["issues"] if c["id"] == str(complaint_id)]
        assert matches, "the seeded complaint must appear on its assigned leader's live dashboard"
        assert matches[0]["citizen_phone"] != real_phone, "phone must be masked, never the raw value"
        assert matches[0]["citizen_phone"] == real_phone[:2] + "*" * (len(real_phone) - 4) + real_phone[-2:]

    finally:
        with Session(db_engine) as session:
            row = session.get(Complaint, complaint_id)
            if row:
                session.delete(row)
            leader_row = session.get(Leader, leader_row_id)
            if leader_row:
                session.delete(leader_row)
            session.commit()
        _delete_supabase_user(citizen_auth_id)
        _delete_supabase_user(leader_auth_id)
