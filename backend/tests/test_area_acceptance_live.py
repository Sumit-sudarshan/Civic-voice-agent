"""
Live regression tests for a real, user-reported conversational failure.

What went wrong: a citizen reported daily 2-3 hour power cuts (worse in the
monsoon), named their locality ("Shriram Nagar Karegaon Road"), and was then
asked THREE times for a "broader area". They answered every time — "Area is
same as Shriram nagar", then the nearest landmark, then "no need further
clarification" — and the system responded "Can't Proceed With This Request",
discarding a completely actionable complaint over a missing label for a
*larger* place that, in many towns, simply does not exist.

Two independent defects caused it, and both are covered here:
  1. The dialogue-manager prompt had no way to represent "the citizen says
     the locality IS the area" — DialogueState.area_same_as_address now does.
  2. decide_next_action treated area exhaustion as a hard stop. It no longer
     can (see test_orchestrator.py for the deterministic half).

These are live tests because the defect was in the PROMPT — a mocked
DialogueState would assert nothing about whether the model actually reads a
citizen's answer correctly. Skips cleanly if no provider is reachable.
"""
import pytest

from app.models.schemas import ChatTurnRecord
from app.pipeline.orchestrator import decide_next_action
from app.pipeline.stages import run_dialogue_manager

pytestmark = pytest.mark.live


def _judge(transcript: str):
    try:
        state = run_dialogue_manager(transcript)
    except Exception as e:
        pytest.skip(f"Live LLM unavailable: {e}")
    if state is None:
        pytest.skip("Both LLM providers exhausted — no signal about prompt correctness")
    return state


# ── The exact reported conversation ────────────────────────────────────────

REPORTED_TRANSCRIPT = """[Context: the citizen already provided city=Parbhani, pincode=431401 in a form field before this conversation started.]
Citizen: Hello sir in my area there is daily electricity shutdown for 2to 3 hrs and in rainy season this problem goes even worse so please solve this problem.
Agent: Could you tell me the name of the locality or colony where this electricity shutdown issue is happening?
Citizen: Shriram nagar karegaon road parbhani
Agent: And which broader area of Parbhani city is Shriram Nagar Karegaon Road located in?
Citizen: Area is same as Shriram nagar"""


def test_reported_conversation_is_accepted_not_rejected():
    """End-to-end on the real failing transcript: must reach 'ready', not another question."""
    state = _judge(REPORTED_TRANSCRIPT)

    assert state.area_same_as_address is True, (
        '"Area is same as Shriram nagar" is a complete answer — the citizen is stating '
        "there is no separate broader area, not failing to answer"
    )

    history = [
        ChatTurnRecord(speaker="citizen", english_text="daily electricity shutdown 2-3 hrs"),
        ChatTurnRecord(speaker="bot", english_text="...", question_key="ask_address"),
        ChatTurnRecord(speaker="citizen", english_text="Shriram nagar karegaon road parbhani"),
        ChatTurnRecord(speaker="bot", english_text="...", question_key="ask_area"),
        ChatTurnRecord(speaker="citizen", english_text="Area is same as Shriram nagar"),
    ]
    action = decide_next_action(state, history=history, vagueness_mode=False, known_pincode="431401")

    assert action.kind == "ready", (
        f"expected the complaint to be filed, got {action.kind!r} "
        f"(giveup_reason={action.giveup_reason!r}) — this is the reported bug"
    )
    assert action.location_area and action.location_area != "not specified", (
        "the locality the citizen gave must stand in as the area, not be blanked out"
    )


@pytest.mark.parametrize("closing_answer", [
    "that is all I know",
    "I already told you, no need further clarification",
    "Shriram Nagar is the whole place only, there is no bigger area",
])
def test_citizen_signalling_there_is_no_broader_area_is_believed(closing_answer):
    """Several natural phrasings of the same thing must all be accepted."""
    state = _judge(
        "Citizen: Sewage has been overflowing onto our street for four days.\n"
        "Agent: Could you share the colony or locality name?\n"
        "Citizen: Shriram Nagar\n"
        "Agent: Which broader area is Shriram Nagar in?\n"
        f"Citizen: {closing_answer}"
    )
    assert state.area_same_as_address is True, (
        f"{closing_answer!r} tells us the area question is settled; re-asking reads as not listening"
    )


# ── Guards: the escape hatch must not become a hole ────────────────────────

def test_a_genuinely_distinct_area_is_still_captured_normally():
    """The fix must not make the model assert 'same' whenever an area appears."""
    state = _judge(
        "Citizen: Massive pothole on Station Road near the grocery shop.\n"
        "Agent: Which locality is this?\n"
        "Citizen: Parvati Housing Society\n"
        "Agent: Which broader area is that in?\n"
        "Citizen: Yerwada"
    )
    assert state.location_area, "a real, distinct area name must still be recorded"
    assert state.area_same_as_address is False, (
        "the citizen named a separate area — nothing was asserted to be 'the same'"
    )


def test_a_non_place_answer_is_still_treated_as_missing():
    """'my area' names nowhere — the escape hatch must not swallow this."""
    state = _judge(
        "Citizen: There is no water supply in my area.\n"
        "Agent: Could you share the colony or locality name?\n"
        "Citizen: my area"
    )
    assert state.address_specific_enough is False
    action = decide_next_action(state, history=[], vagueness_mode=False, known_pincode="411001")
    assert action.kind.startswith("ask_"), "a genuinely unknown location must still be asked about"
