"""
FastAPI dependencies for protected routes. Session is an httpOnly cookie
(never localStorage — MVP_Design.md §5) holding the raw Supabase access
token; every dependency here re-verifies it against Supabase's JWKS rather
than trusting the cookie's presence alone.

Authorization note: Supabase Row-Level Security is Supabase's answer for
clients that talk to Postgres directly through PostgREST, where `auth.uid()`
reads a per-request JWT claim that PostgREST sets on the connection. This
backend instead connects to Postgres directly via SQLAlchemy as the shared
`postgres` role (through the Supavisor pooler) — a role that owns the tables
and therefore bypasses RLS regardless of any policy, and a connection that
never sets the `request.jwt.claims` GUC `auth.uid()` depends on. Enabling RLS
here would be a no-op that could misleadingly look like protection, so
authorization is enforced in this application layer instead: every query
that returns citizen- or leader-scoped data filters explicitly by the
verified identity from these dependencies. See MVP_roadmap.md Phase 3.
"""
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, HTTPException, Depends, status
from sqlmodel import Session, select

from app.auth.jwks import verify_jwt, InvalidToken
from app.db.session import get_session
from app.models.db_models import Leader

SESSION_COOKIE = "civic_session"


def is_https_request(request: Request) -> bool:
    """
    Whether the original client request was HTTPS — used to decide the
    session cookie's `secure` flag. Not `request.url.scheme`: that reflects
    the loopback hop Nginx/uvicorn actually see (always plain http — the
    Cloudflare tunnel terminates TLS before that point), and Nginx's own
    X-Forwarded-Proto isn't trustworthy here either since it get set to that
    same local scheme by the proxy_pass config, not forwarded from upstream.
    cloudflared instead sets `Cf-Visitor: {"scheme":"https"}` on every quick
    tunnel request, which is what's actually checked here. Falls back to the
    request's own scheme for local dev, where none of this proxying exists.
    """
    cf_visitor = request.headers.get("cf-visitor", "")
    if '"scheme":"https"' in cf_visitor:
        return True
    if "cf-visitor" in request.headers:
        return False  # behind cloudflared but explicitly not https
    return request.url.scheme == "https"


@dataclass
class CurrentUser:
    id: uuid.UUID
    email: Optional[str]
    role: str  # "citizen" | "leader" — a UX hint from signup, not an authorization boundary
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]


def get_current_user(request: Request) -> CurrentUser:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")
    try:
        claims = verify_jwt(token)
    except InvalidToken:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")

    meta = claims.get("user_metadata") or {}
    return CurrentUser(
        id=uuid.UUID(claims["sub"]),
        email=claims.get("email"),
        role=meta.get("role", "citizen"),
        first_name=meta.get("first_name"),
        last_name=meta.get("last_name"),
        phone=meta.get("phone"),
    )


def get_optional_current_user(request: Request) -> Optional[CurrentUser]:
    if not request.cookies.get(SESSION_COOKIE):
        return None
    try:
        return get_current_user(request)
    except HTTPException:
        return None


def get_current_leader(
    current_user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Leader:
    """
    The real authorization boundary for leader-only actions: not the JWT's
    self-reported `role`, but an actual row in our own `leader` table linked
    to this verified auth user id.
    """
    leader = session.exec(select(Leader).where(Leader.auth_user_id == current_user.id)).first()
    if not leader:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a leader account")
    return leader
