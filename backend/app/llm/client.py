import ollama
import httpx
import logging
from typing import Type, TypeVar, Optional
from pydantic import BaseModel
from app.config import settings
from app.llm.parser import parse_with_retries

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class _OpenRouterChatClient:
    """
    Same .chat(...) shape as ollama.Client / _GroqChatClient — OpenRouter's
    REST API is OpenAI-compatible, so this just speaks it directly over
    httpx (already a dependency) instead of pulling in the openai SDK.
    keep_alive and options.num_thread/num_ctx are Ollama-only and ignored.
    """

    def __init__(self, api_key: str):
        self._http = httpx.Client(
            base_url="https://openrouter.ai/api/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60.0,
        )

    def chat(self, model, messages, format=None, keep_alive=None, options=None):
        payload = {"model": model, "messages": messages}
        if format == "json":
            payload["response_format"] = {"type": "json_object"}
        if options and "temperature" in options:
            payload["temperature"] = options["temperature"]
        resp = self._http.post("/chat/completions", json=payload)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"] or ""
        return {"message": {"content": content}}


class _GroqChatClient:
    """
    Exposes the same .chat(model=, messages=, format=, keep_alive=, options=) shape
    as ollama.Client, so parser.py / call_llm_text need no changes to run against
    either backend. keep_alive and options.num_thread/num_ctx are Ollama-only
    (local hardware tuning) and are silently ignored here.
    """

    def __init__(self, api_key: str):
        from groq import Groq
        self._client = Groq(api_key=api_key)

    def chat(self, model, messages, format=None, keep_alive=None, options=None):
        kwargs = {"model": model, "messages": messages}
        if format == "json":
            kwargs["response_format"] = {"type": "json_object"}
        if options and "temperature" in options:
            kwargs["temperature"] = options["temperature"]
        resp = self._client.chat.completions.create(**kwargs)
        return {"message": {"content": resp.choices[0].message.content or ""}}


def _build_llm_client():
    if settings.GROQ_API_KEY:
        logger.info(f"LLM backend: Groq (model={settings.LLM_MODEL})")
        return _GroqChatClient(api_key=settings.GROQ_API_KEY)
    if settings.OPENROUTER_API_KEY:
        logger.info(f"LLM backend: OpenRouter (model={settings.LLM_MODEL})")
        return _OpenRouterChatClient(api_key=settings.OPENROUTER_API_KEY)
    logger.info(f"LLM backend: Ollama (model={settings.LLM_MODEL}, host={settings.OLLAMA_HOST})")
    return ollama.Client(host=settings.OLLAMA_HOST)


ollama_client = _build_llm_client()

def call_llm(system_prompt: str, user_prompt: str, response_model: Type[T]) -> Optional[T]:
    """
    Thin wrapper to call Ollama model and return validated Pydantic models.
    Delegates to parser for retry logic.
    """
    return parse_with_retries(
        client=ollama_client,
        model=settings.LLM_MODEL,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_model=response_model
    )

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
