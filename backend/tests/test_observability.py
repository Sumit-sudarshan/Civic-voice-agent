import json
import logging

from app.utils.logging import JsonFormatter, log_stage
from app.llm.pricing import estimate_cost_usd
from app.llm.cost_logging import log_llm_call


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_includes_standard_and_extra_fields():
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    record.stage = "classify"
    record.cost_usd = 0.0012

    payload = _format(record)
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello world"
    assert payload["stage"] == "classify"
    assert payload["cost_usd"] == 0.0012
    assert "timestamp" in payload


def test_log_stage_emits_structured_fields(caplog):
    logger = logging.getLogger("app.test.orchestrator")
    with caplog.at_level(logging.INFO, logger="app.test.orchestrator"):
        log_stage(logger, "complaint-123", "classify", "proceed", reason="category=roads")

    record = caplog.records[-1]
    assert record.stage == "classify"
    assert record.decision == "proceed"
    assert record.complaint_id == "complaint-123"
    assert record.event == "pipeline_stage"
    assert "Stage: classify" in record.getMessage()


def test_estimate_cost_free_suffix_is_zero():
    assert estimate_cost_usd("meta-llama/llama-3.1-8b-instruct:free", 1000, 500) == 0.0


def test_estimate_cost_unknown_paid_model_is_none(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "OPENROUTER_API_KEY", "sk-fake")
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "")
    assert estimate_cost_usd("some/unlisted-model", 1000, 500) is None


def test_estimate_cost_known_model_computes_expected_value(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "OPENROUTER_API_KEY", "sk-fake")
    monkeypatch.setattr(config.settings, "GROQ_API_KEY", "")
    # openai/gpt-4o-mini: $0.15 / 1M input, $0.60 / 1M output
    cost = estimate_cost_usd("openai/gpt-4o-mini", 1_000_000, 1_000_000)
    assert round(cost, 4) == round(0.15 + 0.60, 4)


def test_log_llm_call_does_not_raise(caplog):
    with caplog.at_level(logging.INFO, logger="app.llm.cost"):
        log_llm_call("classify", "openai/gpt-4o-mini",
                      {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
    record = caplog.records[-1]
    assert record.event == "llm_call"
    assert record.stage == "classify"
    assert record.prompt_tokens == 100
