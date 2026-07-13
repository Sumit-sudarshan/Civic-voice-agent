import json
import logging
from typing import Type, TypeVar, Optional
from pydantic import BaseModel, ValidationError
from app.config import settings

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
    client, model: str, system_prompt: str, user_prompt: str, response_model: Type[T]
) -> Optional[T]:
    """
    Calls the LLM, attempts to parse as response_model.
    On ValidationError, retries by appending the error to the prompt.
    Max 2 retries (3 attempts total).
    """
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

    for attempt in range(3):
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
            return response_model.model_validate_json(raw_output)

        except ValidationError as e:
            logger.warning(f"LLM validation error on attempt {attempt + 1}: {e}")
            if attempt < 2:
                current_user_prompt = (
                    f"{user_prompt}\n\n"
                    f"Your last response was invalid. Error: {e}. "
                    "Fix it and return only the JSON object."
                )
            else:
                logger.error("Final LLM retry failed. Returning None.")
                return None
        except Exception as e:
            logger.error(f"Unexpected error calling LLM: {e}")
            return None

    return None
