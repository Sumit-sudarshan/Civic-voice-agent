"""
Regression tests for a real UX bug: the FR9 header fields (city/pincode,
used to filter the concerned-person dropdown) were never sent to the
backend at all — only `concerned_leader_id` was. So the conversation would
ask for the pincode a second time, mid-chat, even though the citizen had
already typed it above the thread. Confirmed live: the bot's exact reply
("Do you happen to know the PIN code for that area? No worries if not.")
turned out to be the prompt's OWN single few-shot example, echoed almost
verbatim — a separate, compounding bug fixed alongside this one (see
compose_reply.py / compose_reply_stream.py's expanded few-shot sets).

Two independent layers now prevent the redundant ask:
  1. `_build_transcript_blob` prepends a "[Context: ...]" line so the LLM
     (dialogue manager + reply composer) sees the already-known city/pincode.
  2. `decide_next_action`'s `known_pincode` param is a deterministic backstop
     — even if the LLM ignores that context on an off day, the pure-Python
     decision logic still treats a valid pre-supplied pincode as resolved.
"""
from app.models.schemas import ChatTurnRecord
from app.pipeline.orchestrator import decide_next_action, _build_transcript_blob
from app.llm.prompts.dialogue import DialogueState


# ── _build_transcript_blob: known-context line ──────────────────────────────

def test_known_city_and_pincode_are_prepended_as_context():
    blob = _build_transcript_blob([], "There's a pothole", known_city="Parbhani", known_pincode="431401")
    assert blob.startswith("[Context:")
    assert "city=Parbhani" in blob
    assert "pincode=431401" in blob
    assert "There's a pothole" in blob


def test_no_context_line_when_nothing_known():
    blob = _build_transcript_blob([], "There's a pothole")
    assert not blob.startswith("[Context:")
    assert blob == "Citizen: There's a pothole"


def test_context_line_handles_city_only():
    blob = _build_transcript_blob([], "issue", known_city="Pune", known_pincode=None)
    context_line = blob.split("\n")[0]
    assert "city=Pune" in context_line
    assert "pincode=" not in context_line


# ── decide_next_action: known_pincode as a deterministic backstop ──────────

def _resolved_state(pincode=None):
    return DialogueState(
        location_address="Rajiv Nagar", address_specific_enough=True,
        location_area="Cotton Green", location_pincode=pincode,
        pincode_declined=False, issue_clear=True,
    )


def test_known_pincode_short_circuits_ask_pincode():
    """Address and area are resolved, the LLM hasn't mentioned pincode at
    all yet — but the citizen already gave one via the FR9 header field."""
    state = _resolved_state(pincode=None)
    action = decide_next_action(state, history=[], vagueness_mode=False, known_pincode="431401")

    assert action.kind == "ready", "a known, valid pincode must not trigger another ask_pincode"
    assert action.location_pincode == "431401", "the known pincode must land on the final record"


def test_without_known_pincode_the_conversation_still_asks_normally():
    """Regression guard: omitting known_pincode must not change any
    existing behavior — this is additive, not a default-on shortcut."""
    state = _resolved_state(pincode=None)
    action = decide_next_action(state, history=[], vagueness_mode=False)

    assert action.kind == "ask_pincode"


def test_invalid_known_pincode_is_not_trusted():
    """A junk/partial value from the header field (e.g. still being typed)
    must not be treated as a real pincode."""
    state = _resolved_state(pincode=None)
    action = decide_next_action(state, history=[], vagueness_mode=False, known_pincode="43")

    assert action.kind == "ask_pincode"


def test_llm_supplied_pincode_still_wins_over_known_pincode_if_different():
    """If the citizen states a different pincode mid-conversation than the
    one in the header field, the conversation's own value (presumably more
    specific/current) takes precedence — known_pincode is a fallback, not an
    override of what was actually said."""
    state = _resolved_state(pincode="411001")
    action = decide_next_action(state, history=[], vagueness_mode=False, known_pincode="431401")

    assert action.kind == "ready"
    assert action.location_pincode == "411001"


def test_known_pincode_does_not_affect_address_or_area_resolution():
    """known_pincode must only ever resolve pincode — it has no business
    influencing whether address/area still need asking about."""
    state = DialogueState(
        location_address=None, address_specific_enough=False,
        location_area=None, location_pincode=None,
        pincode_declined=False, issue_clear=True,
    )
    action = decide_next_action(state, history=[], vagueness_mode=False, known_pincode="431401")

    assert action.kind == "ask_address", "address must still be asked even with a known pincode"


def test_pincode_decline_still_works_alongside_known_pincode_param():
    """An explicit citizen decline must still resolve pincode even when no
    known_pincode was supplied at all (existing behavior, unaffected)."""
    state = DialogueState(
        location_address="Rajiv Nagar", address_specific_enough=True,
        location_area="Cotton Green", location_pincode="not specified",
        pincode_declined=True, issue_clear=True,
    )
    action = decide_next_action(state, history=[], vagueness_mode=False, known_pincode=None)

    assert action.kind == "ready"
    assert action.location_pincode == "not specified"
