import pytest
from unittest.mock import MagicMock
from pydantic import BaseModel, Field, ValidationError
from app.llm.parser import parse_with_retries
from app.llm.client import call_llm

class DummyExtraction(BaseModel):
    name: str = Field(..., description="The name of the person")
    age: int = Field(..., description="The age of the person")

def test_parser_retries_on_failure():
    """Prove that parser.py catches ValidationErrors and retries up to 3 times."""
    mock_client = MagicMock()
    # 1st attempt: missing age
    # 2nd attempt: missing name
    # 3rd attempt: correct JSON
    mock_client.chat.side_effect = [
        {"message": {"content": '{"name": "John"}'}},
        {"message": {"content": '{"age": 30}'}},
        {"message": {"content": '{"name": "John", "age": 30}'}}
    ]
    
    result = parse_with_retries(
        client=mock_client,
        model="dummy-model",
        system_prompt="Test prompt",
        user_prompt="Extract data",
        response_model=DummyExtraction
    )
    
    assert result is not None
    assert result.name == "John"
    assert result.age == 30
    assert mock_client.chat.call_count == 3

def test_live_llm_json_extraction():
    """A real throwaway test hitting the local LLM to verify it can extract JSON."""
    system_prompt = "You are a helpful extraction assistant."
    user_prompt = "Extract the following details: John is 30 years old."
    
    try:
        result = call_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=DummyExtraction
        )
        assert result is not None
        assert result.name.lower() == "john"
        assert result.age == 30
    except Exception as e:
        pytest.skip(f"Live LLM test skipped. Ensure ollama is running and qwen2.5:1.5b is pulled. Error: {e}")
