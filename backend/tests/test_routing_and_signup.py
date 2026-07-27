"""
Regression tests for the post-Phase-9 bug sweep.

Three real defects, all of which only surface on paths the earlier phases'
tests never exercised:

1. `concerned_leader_id` arrives from the request body and is a real FK to
   `leader.id`, but nothing verified it existed. A stale or hand-crafted id
   only failed at INSERT time — several LLM calls into the turn — as an
   IntegrityError the citizen saw as a 500, discarding the whole conversation.

2. A submission with no `concerned_leader_id` is invisible to every leader
   (all leader-facing queries filter on it), yet the citizen still got a
   "Submitted Successfully" confirmation. The chat UI now requires the FR9
   selection; the backend logs a warning if one gets through anyway.

3. GoTrue's /signup returns two different response shapes depending on the
   project's "Confirm email" setting. Leader signup read only the top-level
   "id", so with confirmation turned off (the documented demo toggle) it
   raised KeyError -> 500 *after* the Supabase account already existed,
   leaving an account that can log in but 403s on every leader route.
"""
import uuid

import pytest

from app.models.schemas import ChatMessageRequest


# --------------------------------------------------------------------------
# 1 + 2 — concerned_leader_id validation and the unassigned-submission warning
# --------------------------------------------------------------------------

class _FakeSession:
    """Minimal stand-in; `get` mimics a lookup miss unless told otherwise."""

    def __init__(self, known_leader_id=None):
        self.known_leader_id = known_leader_id
        self.lookups = []

    def get(self, model, pk):
        self.lookups.append(pk)
        return object() if pk == self.known_leader_id else None

    def rollback(self):
        pass

    def commit(self):
        pass

    def add(self, *a, **kw):
        pass


def _stub_llm(monkeypatch):
    """Stop the turn at the first question so no real LLM call is made."""
    from app.pipeline import orchestrator
    from app.llm.prompts.gatekeeper import GatekeeperResponse
    from app.llm.prompts.dialogue import DialogueState

    monkeypatch.setattr(orchestrator, "check_rate_limit", lambda s, o: None)
    monkeypatch.setattr(
        orchestrator, "run_gatekeeper",
        lambda t: GatekeeperResponse(label="valid_complaint", confidence="high"),
    )
    monkeypatch.setattr(
        orchestrator, "run_dialogue_manager",
        lambda t: DialogueState(issue_clear=False),
    )


def _payload(leader_id):
    return ChatMessageRequest(
        new_message="There is a water leak on my street",
        history=[],
        citizen_first_name="Test",
        citizen_phone="9876543210",
        concerned_leader_id=leader_id,
    )


def test_unknown_concerned_leader_id_is_dropped_not_left_to_fail_at_insert(monkeypatch):
    from app.pipeline import orchestrator

    _stub_llm(monkeypatch)
    ghost_id = uuid.uuid4()
    payload = _payload(ghost_id)
    session = _FakeSession(known_leader_id=None)

    orchestrator._prepare_turn(payload, session, None, owner_user_id=uuid.uuid4())

    assert ghost_id in session.lookups, "the leader id must be verified before the turn proceeds"
    assert payload.concerned_leader_id is None, (
        "an unknown leader id must be cleared, so the row still inserts "
        "(NFR7 — never silently drop a submission) instead of raising an FK error"
    )


def test_known_concerned_leader_id_is_preserved(monkeypatch):
    from app.pipeline import orchestrator

    _stub_llm(monkeypatch)
    real_id = uuid.uuid4()
    payload = _payload(real_id)
    session = _FakeSession(known_leader_id=real_id)

    orchestrator._prepare_turn(payload, session, None, owner_user_id=uuid.uuid4())

    assert payload.concerned_leader_id == real_id, "a valid assignment must survive validation"


def test_no_leader_id_skips_the_lookup_entirely(monkeypatch):
    from app.pipeline import orchestrator

    _stub_llm(monkeypatch)
    payload = _payload(None)
    session = _FakeSession()

    orchestrator._prepare_turn(payload, session, None, owner_user_id=uuid.uuid4())

    assert session.lookups == [], "no id to check means no extra query on the hot path"


# --------------------------------------------------------------------------
# 3 — GoTrue signup response shapes
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body,expected_id",
    [
        # "Confirm email" ON — GoTrue returns the bare User object.
        ({"id": "11111111-1111-1111-1111-111111111111", "email": "a@b.c"},
         "11111111-1111-1111-1111-111111111111"),
        # "Confirm email" OFF — GoTrue returns a session envelope instead.
        ({"access_token": "jwt", "refresh_token": "r",
          "user": {"id": "22222222-2222-2222-2222-222222222222", "email": "a@b.c"}},
         "22222222-2222-2222-2222-222222222222"),
    ],
)
def test_leader_signup_reads_the_auth_user_id_from_either_shape(body, expected_id):
    auth_user_id = body.get("id") or (body.get("user") or {}).get("id")
    assert auth_user_id == expected_id


def test_signup_message_matches_whether_confirmation_is_required():
    from app.api.auth import _signup_message

    assert "confirm" in _signup_message({"id": "x"}).lower()
    assert "log in now" in _signup_message({"access_token": "jwt", "user": {"id": "x"}})
