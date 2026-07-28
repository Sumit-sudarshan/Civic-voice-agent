"""
FR4 — live confirmation that the dialogue manager correctly folds a landmark
answer ("near the municipal water tank") into location_address rather than
mistaking it for a formal area name. This was flagged in MVP_roadmap.md
Phase 4 as "prompt looks correct, not independently re-confirmed live"
(OpenRouter was persistently rate-limited that session) — this test closes
that gap with a real LLM call (OpenRouter/Groq failover applies as usual),
mirroring dialogue.py's own EXAMPLE 2 few-shot case.

Skips (not fails) if both providers are genuinely unreachable — this is a
live confirmation, not a mockable unit test; the deterministic scaffolding
around it (decide_next_action, known-context injection) is already covered
by test_known_location_context.py without needing a live call.
"""
import pytest

from app.pipeline.stages import run_dialogue_manager

pytestmark = pytest.mark.live

_TRANSCRIPT = (
    "Citizen: There is a big pothole on the road near the municipal water tank "
    "in Shriram Nagar, a bike almost crashed into it yesterday.\n"
    "Bot: Which area or locality is this in?\n"
    "Citizen: it is near the municipal water tank"
)


def test_landmark_answer_stays_out_of_location_area():
    try:
        state = run_dialogue_manager(_TRANSCRIPT)
    except Exception as e:
        pytest.skip(f"Live LLM call unavailable: {e}")

    if state is None:
        pytest.skip("Both LLM providers unavailable (chain exhausted) — not a prompt-correctness signal")

    assert state.location_area is None, (
        "a landmark description ('near the municipal water tank') must NOT be "
        "accepted as a formal area name, even though an area question was just asked"
    )
    assert state.location_address and "water tank" in state.location_address.lower(), (
        "the landmark detail must still be captured, just in location_address instead"
    )
