"""
FR14 — static $-per-1M-token pricing table for cost estimation. OpenRouter
prices vary per model and can change without notice; this is a best-effort
snapshot (https://openrouter.ai/models), not a live-fetched rate — if a
newly-configured model's actual OpenRouter invoice looks off from what's
logged here, refresh this table.

Models with a ":free" suffix are OpenRouter's own $0 free-tier convention
and always cost $0 regardless of this table. Groq's free tier and local
Ollama are never billed per token, so both always resolve to $0 too.
"""
from app.config import settings

# USD per 1,000,000 tokens: (input_price, output_price).
_OPENROUTER_PRICING_PER_1M = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "openai/gpt-4o": (2.50, 10.00),
    "meta-llama/llama-3.1-8b-instruct": (0.055, 0.055),
    "google/gemma-2-9b-it": (0.06, 0.06),
    "mistralai/mistral-7b-instruct": (0.055, 0.055),
}


def estimate_cost_usd(model: str, prompt_tokens, completion_tokens):
    """
    Returns a float, or None when the cost genuinely can't be determined
    (unrecognized paid model) — deliberately NOT 0.0 in that case, since a
    real but unestimated cost silently folding into a $0.00 total would
    defeat the point of a spend alert. Returns 0.0 only for confirmed-free
    paths (":free" models, Groq, local Ollama).
    """
    if not model or prompt_tokens is None or completion_tokens is None:
        return None
    if model.endswith(":free"):
        return 0.0
    if settings.GROQ_API_KEY:
        return 0.0  # Groq billing is separate/out-of-band from OpenRouter; not tracked here.
    if not settings.OPENROUTER_API_KEY:
        return 0.0  # Ollama — local, no per-token cost.

    pricing = _OPENROUTER_PRICING_PER_1M.get(model)
    if not pricing:
        return None
    input_price, output_price = pricing
    return (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price
