from typing import Iterator
from app.llm.client import call_llm, stream_llm_text
from app.llm.prompts.gatekeeper import GatekeeperResponse, GATEKEEPER_SYSTEM_PROMPT, build_gatekeeper_user_prompt
from app.llm.prompts.classify import ClassifyResponse, CLASSIFY_SYSTEM_PROMPT, build_classify_user_prompt
from app.llm.prompts.urgency import UrgencyResponse, URGENCY_SYSTEM_PROMPT, build_urgency_user_prompt
from app.llm.prompts.extract import ExtractionResponse, EXTRACT_SYSTEM_PROMPT, build_extract_user_prompt
from app.llm.prompts.dialogue import DialogueState, DIALOGUE_SYSTEM_PROMPT, build_dialogue_user_prompt
from app.llm.prompts.compose_reply import ComposedReply, COMPOSE_REPLY_SYSTEM_PROMPT, build_compose_reply_user_prompt
from app.llm.prompts.compose_reply_stream import STREAM_COMPOSE_REPLY_SYSTEM_PROMPT, build_stream_compose_reply_user_prompt

# mode="sync": citizen is actively waiting on the HTTP response (gatekeeper,
# dialogue manager, reply composer — all called from process_turn).
# mode="async": runs in the background finalize task, nobody's waiting
# (classify, urgency, extract). See NFR7/NFR8 in MVP_Design.md and the
# SYNC_LLM_*/ASYNC_LLM_* settings in config.py.
#
# `stage=` (FR14) tags each call's cost/token log — see llm/cost_logging.py.

def run_gatekeeper(text: str) -> GatekeeperResponse | None:
    return call_llm(
        system_prompt=GATEKEEPER_SYSTEM_PROMPT,
        user_prompt=build_gatekeeper_user_prompt(text),
        response_model=GatekeeperResponse,
        mode="sync",
        stage="gatekeeper",
    )

def run_classifier(text: str) -> ClassifyResponse | None:
    return call_llm(
        system_prompt=CLASSIFY_SYSTEM_PROMPT,
        user_prompt=build_classify_user_prompt(text),
        response_model=ClassifyResponse,
        mode="async",
        stage="classify",
    )

def run_urgency_scorer(text: str) -> UrgencyResponse | None:
    return call_llm(
        system_prompt=URGENCY_SYSTEM_PROMPT,
        user_prompt=build_urgency_user_prompt(text),
        response_model=UrgencyResponse,
        mode="async",
        stage="urgency",
    )

def run_extractor(text: str, known_location: str = None) -> ExtractionResponse | None:
    return call_llm(
        system_prompt=EXTRACT_SYSTEM_PROMPT,
        user_prompt=build_extract_user_prompt(text, known_location),
        response_model=ExtractionResponse,
        mode="async",
        stage="extract",
    )

def run_dialogue_manager(transcript_blob: str) -> DialogueState | None:
    return call_llm(
        system_prompt=DIALOGUE_SYSTEM_PROMPT,
        user_prompt=build_dialogue_user_prompt(transcript_blob),
        response_model=DialogueState,
        mode="sync",
        stage="dialogue",
    )

def run_reply_composer(transcript_blob: str, need: str, language_name: str) -> ComposedReply | None:
    return call_llm(
        system_prompt=COMPOSE_REPLY_SYSTEM_PROMPT,
        user_prompt=build_compose_reply_user_prompt(transcript_blob, need, language_name),
        response_model=ComposedReply,
        mode="sync",
        stage="compose_reply",
    )

def stream_reply_composer(transcript_blob: str, need: str) -> Iterator[str]:
    """FR15 — English-only streaming counterpart to run_reply_composer."""
    return stream_llm_text(
        system_prompt=STREAM_COMPOSE_REPLY_SYSTEM_PROMPT,
        user_prompt=build_stream_compose_reply_user_prompt(transcript_blob, need),
        stage="compose_reply_stream",
    )
