import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models.schemas import ChatMessageRequest
from app.models.db_models import SubmissionType, Category
from app.pipeline.orchestrator import process_turn, finalize_submission, decide_next_action
from app.llm.prompts.dialogue import DialogueState


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _turn(new_message: str) -> ChatMessageRequest:
    return ChatMessageRequest(
        new_message=new_message,
        history=[],
        citizen_first_name="Test",
        citizen_phone="9876543210",
    )


def test_orchestrator_early_exit_on_spam(monkeypatch, session):
    """Test that the turn-1 gatekeeper rejects spam without reaching the dialogue manager."""
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    def mock_run_gatekeeper(text):
        return GatekeeperResponse(label="spam_or_gibberish", confidence="high")

    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", mock_run_gatekeeper)

    result = process_turn(_turn("buy cheap viagra"), session)
    assert result.kind == "rejected"
    assert result.rejection_reason == "spam_or_gibberish"


def test_orchestrator_early_exit_on_abuse(monkeypatch, session):
    """Abusive/harmful text with no describable issue must be rejected on turn 1."""
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    def mock_run_gatekeeper(text):
        return GatekeeperResponse(label="abusive_or_harmful", confidence="high")

    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", mock_run_gatekeeper)

    result = process_turn(_turn("You are all worthless and deserve to die"), session)
    assert result.kind == "rejected"
    assert result.rejection_reason == "abusive_or_harmful"


def test_orchestrator_early_exit_on_personal_emergency(monkeypatch, session):
    """Personal emergencies are out of scope and must be rejected, not scored as civic issues."""
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    def mock_run_gatekeeper(text):
        return GatekeeperResponse(label="personal_emergency", confidence="high")

    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", mock_run_gatekeeper)

    result = process_turn(_turn("My child is missing, please help"), session)
    assert result.kind == "rejected"
    assert result.rejection_reason == "personal_emergency"


def test_finalize_submission_full_flow(monkeypatch):
    """Test the happy path of finalize_submission (classify -> urgency -> extract -> embed)."""
    from app.llm.prompts.classify import ClassifyResponse
    from app.llm.prompts.urgency import UrgencyResponse
    from app.llm.prompts.extract import ExtractionResponse

    monkeypatch.setattr("app.pipeline.orchestrator.run_classifier", lambda x: ClassifyResponse(category=Category.roads, confidence="high"))
    monkeypatch.setattr("app.pipeline.orchestrator.run_urgency_scorer", lambda x: UrgencyResponse(urgency="high", reasoning="Test"))
    monkeypatch.setattr("app.pipeline.orchestrator.run_extractor", lambda x, *a, **kw: ExtractionResponse(location="Loc", issue_summary="Sum", affected_parties="Part", ask="Ask"))
    monkeypatch.setattr("app.pipeline.orchestrator.embed", lambda x: [0.1, 0.2])

    result = finalize_submission(
        raw_text="Huge pothole",
        submission_type=SubmissionType.complaint,
        citizen_name="Bob",
        citizen_phone="9876543210",
    )

    assert result.is_valid_submission is True
    assert result.category == Category.roads
    assert result.urgency_level == "high"
    assert result.extracted_location == "Loc"
    assert result.embedding == [0.1, 0.2]


# ── Regression tests for the observed dialogue-manager hallucination bugs ──
# (the LLM copying location_address into location_area, or inventing a
# non-numeric "pincode") — decide_next_action must not trust these blindly.

def test_decide_next_action_rejects_area_duplicate_of_address():
    """If the model copies the address text into area (a real observed bug),
    area must still be treated as unresolved and asked about again."""
    state = DialogueState(
        location_address="Shriram Nagar, near the municipal water tank",
        address_specific_enough=True,
        location_area="near the municipal water tank",  # duplicate/landmark, not a real area
        location_pincode=None,
        pincode_declined=False,
        issue_clear=True,
    )
    action = decide_next_action(state, history=[], vagueness_mode=False)
    assert action.kind == "ask_area"


