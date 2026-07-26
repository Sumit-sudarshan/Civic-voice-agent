import json
import ollama
import httpx
import logging
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


def _build_llm_client(timeout: float):
    if settings.GROQ_API_KEY:
        logger.info(f"LLM backend: Groq (model={settings.LLM_MODEL}, timeout={timeout}s)")
        return _GroqChatClient(api_key=settings.GROQ_API_KEY, timeout=timeout)
    if settings.OPENROUTER_API_KEY:
        logger.info(f"LLM backend: OpenRouter (model={settings.LLM_MODEL}, timeout={timeout}s)")
        return _OpenRouterChatClient(api_key=settings.OPENROUTER_API_KEY, timeout=timeout)
    logger.info(f"LLM backend: Ollama (model={settings.LLM_MODEL}, host={settings.OLLAMA_HOST}, timeout={timeout}s)")
    return ollama.Client(host=settings.OLLAMA_HOST, timeout=timeout)


# Two client instances, not one — the sync conversational loop (gatekeeper,
# dialogue manager, reply composer) and the async finalize pipeline
# (classify, urgency, extract) have different timeout budgets (NFR8), and
# each backend's client pins its timeout at construction time rather than
# accepting it per call. ollama_client kept as an alias for the sync client
# since a few call sites (translation.py) reach for it directly for backward
# compatibility.
sync_llm_client = _build_llm_client(settings.SYNC_LLM_TIMEOUT_S)
async_llm_client = _build_llm_client(settings.ASYNC_LLM_TIMEOUT_S)
ollama_client = sync_llm_client

def call_llm(system_prompt: str, user_prompt: str, response_model: Type[T], mode: str = "sync",
             stage: str = "unknown") -> Optional[T]:
    """
    Thin wrapper to call the configured LLM backend and return a validated
    Pydantic model. Delegates to parser for retry logic. `mode` selects the
    timeout/retry budget (NFR7/NFR8): "sync" for the citizen-facing
    conversational loop, "async" for the background finalize pipeline.
    `stage` (FR14) tags the cost/token log for this call — e.g. "classify",
    "urgency" — so per-call cost is queryable by pipeline stage.
    """
    if mode == "async":
        client, retries, backoff = async_llm_client, settings.ASYNC_LLM_RETRIES, settings.ASYNC_LLM_BACKOFF_S
    else:
        client, retries, backoff = sync_llm_client, settings.SYNC_LLM_RETRIES, settings.SYNC_LLM_BACKOFF_S
    return parse_with_retries(
        client=client,
        model=settings.LLM_MODEL,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=response_model,
        max_retries=retries,
        backoff_schedule=backoff,
        stage=stage,
    )

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
    options = {"temperature": 0.4}

    if isinstance(sync_llm_client, (_OpenRouterChatClient, _GroqChatClient)):
        yield from sync_llm_client.chat_stream(model=settings.LLM_MODEL, messages=messages, options=options, stage=stage)
        return

    # Raw ollama.Client — no wrapper class, so handle its native stream shape directly.
    for chunk in sync_llm_client.chat(
        model=settings.LLM_MODEL,
        messages=messages,
        stream=True,
        keep_alive=settings.OLLAMA_KEEP_ALIVE,
        options={**options, "num_thread": settings.OLLAMA_NUM_THREAD, "num_ctx": settings.OLLAMA_NUM_CTX},
    ):
        content = chunk.get("message", {}).get("content", "") if isinstance(chunk, dict) else chunk.message.content
        if content:
            yield content

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
