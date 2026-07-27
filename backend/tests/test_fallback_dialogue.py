"""
Regression tests for a real bug hit during a live OpenRouter outage: the
dialogue-manager LLM call failed on every retry, and the code fell back to
a blind `DialogueState(issue_clear=False)` default — so a citizen who wrote
several detailed sentences in one message ("Huge pile of uncollected
garbage near the bus stop outside Apex Hospital in Sector 1, near the
municipal water tank area. The dump hasn't been cleared for 4 days...")
was still asked "could you describe the issue in a bit more detail?",
purely because the LLM was down, not because anything was missing.

Two independent fixes are covered here:
  1. fallback_dialogue.build_fallback_dialogue_state — reads the transcript
     directly (word count + landmark/place-noun keywords + pincode regex)
     instead of assuming nothing is known.
  2. dialogue_templates.get_template's variant selection — 5 differently
     structured phrasings per ask_* key so a sustained outage doesn't show
     every citizen the exact same canned line, verified deterministic so
     the English and localized text of one turn always agree.
"""
import uuid
import zlib

from app.pipeline.fallback_dialogue import build_fallback_dialogue_state
from app.pipeline.dialogue_templates import get_template, TEMPLATES, _stable_variant_index
from app.models.schemas import ChatMessageRequest


# ── build_fallback_dialogue_state ───────────────────────────────────────────

def test_detailed_first_message_is_judged_clear_and_yields_an_address_hint():
    transcript = (
        "Citizen: Huge pile of uncollected garbage near the bus stop outside Apex Hospital "
        "in Sector 1, near the municipal water tank area. The dump hasn't been cleared for "
        "4 days, causing a severe foul smell and attracting stray animals."
    )
    state = build_fallback_dialogue_state(transcript)

    assert state.issue_clear is True, "a long, detailed message must not be treated as vague just because the LLM is down"
    assert state.location_address is not None, "'near the bus stop' / 'Apex Hospital' should be picked up as a locating hint"
    assert state.address_specific_enough is True
    assert state.location_area is None, "area must never be guessed — only a real dialogue-manager judgment may set it"


def test_short_vague_message_is_still_judged_unclear():
    transcript = "Citizen: There's a problem, please fix it."
    state = build_fallback_dialogue_state(transcript)

    assert state.issue_clear is False
    assert state.location_address is None


def test_pincode_in_message_is_extracted():
    transcript = "Citizen: No water supply in Kothrud for three days now, pincode 411038."
    state = build_fallback_dialogue_state(transcript)

    assert state.location_pincode == "411038"


def test_only_citizen_lines_are_considered_not_agent_questions():
    # A verbose Agent question shouldn't inflate the perceived word count of
    # what the CITIZEN actually said.
    transcript = (
        "Agent: Could you describe the issue in a bit more detail, tell me exactly what is "
        "happening, where it is, and how long it has been going on for?\n"
        "Citizen: pothole"
    )
    state = build_fallback_dialogue_state(transcript)

    assert state.issue_clear is False


# ── get_template variant selection ──────────────────────────────────────────

ASK_KEYS = ["ask_address", "ask_landmark", "ask_area", "ask_pincode", "ask_issue_clarification"]


def test_every_ask_key_has_at_least_five_variants_in_every_language():
    for key in ASK_KEYS:
        for lang in ("en", "hi", "mr"):
            variants = TEMPLATES[key][lang]
            assert isinstance(variants, list), f"{key}/{lang} must be a list of variants"
            assert len(variants) >= 5, f"{key}/{lang} has only {len(variants)} variant(s)"
            assert len(set(variants)) == len(variants), f"{key}/{lang} has duplicate phrasings"


def test_same_seed_yields_the_same_variant_every_time():
    seed = "Citizen: garbage not collected for a week near the market"
    first = get_template("ask_issue_clarification", "en", variation_seed=seed)
    for _ in range(5):
        assert get_template("ask_issue_clarification", "en", variation_seed=seed) == first


def test_english_and_localized_pick_the_same_variant_index_for_one_seed():
    seed = "Citizen: streetlight has been out for two weeks on MG road"
    en_variants = TEMPLATES["ask_address"]["en"]
    hi_variants = TEMPLATES["ask_address"]["hi"]
    index = _stable_variant_index(seed, len(en_variants))

    assert get_template("ask_address", "en", variation_seed=seed) == en_variants[index]
    assert get_template("ask_address", "hi", variation_seed=seed) == hi_variants[index]


def test_different_conversations_can_land_on_different_variants():
    seeds = [f"Citizen: issue number {i} near the market" for i in range(20)]
    picked = {get_template("ask_issue_clarification", "en", variation_seed=s) for s in seeds}
    assert len(picked) > 1, "20 distinct conversations all landing on the exact same phrasing defeats the point"


def test_missing_seed_still_returns_a_valid_variant():
    # Backward-compatible default — callers that don't care about variety
    # (there are none left in orchestrator.py, but the contract should hold).
    result = get_template("ask_area", "en")
    assert result in TEMPLATES["ask_area"]["en"]


def test_single_string_entries_ignore_the_seed():
    assert get_template("submitted_complaint", "en", variation_seed="anything") == TEMPLATES["submitted_complaint"]["en"]


def test_stable_variant_index_is_pure_crc32_not_python_hash():
    # Guards against a regression to the built-in hash(), which is
    # randomized per-process (PYTHONHASHSEED) and would break the
    # "same seed -> same variant" guarantee across restarts.
    assert _stable_variant_index("abc", 5) == zlib.crc32("abc".encode("utf-8")) % 5


# ── End-to-end: the exact live-outage scenario that surfaced this bug ──────

class _FakeSession:
    def rollback(self):
        pass

    def commit(self):
        pass

    def add(self, *a, **kw):
        pass


def test_detailed_complaint_is_not_re_asked_for_more_detail_during_a_full_llm_outage(monkeypatch):
    """
    Reproduces the exact live scenario: gatekeeper, dialogue-manager, AND the
    reply-composer recheck all fail (OpenRouter 429 on every call, as
    observed live), on a first message that is long and specific. Before the
    fix, this landed on "ask_issue_clarification" regardless — an obviously
    wrong question given how much detail was already provided. After the
    fix, the deterministic fallback recognizes the issue as clear and moves
    on to a question that's actually still unanswered (area).
    """
    from app.pipeline import orchestrator

    def _always_fails(*args, **kwargs):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(orchestrator, "check_rate_limit", lambda s, o: None)
    monkeypatch.setattr(orchestrator, "run_gatekeeper", _always_fails)
    monkeypatch.setattr(orchestrator, "run_dialogue_manager", _always_fails)

    payload = ChatMessageRequest(
        new_message=(
            "Huge pile of uncollected garbage near the bus stop outside Apex Hospital in "
            "Sector 1, near the municipal water tank area. The dump hasn't been cleared for "
            "4 days, causing a severe foul smell and attracting stray animals."
        ),
        history=[],
        citizen_first_name="Test",
        citizen_phone="9876543210",
    )

    result = orchestrator._prepare_turn(payload, _FakeSession(), None, owner_user_id=uuid.uuid4())

    assert isinstance(result, orchestrator.PendingQuestion), f"expected a follow-up question, got {result!r}"
    assert result.question_key != "ask_issue_clarification", (
        "a detailed first message must not be met with 'describe the issue in more detail' "
        "just because the LLM calls failed"
    )
    assert result.question_key == "ask_area", "address is already implied; area is the genuinely unanswered next question"
