import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, field_validator
from sqlmodel import Session

from app.config import settings
from app.db.session import get_session
from app.models.db_models import Leader
from app.auth.deps import CurrentUser, get_current_user, is_https_request, SESSION_COOKIE
from app.utils.validators import validate_phone, validate_pincode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

_AUTH_HEADERS = {"apikey": settings.PUBLISHABLE_KEY, "Content-Type": "application/json"}
_SUPABASE_AUTH_URL = f"{settings.SUPABASE_URL}/auth/v1"

# Access tokens are short-lived (Supabase default ~1h) and this MVP does not
# implement silent refresh — a session simply expires and the user logs in
# again. Named as a known gap rather than built out, given the assumed scale
# (a few hundred citizens, not a long-running always-on client). Revisit if
# session drop-outs during a single chat conversation turn out to be common.


class CitizenSignupRequest(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    phone: str
    email: EmailStr
    password: str

    _validate_phone = field_validator("phone")(validate_phone)


class LeaderSignupRequest(BaseModel):
    # Split into first/last (matching CitizenSignupRequest) rather than a
    # single free-text NAME field — the single field meant whatever a leader
    # typed (e.g. just "Sumit") was displayed everywhere else verbatim,
    # including the citizen-facing FR9 concerned-person dropdown, with no
    # structured way to show a proper full name.
    first_name: str
    last_name: Optional[str] = None
    phone: str
    email: EmailStr
    password: str
    city: str
    pincode: str

    _validate_phone = field_validator("phone")(validate_phone)
    _validate_pincode = field_validator("pincode")(validate_pincode)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _signup_message(body: dict) -> str:
    """
    The "check your email" copy is only true when the project requires email
    confirmation. With Supabase's "Confirm email" toggle off, /signup returns
    a live session instead and the account is usable immediately — telling
    that user to go find a confirmation email that will never arrive is a
    dead end, so the message follows the actual response shape.
    """
    if body.get("access_token"):
        return "Account created. You can log in now."
    return "Account created. Check your email to confirm it before logging in."


def _serialize_identity(auth_user_id: str, email: str, meta: dict, session: Session) -> dict:
    """
    Shared shape for "who is currently logged in", used by both /login and
    /me. /login previously built its own, thinner response by hand — it had
    `name` (from the leader signup form's single NAME field) but no nested
    `leader` object, while /me queried the `leader` table and returned
    `leader: {name, city, pincode}` but never `name` at the top level.
    Frontend code reading `user.leader?.name` immediately after login (before
    any subsequent /me call) got nothing, silently falling back further than
    intended. One function now backs both routes so they can't drift apart
    again.
    """
    role = meta.get("role", "citizen")
    result = {
        "id": auth_user_id,
        "email": email,
        "role": role,
        "first_name": meta.get("first_name"),
        "last_name": meta.get("last_name"),
        "name": meta.get("name"),
        "phone": meta.get("phone"),
    }
    if role == "leader":
        from sqlmodel import select
        leader = session.exec(select(Leader).where(Leader.auth_user_id == uuid.UUID(str(auth_user_id)))).first()
        if leader:
            result["leader"] = {
                "id": str(leader.id), "name": leader.name,
                "city": leader.city, "pincode": leader.pincode,
            }
    return result


def _supabase_error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return "Authentication request failed"
    code = body.get("error_code")
    msg = body.get("msg") or body.get("error_description") or ""
    if code == "email_not_confirmed" or "confirm" in msg.lower():
        # Matched on the message text too, not just the exact error_code
        # string — GoTrue's error shapes have changed across API versions
        # before, and this is the one case worth never silently missing.
        return "Please confirm your email (check your inbox) before logging in."
    if code == "user_already_exists":
        return "An account with this email already exists."
    return msg or "Authentication request failed"


@router.post("/citizen/signup", status_code=201)
def citizen_signup(payload: CitizenSignupRequest):
    body = {
        "email": payload.email,
        "password": payload.password,
        "data": {
            "role": "citizen",
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "phone": payload.phone,
        },
    }
    resp = httpx.post(f"{_SUPABASE_AUTH_URL}/signup", headers=_AUTH_HEADERS, json=body, timeout=20)
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=_supabase_error_detail(resp))
    return {"message": _signup_message(resp.json())}


@router.post("/leader/signup", status_code=201)
def leader_signup(payload: LeaderSignupRequest, session: Session = Depends(get_session)):
    full_name = " ".join(p for p in (payload.first_name, payload.last_name) if p).strip()
    body = {
        "email": payload.email,
        "password": payload.password,
        "data": {
            "role": "leader",
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "name": full_name,
            "phone": payload.phone,
        },
    }
    resp = httpx.post(f"{_SUPABASE_AUTH_URL}/signup", headers=_AUTH_HEADERS, json=body, timeout=20)
    if resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=_supabase_error_detail(resp))

    # GoTrue's /signup returns two different shapes depending on the project's
    # "Confirm email" setting: the bare User object when confirmation is
    # required, but a full session envelope ({access_token, ..., user: {...}})
    # when it is turned off. Reading only the top-level "id" raised KeyError ->
    # 500 in the latter case, and — worse — the Supabase account would already
    # exist while the `leader` row never got written, leaving an account that
    # can log in but 403s on every leader route. Handle both shapes.
    signup_body = resp.json()
    auth_user_id = signup_body.get("id") or (signup_body.get("user") or {}).get("id")
    if not auth_user_id:
        logger.error(f"Unexpected Supabase signup response shape: {list(signup_body.keys())}")
        raise HTTPException(status_code=502, detail="Signup succeeded but the account could not be linked. Contact support.")

    leader = Leader(
        auth_user_id=auth_user_id,
        name=full_name,
        phone=payload.phone,
        email=payload.email,
        city=payload.city,
        pincode=payload.pincode,
    )
    session.add(leader)
    session.commit()
    return {"message": _signup_message(signup_body)}


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, session: Session = Depends(get_session)):
    resp = httpx.post(
        f"{_SUPABASE_AUTH_URL}/token?grant_type=password",
        headers=_AUTH_HEADERS,
        json={"email": payload.email, "password": payload.password},
        timeout=20,
    )
    if resp.status_code >= 400:
        raise HTTPException(status_code=401, detail=_supabase_error_detail(resp))

    data = resp.json()
    access_token = data["access_token"]
    user = data["user"]
    meta = user.get("user_metadata") or {}

    response.set_cookie(
        key=SESSION_COOKIE,
        value=access_token,
        httponly=True,
        secure=is_https_request(request),
        samesite="lax",
        max_age=data.get("expires_in", 3600),
        path="/",
    )
    return _serialize_identity(user["id"], user["email"], meta, session)


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"message": "Logged out"}


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)):
    meta = {
        "role": current_user.role,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "name": current_user.name,
        "phone": current_user.phone,
    }
    return _serialize_identity(str(current_user.id), current_user.email, meta, session)
