import json
import time
import ollama
import httpx
import logging
from dataclasses import dataclass
from typing import Iterator, Type, TypeVar, Optional
from pydantic import BaseModel
from app.config import settings
from app.llm.parser import parse_with_retries
from app.llm.cost_logging import log_llm_call

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class _OpenRouterChatClient:
    """
    Same .chat(...) shape as ollama.Client / _GroqChatClient — OpenRouter's
    REST API is OpenAI-compatible, so this just speaks it directly over
    httpx (already a dependency) instead of pulling in the openai SDK.
    keep_alive and options.num_thread/num_ctx are Ollama-only and ignored.
    """

    def __init__(self, api_key: str, timeout: float):
        self._http = httpx.Client(
            base_url="https://openrouter.ai/api/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def chat(self, model, messages, format=None, keep_alive=None, options=None):
        payload = {"model": model, "messages": messages}
        if format == "json":
            payload["response_format"] = {"type": "json_object"}
        if options and "temperature" in options:
            payload["temperature"] = options["temperature"]
        resp = self._http.post("/chat/completions", json=payload)
        resp.raise_for_status()
        body = resp.json()
        content = body["choices"][0]["message"]["content"] or ""
        # FR14 — usage/model are OpenRouter's own OpenAI-compatible response
        # fields; carried through so the caller (parser.py) can log cost.
        return {"message": {"content": content}, "usage": body.get("usage"), "model": body.get("model", model)}

    def chat_stream(self, model, messages, options=None, stage: str = "unknown") -> Iterator[str]:
        payload = {"model": model, "messages": messages, "stream": True,
                   "stream_options": {"include_usage": True}}
        if options and "temperature" in options:
            payload["temperature"] = options["temperature"]
        usage = None
        resp_model = model
        with self._http.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if parsed.get("usage"):
                    usage = parsed["usage"]
                resp_model = parsed.get("model", resp_model)
                choices = parsed.get("choices") or []
                delta = choices[0]["delta"].get("content") if choices else None
                if delta:
                    yield delta
        log_llm_call(stage, resp_model, usage)


class _GroqChatClient:
    """
    Exposes the same .chat(model=, messages=, format=, keep_alive=, options=) shape
    as ollama.Client, so parser.py / call_llm_text need no changes to run against
    either backend. keep_alive and options.num_thread/num_ctx are Ollama-only
    (local hardware tuning) and are silently ignored here.
    """

    def __init__(self, api_key: str, timeout: float):
        from groq import Groq
        self._client = Groq(api_key=api_key, timeout=timeout)

    def chat(self, model, messages, format=None, keep_alive=None, options=None):
        kwargs = {"model": model, "messages": messages}
        if format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        if options and "temperature" in options:
            kwargs["temperature"] = options["temperature"]
        resp = self._client.chat.completions.create(**kwargs)
        usage = resp.usage.model_dump() if getattr(resp, "usage", None) else None
        return {"message": {"content": resp.choices[0].message.content or ""}, "usage": usage, "model": resp.model}

    def chat_stream(self, model, messages, options=None, stage: str = "unknown") -> Iterator[str]:
        kwargs = {"model": model, "messages": messages, "stream": True}
        if options and "temperature" in options:
            kwargs["temperature"] = options["temperature"]
        stream = self._client.chat.completions.create(**kwargs)
        usage = None
        for chunk in stream:
            # Groq's own extension: the final chunk carries usage under
            # x_groq.usage. Best-effort only — cost is $0 for Groq either
            # way (see pricing.py), this is just for token visibility.
            x_groq = getattr(chunk, "x_groq", None)
            if x_groq and getattr(x_groq, "usage", None):
                usage = x_groq.usage.model_dump() if hasattr(x_groq.usage, "model_dump") else x_groq.usage
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
        log_llm_call(stage, model, usage)


@dataclass(frozen=True)
class _Provider:
    """One LLM backend plus the model name that is valid *for that backend*.
    The model cannot be a single global: OpenRouter and Groq have entirely
    separate model namespaces ("google/gemma-4-31b-it:free" vs
    "llama-3.1-8b-instant"), so a name that works on one is meaningless on
    the other and the pairing has to travel together through failover."""
    name: str
    client: object
    model: str


def _build_provider_chain(timeout: float) -> list[_Provider]:
    """
    Ordered failover chain, highest priority first. Any configured provider
    is included; the chain is walked in order until one returns a usable
    response (see call_llm / stream_llm_text).

    OpenRouter is tried before Groq because it is the model the pipeline's
    prompts were most recently tuned against; Groq exists to keep the app
    working through OpenRouter's free-tier 429s, which are frequent enough
    to have caused visible user-facing degradation in real use. Ollama is
    the last resort and only when no hosted key is configured at all, since
    on the e2-micro it is the local embedding model's host, not a
    general-purpose reasoning backend.
    """
    chain: list[_Provider] = []
    if settings.OPENROUTER_API_KEY:
        chain.append(_Provider("openrouter",
                               _OpenRouterChatClient(api_key=settings.OPENROUTER_API_KEY, timeout=timeout),
                               settings.OPENROUTER_MODEL))
    if settings.GROQ_API_KEY:
        chain.append(_Provider("groq",
                               _GroqChatClient(api_key=settings.GROQ_API_KEY, timeout=timeout),
                               settings.GROQ_MODEL))
    if not chain:
        chain.append(_Provider("ollama",
                               ollama.Client(host=settings.OLLAMA_HOST, timeout=timeout),
                               settings.OLLAMA_LLM_MODEL))
    logger.info(
        f"LLM provider chain (timeout={timeout}s): "
        + " -> ".join(f"{p.name}({p.model})" for p in chain)
    )
    return chain


# ── Rate-limit circuit breaker ─────────────────────────────────────────────
# Retrying a provider that just returned 429 is wasted work: the full retry
# budget plus its backoff sleeps (~4s) burns before failover, on every call,
# while the quota demonstrably will not reset in that window. Once a provider
# rate-limits, it is skipped entirely for a cooldown so traffic goes straight
# to the next one. In-memory and per-process by design — this is a latency
# optimization, not a correctness mechanism, so it does not justify shared
# state across workers.
_RATE_LIMIT_COOLDOWN_S = 60.0
_provider_cooldowns: dict[str, float] = {}


def _is_rate_limit_error(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return True
    if getattr(exc, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def _cool_down(provider_name: str) -> None:
    _provider_cooldowns[provider_name] = time.monotonic() + _RATE_LIMIT_COOLDOWN_S
    logger.warning(f"Provider {provider_name} rate-limited; skipping it for {_RATE_LIMIT_COOLDOWN_S:.0f}s")


def _is_cooling_down(provider_name: str) -> bool:
    return time.monotonic() < _provider_cooldowns.get(provider_name, 0.0)


def _usable_providers(chain: list[_Provider]) -> list[_Provider]:
    """Cooled-down providers are skipped — unless every provider is cooling,
    in which case the whole chain is tried anyway rather than failing without
    even attempting a call (the cooldown is a heuristic; a real quota reset
    inside the window should not be locked out)."""
    return [p for p in chain if not _is_cooling_down(p.name)] or chain


# Two chains, not one — the sync conversational loop (gatekeeper, dialogue
# manager, reply composer) and the async finalize pipeline (classify,
# urgency, extract) have different timeout budgets (NFR8), and each backend's
# client pins its timeout at construction time rather than accepting it per
# call.
sync_providers = _build_provider_chain(settings.SYNC_LLM_TIMEOUT_S)
async_providers = _build_provider_chain(settings.ASYNC_LLM_TIMEOUT_S)

# Primary-provider aliases, kept for the Ollama-shaped call sites below
# (call_llm_text) and any external caller that reaches for a bare client.
sync_llm_client = sync_providers[0].client
async_llm_client = async_providers[0].client
ollama_client = sync_llm_client

# Captured at import, before any eval script mutates settings.LLM_MODEL, so
# an explicit override can be told apart from the value config.py derived
# from whichever provider is configured. See _pinned_model().
_DEFAULT_LLM_MODEL = settings.LLM_MODEL


def _pinned_model() -> Optional[str]:
    """
    The eval harness pins a specific model (`settings.LLM_MODEL = args.model`
    in eval/run_eval.py and friends) to measure *that* model's accuracy. If
    failover silently answered some of those cases from a different provider,
    the resulting numbers would be a blend of two models attributed to one —
    quietly corrupting the benchmark the whole eval exists to produce. So a
    pinned model disables failover: the primary provider is used with that
    model, and a failure is a real failure.
    """
    current = settings.LLM_MODEL
    return current if current and current != _DEFAULT_LLM_MODEL else None

def call_llm(system_prompt: str, user_prompt: str, response_model: Type[T], mode: str = "sync",
             stage: str = "unknown", temperature: float = 0.1) -> Optional[T]:
    """
    Thin wrapper to call the configured LLM backend and return a validated
    Pydantic model. Delegates to parser for retry logic. `mode` selects the
    timeout/retry budget (NFR7/NFR8): "sync" for the citizen-facing
    conversational loop, "async" for the background finalize pipeline.
    `stage` (FR14) tags the cost/token log for this call — e.g. "classify",
    "urgency" — so per-call cost is queryable by pipeline stage. `temperature`
    passes straight through to parse_with_retries — see its docstring for why
    the reply-composer stages override the 0.1 default.
    """
    if mode == "async":
        chain, retries, backoff = async_providers, settings.ASYNC_LLM_RETRIES, settings.ASYNC_LLM_BACKOFF_S
    else:
        chain, retries, backoff = sync_providers, settings.SYNC_LLM_RETRIES, settings.SYNC_LLM_BACKOFF_S

    pinned = _pinned_model()
    providers = [chain[0]] if pinned else _usable_providers(chain)

    for provider in providers:
        def _on_call_error(exc: Exception, _name=provider.name) -> bool:
            if _is_rate_limit_error(exc):
                _cool_down(_name)
                return True  # don't burn the retry budget on a live quota block
            return False

        result = parse_with_retries(
            client=provider.client,
            model=pinned or provider.model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            max_retries=retries,
            backoff_schedule=backoff,
            stage=stage,
            on_call_error=_on_call_error,
            temperature=temperature,
        )
        if result is not None:
            return result
        if len(providers) > 1:
            logger.warning(f"Provider {provider.name} failed for stage={stage}; trying next in chain")

    return None

def stream_llm_text(system_prompt: str, user_prompt: str, stage: str = "unknown") -> Iterator[str]:
    """
    FR15 — yields the reply text token-by-token (well, chunk-by-chunk; the
    provider decides chunk granularity) instead of waiting for the full
    response. Always uses the sync-loop client/timeout, since this is only
    ever called for citizen-facing replies in the conversational loop. No
    retry here (unlike call_llm) — a stream that fails partway through can't
    be cleanly restarted mid-sentence; the caller (orchestrator.stream_turn_reply)
    falls back to a static template if nothing streamed successfully at all.
    `stage` (FR14) tags the cost/token log emitted once the stream completes.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    # Higher than the structured-judgment stages' 0.1 (see parser.py) — this
    # is free-form conversational text, where some randomness is the point,
    # not a risk. 0.4 was still low enough that a small/free model tended to
    # fall back on the prompt's single few-shot example almost verbatim
    # rather than generating fresh phrasing (see compose_reply_stream.py).
    options = {"temperature": 0.65}

    pinned = _pinned_model()
    providers = [sync_providers[0]] if pinned else _usable_providers(sync_providers)
    last_error: Optional[Exception] = None

    for provider in providers:
        model = pinned or provider.model
        emitted = False
        try:
            if isinstance(provider.client, (_OpenRouterChatClient, _GroqChatClient)):
                for chunk in provider.client.chat_stream(model=model, messages=messages, options=options, stage=stage):
                    emitted = True
                    yield chunk
            else:
                # Raw ollama.Client — no wrapper class, so handle its native stream shape directly.
                for chunk in provider.client.chat(
                    model=model,
                    messages=messages,
                    stream=True,
                    keep_alive=settings.OLLAMA_KEEP_ALIVE,
                    options={**options, "num_thread": settings.OLLAMA_NUM_THREAD, "num_ctx": settings.OLLAMA_NUM_CTX},
                ):
                    content = chunk.get("message", {}).get("content", "") if isinstance(chunk, dict) else chunk.message.content
                    if content:
                        emitted = True
                        yield content
            return
        except Exception as e:
            last_error = e
            if _is_rate_limit_error(e):
                _cool_down(provider.name)
            # Only fail over if nothing reached the citizen yet. Once tokens
            # have been streamed, restarting on another provider would splice
            # two different half-sentences together mid-reply; the caller
            # (orchestrator.stream_turn_reply) already keeps the partial text.
            if emitted:
                raise
            logger.warning(f"Streaming provider {provider.name} failed before emitting for stage={stage}: {e}")

    if last_error is not None:
        raise last_error

def call_llm_text(system_prompt: str, user_prompt: str) -> Optional[str]:
    """
    Call Ollama and return raw text output — used for free-form narrative
    generation (e.g. AI summary) where JSON output is not needed.
    Returns None on failure.
    """
    try:
        # Scale context with prompt size (top_n can be up to 100 issues) —
        # a fixed window truncates the input on large lists, and the model
        # fills the gap by inventing issues that were cut off. ~4 chars/token.
        est_tokens = len(system_prompt + user_prompt) // 3
        num_ctx = min(max(2048, est_tokens + 512), 8192)

        response = ollama_client.chat(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            keep_alive=settings.OLLAMA_KEEP_ALIVE,
            options={
                "num_thread":  settings.OLLAMA_NUM_THREAD,
                "num_ctx":     num_ctx,
                "temperature": 0.15,  # Low — this must stick to the given data, not improvise
            },
        )
        return response.get("message", {}).get("content", "").strip() or None
    except Exception as e:
        logger.error(f"call_llm_text error: {e}")
        return None