def test_decide_next_action_rejects_non_numeric_pincode():
    """A hallucinated non-6-digit 'pincode' must not be trusted as resolved."""
    state = DialogueState(
        location_address="Rajiv Nagar",
        address_specific_enough=True,
        location_area="Bandra",
        location_pincode="somewhere nearby",  # not a real pincode
        pincode_declined=False,
        issue_clear=True,
    )
    action = decide_next_action(state, history=[], vagueness_mode=False)
    assert action.kind == "ask_pincode"


def test_decide_next_action_accepts_genuine_distinct_area_and_pincode():
    """A real, distinct area name and a real 6-digit pincode should be accepted as-is."""
    state = DialogueState(
        location_address="MG Road, near Ravi's grocery shop",
        address_specific_enough=True,
        location_area="Cotton Green",
        location_pincode="400021",
        pincode_declined=False,
        issue_clear=True,
    )
    action = decide_next_action(state, history=[], vagueness_mode=False)
    assert action.kind == "ready"
    assert action.location_area == "Cotton Green"
    assert action.location_pincode == "400021"


def test_decide_next_action_proceeds_after_area_attempts_exhausted():
    """
    Regression test for a real user-reported failure: a fully actionable
    complaint was DISCARDED ("Can't Proceed With This Request") purely because
    the citizen never produced a separate "broader area" name — something many
    small towns and standalone localities genuinely do not have.

    Running out of area attempts must now proceed with the locality the
    citizen did give, never reject the submission.
    """
    from app.models.schemas import ChatTurnRecord
    from app.pipeline.orchestrator import MAX_AREA_ATTEMPTS

    state = DialogueState(
        location_address="Rajiv Nagar", address_specific_enough=True,
        location_area=None, location_pincode="411001", pincode_declined=False, issue_clear=True,
    )
    history = [
        ChatTurnRecord(speaker="citizen", english_text="..."),
        ChatTurnRecord(speaker="bot", english_text="...", question_key="ask_address"),
        ChatTurnRecord(speaker="citizen", english_text="Rajiv Nagar"),
    ]
    # Exhaust every allowed area attempt.
    for _ in range(MAX_AREA_ATTEMPTS):
        history.append(ChatTurnRecord(speaker="bot", english_text="...", question_key="ask_area"))
        history.append(ChatTurnRecord(speaker="citizen", english_text="I don't know"))

    action = decide_next_action(state, history=history, vagueness_mode=False)
    assert action.kind == "ready", "an answerable complaint must never be thrown away over a missing area label"
    assert action.location_area == "Rajiv Nagar", "falls back to the locality the citizen actually gave"


def test_citizen_asserting_locality_is_the_area_is_accepted_immediately():
    """
    The exact reported conversation: citizen names their locality, then says
    "Area is same as Shriram nagar". That is a complete answer — it must be
    honoured on the spot, not met with another "which broader area?" question.
    """
    from app.models.schemas import ChatTurnRecord

    state = DialogueState(
        location_address="Shriram Nagar Karegaon Road", address_specific_enough=True,
        location_area=None, area_same_as_address=True,
        location_pincode="431401", pincode_declined=False, issue_clear=True,
    )
    history = [
        ChatTurnRecord(speaker="citizen", english_text="Daily power cuts of 2-3 hours"),
        ChatTurnRecord(speaker="bot", english_text="...", question_key="ask_address"),
        ChatTurnRecord(speaker="citizen", english_text="Shriram nagar karegaon road parbhani"),
        ChatTurnRecord(speaker="bot", english_text="...", question_key="ask_area"),
        ChatTurnRecord(speaker="citizen", english_text="Area is same as Shriram nagar"),
    ]

    action = decide_next_action(state, history=history, vagueness_mode=False)
    assert action.kind == "ready", "the citizen answered; asking again reads as the system not listening"
    assert action.location_area == "Shriram Nagar Karegaon Road"


def test_area_assertion_is_ignored_when_no_usable_locality_was_given():
    """
    The assertion escape hatch must not become a way to skip location entirely
    — "that's all I know" with no findable place named is still unresolved.
    """
    state = DialogueState(
        location_address=None, address_specific_enough=False,
        location_area=None, area_same_as_address=True,
        location_pincode="411001", pincode_declined=False, issue_clear=True,
    )
    action = decide_next_action(state, history=[], vagueness_mode=False)
    assert action.kind == "ask_address"
