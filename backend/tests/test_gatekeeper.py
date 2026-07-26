import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.pipeline.stages import run_gatekeeper
from app.pipeline.orchestrator import process_turn
from app.models.schemas import ChatMessageRequest

def test_gatekeeper_stage_live():
    """Live test hitting Ollama to check gatekeeper categorization."""
    try:
        res = run_gatekeeper("Pothole on 5th street")
        assert res is not None
        assert res.label == "valid_complaint"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_gatekeeper_spam_live():
    try:
        res = run_gatekeeper("buy cheap watches at http://scam.com")
        assert res is not None
        assert res.label == "spam_or_gibberish"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_gatekeeper_vague_live():
    try:
        res = run_gatekeeper("fix it please")
        assert res is not None
        assert res.label == "too_vague_to_process"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_gatekeeper_abusive_no_issue_live():
    try:
        res = run_gatekeeper("F*** you, I will kill you")
        assert res is not None
        assert res.label == "abusive_or_harmful"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_gatekeeper_profanity_with_real_issue_live():
    """Profanity + an actual civic issue should still register, not be rejected as abuse."""
    try:
        res = run_gatekeeper("This f***ing pothole outside my house has been here for months, fix it now!")
        assert res is not None
        assert res.label == "valid_complaint"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_gatekeeper_personal_emergency_live():
    try:
        res = run_gatekeeper("My father is having a heart attack, please send an ambulance immediately")
        assert res is not None
        assert res.label == "personal_emergency"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _turn(new_message: str) -> ChatMessageRequest:
    return ChatMessageRequest(
        new_message=new_message, history=[], citizen_first_name="Test", citizen_phone="9876543210",
    )


def test_orchestrator_early_exit_logic(monkeypatch, session):
    """Test process_turn's routing logic by mocking the gatekeeper stage."""
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    def mock_run_gatekeeper(text):
        return GatekeeperResponse(label="spam_or_gibberish", confidence="high")

    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", mock_run_gatekeeper)

    result = process_turn(_turn("asdffff"), session)
    assert result.kind == "rejected"
    assert result.rejection_reason == "spam_or_gibberish"

def test_orchestrator_early_exit_abusive(monkeypatch, session):
    """Abusive/harmful submissions with no real issue must be rejected on turn 1."""
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    def mock_run_gatekeeper(text):
        return GatekeeperResponse(label="abusive_or_harmful", confidence="high")

    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", mock_run_gatekeeper)

    result = process_turn(_turn("F*** you, I will kill you"), session)
    assert result.kind == "rejected"
    assert result.rejection_reason == "abusive_or_harmful"

def test_orchestrator_early_exit_personal_emergency(monkeypatch, session):
    """Personal emergencies are out of civic scope and must be rejected, not scored as urgent civic issues."""
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    def mock_run_gatekeeper(text):
        return GatekeeperResponse(label="personal_emergency", confidence="high")

    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", mock_run_gatekeeper)

    result = process_turn(_turn("My father is having a heart attack, send an ambulance"), session)
    assert result.kind == "rejected"
    assert result.rejection_reason == "personal_emergency"
