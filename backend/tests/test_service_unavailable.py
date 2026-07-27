"""
When every configured LLM provider (OpenRouter, then Groq) fails on a live
turn, the citizen must see an honest "service unavailable" outcome rather
than a heuristic-guessed question or a canned template standing in for the
LLM's answer. See orchestrator._service_unavailable and the removal of
Ollama as a reasoning fallback (llm/client.py) — Ollama remains the
embedding backend only (dedup.py), unrelated to this chain.
"""
import pytest
from sqlmodel import Session, SQLModel, create_engine

from app.models.schemas import ChatMessageRequest
from app.pipeline.orchestrator import process_turn


@pytest.fixture(name="session")
def session_fixture():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _turn(new_message: str, history=None) -> ChatMessageRequest:
    return ChatMessageRequest(
        new_message=new_message,
        history=history or [],
        citizen_first_name="Test",
        citizen_phone="9876543210",
    )


def test_turn1_gatekeeper_total_failure_returns_service_unavailable(monkeypatch, session):
    monkeypatch.setattr("app.pipeline.orchestrator.run_gatekeeper", lambda text: None)

    result = process_turn(_turn("There is a pothole near my house"), session)

    assert result.kind == "service_unavailable"
    assert result.service_unavailable_message == "Server down, try again later."


def test_dialogue_manager_total_failure_returns_service_unavailable(monkeypatch, session):
    from app.llm.prompts.gatekeeper import GatekeeperResponse

    monkeypatch.setattr(
        "app.pipeline.orchestrator.run_gatekeeper",
        lambda text: GatekeeperResponse(label="valid_complaint", confidence="high"),
    )
    monkeypatch.setattr("app.pipeline.orchestrator.run_dialogue_manager", lambda transcript: None)

    result = process_turn(_turn("There is a big pothole on my street near the water tank"), session)

    assert result.kind == "service_unavailable"
    assert result.service_unavailable_message == "Server down, try again later."


def test_reply_composer_total_failure_returns_service_unavailable(monkeypatch, session):
    from app.llm.prompts.gatekeeper import GatekeeperResponse
    from app.llm.prompts.dialogue import DialogueState

    monkeypatch.setattr(
        "app.pipeline.orchestrator.run_gatekeeper",
        lambda text: GatekeeperResponse(label="valid_complaint", confidence="high"),
    )
    monkeypatch.setattr(
        "app.pipeline.orchestrator.run_dialogue_manager",
        lambda transcript: DialogueState(issue_clear=False),
    )
    monkeypatch.setattr("app.pipeline.orchestrator.run_reply_composer", lambda *a, **kw: None)

    result = process_turn(_turn("There is a problem"), session)

    assert result.kind == "service_unavailable"
    assert result.service_unavailable_message == "Server down, try again later."
