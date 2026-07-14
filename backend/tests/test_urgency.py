import pytest
from app.pipeline.stages import run_urgency_scorer
from app.pipeline.orchestrator import finalize_submission
from app.models.db_models import SubmissionType, Category, UrgencyLevel

def test_urgency_stage_live():
    """Live test hitting Ollama to check urgency scoring."""
    try:
        res = run_urgency_scorer("A live electricity wire is hanging near the school.")
        assert res is not None
        assert res.urgency == UrgencyLevel.critical
        assert len(res.reasoning) > 5
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_finalize_submission_skips_urgency_for_suggestions(monkeypatch):
    """Test finalize_submission correctly skips urgency scoring for suggestions."""
    from app.llm.prompts.classify import ClassifyResponse
    from app.llm.prompts.extract import ExtractionResponse

    def mock_run_classifier(text):
        return ClassifyResponse(category=Category.other, confidence="high")

    def mock_run_urgency(text):
        raise Exception("Urgency scorer should not be called for suggestions")

    def mock_run_extract(text, known_location=None):
        return ExtractionResponse(location="not specified", issue_summary="Sum", affected_parties="Part", ask="Ask")

    monkeypatch.setattr("app.pipeline.orchestrator.run_classifier", mock_run_classifier)
    monkeypatch.setattr("app.pipeline.orchestrator.run_urgency_scorer", mock_run_urgency)
    monkeypatch.setattr("app.pipeline.orchestrator.run_extractor", mock_run_extract)

    result = finalize_submission(
        raw_text="Please build a park here",
        submission_type=SubmissionType.suggestion,
        citizen_name="Test",
        citizen_phone="123",
    )

    assert result.is_valid_submission is True
    assert result.urgency_level is None
    assert result.urgency_reasoning is None
