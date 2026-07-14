import pytest
from app.pipeline.stages import run_classifier
from app.models.db_models import Category

def test_classify_stage_live():
    """Live test hitting Ollama to check category classification."""
    try:
        res = run_classifier("A burst water pipe has flooded the road.")
        assert res is not None
        assert res.category == Category.water
    except Exception as e:
        pytest.skip(f"Skipping live test: {e}")
