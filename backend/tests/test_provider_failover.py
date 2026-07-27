"""
Tests for the OpenRouter -> Groq failover chain (llm/client.py).

Context: OpenRouter's free tier returns 429 frequently enough that it caused
visible user-facing degradation in real use — confirmed from production logs
(every gatekeeper/dialogue/reply-composer call in one conversation returning
"429 Too Many Requests"). Groq's independent free-tier quota is the failover.

Three properties matter and are each pinned here:
  1. A failing primary hands off to the next provider, with that provider's
     OWN model name (the namespaces are disjoint — sending OpenRouter's
     "google/gemma-4-31b-it:free" to Groq is meaningless).
  2. A rate-limited provider is abandoned immediately rather than burning its
     full retry budget plus backoff sleeps against a quota that will not
     reset in those few seconds, and is then skipped for a cooldown.
  3. A pinned model (the eval harness's `settings.LLM_MODEL = args.model`)
     DISABLES failover — otherwise a benchmark measuring one model would be
     silently answered in part by another, corrupting the numbers.
"""
import httpx
import pytest
from pydantic import BaseModel

from app.llm import client as llm_client
from app.llm.client import (
    _Provider, _is_rate_limit_error, _usable_providers,
    _cool_down, _is_cooling_down, _provider_cooldowns,
)


class _Schema(BaseModel):
    value: str


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    """The breaker is module-level state — reset it between tests so one
    test's rate limit can't leak into the next."""
    _provider_cooldowns.clear()
    yield
    _provider_cooldowns.clear()


class _FakeClient:
    """Records the model it was called with, so failover can be proven to use
    the *right* model per provider, not just to have happened."""

    def __init__(self, *, exc=None, content='{"value": "ok"}'):
        self.exc = exc
        self.content = content
        self.calls: list[str] = []

    def chat(self, model, messages, format=None, keep_alive=None, options=None):
        self.calls.append(model)
        if self.exc:
            raise self.exc
        return {"message": {"content": self.content}, "usage": None, "model": model}


def _rate_limit_exc():
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(429, request=request)
    return httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)


# ── 1. Failover hands off, with the correct per-provider model ──────────────

def test_failover_uses_the_next_provider_with_its_own_model(monkeypatch):
    primary = _FakeClient(exc=_rate_limit_exc())
    secondary = _FakeClient()
    chain = [
        _Provider("openrouter", primary, "google/gemma-4-31b-it:free"),
        _Provider("groq", secondary, "llama-3.1-8b-instant"),
    ]
    monkeypatch.setattr(llm_client, "sync_providers", chain)

    result = llm_client.call_llm("sys", "user", _Schema, mode="sync", stage="gatekeeper")

    assert result is not None and result.value == "ok", "a healthy secondary must satisfy the call"
    assert primary.calls == ["google/gemma-4-31b-it:free"]
    assert secondary.calls == ["llama-3.1-8b-instant"], "the failover must use Groq's namespace, not OpenRouter's"


def test_returns_none_only_when_every_provider_fails(monkeypatch):
    chain = [
        _Provider("openrouter", _FakeClient(exc=RuntimeError("boom")), "m1"),
        _Provider("groq", _FakeClient(exc=RuntimeError("boom")), "m2"),
    ]
    monkeypatch.setattr(llm_client, "sync_providers", chain)

    assert llm_client.call_llm("sys", "user", _Schema, mode="sync") is None


def test_healthy_primary_is_not_failed_over_from(monkeypatch):
    primary = _FakeClient()
    secondary = _FakeClient()
    monkeypatch.setattr(llm_client, "sync_providers", [
        _Provider("openrouter", primary, "m1"),
        _Provider("groq", secondary, "m2"),
    ])

    llm_client.call_llm("sys", "user", _Schema, mode="sync")

    assert len(primary.calls) == 1
    assert secondary.calls == [], "the secondary must not be touched when the primary works"


# ── 2. Rate limit: fail fast, then cool down ───────────────────────────────

@pytest.mark.parametrize("exc", [
    _rate_limit_exc(),
    RuntimeError("Client error '429 Too Many Requests' for url ..."),
    RuntimeError("Rate limit reached for model"),
])
def test_rate_limit_errors_are_recognized(exc):
    assert _is_rate_limit_error(exc) is True


def test_non_rate_limit_errors_are_not_misclassified():
    assert _is_rate_limit_error(RuntimeError("connection reset by peer")) is False
    assert _is_rate_limit_error(ValueError("invalid json")) is False


def test_a_rate_limited_provider_is_abandoned_without_burning_its_retries(monkeypatch):
    primary = _FakeClient(exc=_rate_limit_exc())
    monkeypatch.setattr(llm_client, "sync_providers", [
        _Provider("openrouter", primary, "m1"),
        _Provider("groq", _FakeClient(), "m2"),
    ])
    monkeypatch.setattr(llm_client.settings, "SYNC_LLM_RETRIES", 2)

    llm_client.call_llm("sys", "user", _Schema, mode="sync")

    assert len(primary.calls) == 1, (
        "a 429 must abandon the provider after ONE attempt — retrying a live quota "
        "block 3x with 1s/3s backoff just adds ~4s of latency before the inevitable failover"
    )


def test_rate_limited_provider_is_skipped_while_cooling_down():
    chain = [_Provider("openrouter", _FakeClient(), "m1"), _Provider("groq", _FakeClient(), "m2")]
    _cool_down("openrouter")

    assert _is_cooling_down("openrouter") is True
    assert [p.name for p in _usable_providers(chain)] == ["groq"]


def test_all_providers_cooling_still_attempts_the_full_chain():
    """The cooldown is a heuristic, not a lock — if everything is cooling we
    still try rather than failing without making a single call."""
    chain = [_Provider("openrouter", _FakeClient(), "m1"), _Provider("groq", _FakeClient(), "m2")]
    _cool_down("openrouter")
    _cool_down("groq")

    assert [p.name for p in _usable_providers(chain)] == ["openrouter", "groq"]


# ── 3. Eval integrity: a pinned model disables failover ────────────────────

def test_pinned_model_disables_failover_to_protect_eval_numbers(monkeypatch):
    primary = _FakeClient(exc=RuntimeError("boom"))
    secondary = _FakeClient()
    monkeypatch.setattr(llm_client, "sync_providers", [
        _Provider("openrouter", primary, "google/gemma-4-31b-it:free"),
        _Provider("groq", secondary, "llama-3.1-8b-instant"),
    ])
    # Simulate `eval/run_eval.py --model ...`
    monkeypatch.setattr(llm_client.settings, "LLM_MODEL", "some/pinned-model")

    result = llm_client.call_llm("sys", "user", _Schema, mode="sync")

    assert result is None, "a pinned eval model must fail honestly rather than silently failing over"
    assert secondary.calls == [], (
        "failing over during an eval run would attribute another model's answers to the "
        "pinned one, corrupting the accuracy numbers the eval exists to produce"
    )
    # A plain RuntimeError is not a rate limit, so the normal retry budget
    # applies — every one of those attempts must still use the pinned model.
    assert primary.calls and set(primary.calls) == {"some/pinned-model"}, (
        "the pinned model must override the provider default on every attempt"
    )
