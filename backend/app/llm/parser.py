import json
import logging
import time
from typing import Type, TypeVar, Optional
from pydantic import BaseModel, ValidationError
from app.config import settings
from app.llm.cost_logging import log_llm_call

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _build_simple_schema_hint(response_model: Type[T]) -> str:
    """
    Build a minimal, readable field description instead of dumping the full
    $defs-heavy JSON schema. Small models (1.5B) confuse the schema for the
    answer and echo it back — a simple field list avoids that failure mode.
    """
    schema = response_model.model_json_schema()

    # Resolve any $ref in properties to their actual enum values
    defs = schema.get("$defs", {})
    props = schema.get("properties", {})

    lines = ["Return a JSON object with exactly these fields:"]
    for field_name, field_info in props.items():
        # Follow $ref if present
        if "$ref" in field_info:
            ref_key = field_info["$ref"].split("/")[-1]
            ref_def = defs.get(ref_key, {})
            enum_vals = ref_def.get("enum", [])
            if enum_vals:
                lines.append(f'  "{field_name}": one of {json.dumps(enum_vals)}')
            else:
                lines.append(f'  "{field_name}": string')
        elif "type" in field_info:
            lines.append(f'  "{field_name}": {field_info["type"]}')
        else:
            lines.append(f'  "{field_name}": string')

    lines.append("No extra keys. No explanations. Only valid JSON.")
    return "\n".join(lines)


def parse_with_retries(
    client, model: str, system_prompt: str, user_prompt: str, response_model: Type[T],
    max_retries: int = 2, backoff_schedule: Optional[list] = None, stage: str = "unknown",
    on_call_error=None,
) -> Optional[T]:
    """
    Calls the LLM, attempts to parse as response_model.
    Two distinct failure modes, both retried up to `max_retries` times
    (`max_retries + 1` attempts total), with a backoff sleep from
    `backoff_schedule` between attempts (NFR7 — a failed call retries with
    bounded attempts, never a silent drop):
      - ValidationError (model returned malformed JSON): the error is
        appended to the prompt so the retry can actually fix it.
      - Any other exception (timeout, connection error, rate limit, etc.):
        retried unchanged — these are transient, not a prompting problem.
    Returns None if every attempt fails, so the caller can fall back
    gracefully (a static template, needs_human_review, etc.) — this
    function itself never raises.

    `on_call_error(exc) -> bool` is an optional hook for non-validation
    errors. Returning True means "this provider is not worth retrying, stop
    now" — used by client.py to abandon a rate-limited provider immediately
    and fail over to the next one, instead of burning the full retry budget
    (plus its backoff sleeps) against a quota that will not reset in a few
    seconds. Validation errors deliberately do NOT consult it: malformed
    JSON is a prompting problem the retry can actually fix.
    """
    if backoff_schedule is None:
        backoff_schedule = [1.0, 3.0]

    schema_hint = _build_simple_schema_hint(response_model)
    base_system_prompt = f"{system_prompt}\n\n{schema_hint}"

    current_user_prompt = user_prompt

    # Ollama tuning options — keep model hot across pipeline calls, limit context.
    # Low temperature keeps this small model on-task for structured extraction
    # instead of improvising fields that aren't in the text.
    ollama_options = {
        "num_thread": settings.OLLAMA_NUM_THREAD,
        "num_ctx": settings.OLLAMA_NUM_CTX,
        "temperature": 0.1,
    }

    total_attempts = max_retries + 1
    for attempt in range(total_attempts):
        is_last_attempt = attempt == total_attempts - 1
        try:
            response = client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": base_system_prompt},
                    {"role": "user", "content": current_user_prompt},
                ],
                format="json",
                keep_alive=settings.OLLAMA_KEEP_ALIVE,
                options=ollama_options,
            )

            raw_output = response.get("message", {}).get("content", "")
            # FR14 — log tokens/cost for every successful call, tagged by stage.
            log_llm_call(stage, response.get("model", model), response.get("usage"), success=True)
            return response_model.model_validate_json(raw_output)

        except ValidationError as e:
            logger.warning(f"LLM validation error on attempt {attempt + 1}/{total_attempts}: {e}")
            if is_last_attempt:
                logger.error("Final LLM retry failed (validation). Returning None.")
                log_llm_call(stage, model, None, success=False)
                return None
            current_user_prompt = (
                f"{user_prompt}\n\n"
                f"Your last response was invalid. Error: {e}. "
                "Fix it and return only the JSON object."
            )
        except Exception as e:
            logger.warning(f"LLM call error on attempt {attempt + 1}/{total_attempts}: {e}")
            give_up = bool(on_call_error(e)) if on_call_error else False
            if is_last_attempt or give_up:
                if give_up and not is_last_attempt:
                    logger.warning(f"Abandoning this provider early (not retryable): {e}")
                else:
                    logger.error(f"Final LLM retry failed (call error): {e}. Returning None.")
                log_llm_call(stage, model, None, success=False)
                return None

        if attempt < len(backoff_schedule):
            time.sleep(backoff_schedule[attempt])

    return None
