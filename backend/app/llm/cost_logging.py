"""
FR14 — logs tokens + estimated cost for every LLM call, tagged by pipeline
stage. Split out from client.py/parser.py (rather than living in either) to
avoid a circular import: client.py already imports parser.py, and both need
this helper.
"""
import logging
from typing import Optional
from app.llm.pricing import estimate_cost_usd

logger = logging.getLogger("app.llm.cost")


def log_llm_call(stage: str, model: str, usage: Optional[dict], success: bool = True):
    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)

    logger.info(
        f"LLM call stage={stage} model={model} tokens={total_tokens} cost_usd={cost_usd}",
        extra={
            "event": "llm_call", "stage": stage, "model": model, "success": success,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": total_tokens, "cost_usd": cost_usd,
        },
    )
