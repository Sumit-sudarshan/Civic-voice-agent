import pytest
from app.pipeline.stages import run_extractor
from app.pipeline.orchestrator import finalize_submission
from app.models.db_models import SubmissionType, Category

def test_extract_stage_live():
    """Live test hitting Ollama to check extraction scoring."""
    try:
        res = run_extractor("I am sick of the municipality doing nothing! Huge pothole outside my house on MG Road! Fix it immediately!")
        assert res is not None
        assert "MG Road" in res.location
        assert "pothole" in res.issue_summary.lower()
        assert "fix" in res.ask.lower()
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_extract_missing_fields_live():
    """Live test hitting Ollama to check 'not specified' fallback."""
    try:
        res = run_extractor("The lights are broken. Fix them.")
        assert res is not None
        assert res.location == "not specified"
        assert res.affected_parties == "not specified"
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")

def test_finalize_submission_runs_extraction(monkeypatch):
    """Test finalize_submission correctly runs extraction and updates output."""
    from app.llm.prompts.classify import ClassifyResponse
    from app.llm.prompts.urgency import UrgencyResponse
    from app.llm.prompts.extract import ExtractionResponse

    def mock_run_classifier(text):
        return ClassifyResponse(category=Category.roads, confidence="high")

    def mock_run_urgency(text):
        return UrgencyResponse(urgency="medium", reasoning="Test")

    def mock_run_extract(text, known_location=None):
        return ExtractionResponse(
            location="Test location",
            issue_summary="Test issue",
            affected_parties="Test parties",
            ask="Test ask"
        )

    monkeypatch.setattr("app.pipeline.orchestrator.run_classifier", mock_run_classifier)
    monkeypatch.setattr("app.pipeline.orchestrator.run_urgency_scorer", mock_run_urgency)
    monkeypatch.setattr("app.pipeline.orchestrator.run_extractor", mock_run_extract)

    result = finalize_submission(
        raw_text="Test complaint",
        submission_type=SubmissionType.complaint,
        citizen_name="Test",
        citizen_phone="123",
    )

    assert result.is_valid_submission is True
    assert result.extracted_location == "Test location"
    assert result.extracted_issue_summary == "Test issue"
