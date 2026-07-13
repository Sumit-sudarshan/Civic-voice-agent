from app.llm.client import call_llm
from app.llm.prompts.gatekeeper import GatekeeperResponse, GATEKEEPER_SYSTEM_PROMPT, build_gatekeeper_user_prompt
from app.llm.prompts.classify import ClassifyResponse, CLASSIFY_SYSTEM_PROMPT, build_classify_user_prompt
from app.llm.prompts.urgency import UrgencyResponse, URGENCY_SYSTEM_PROMPT, build_urgency_user_prompt
from app.llm.prompts.extract import ExtractionResponse, EXTRACT_SYSTEM_PROMPT, build_extract_user_prompt
from app.llm.prompts.dialogue import DialogueState, DIALOGUE_SYSTEM_PROMPT, build_dialogue_user_prompt
from app.llm.prompts.compose_reply import ComposedReply, COMPOSE_REPLY_SYSTEM_PROMPT, build_compose_reply_user_prompt

def run_gatekeeper(text: str) -> GatekeeperResponse | None:
    return call_llm(
        system_prompt=GATEKEEPER_SYSTEM_PROMPT,
        user_prompt=build_gatekeeper_user_prompt(text),
        response_model=GatekeeperResponse
    )

def run_classifier(text: str) -> ClassifyResponse | None:
    return call_llm(
        system_prompt=CLASSIFY_SYSTEM_PROMPT,
        user_prompt=build_classify_user_prompt(text),
        response_model=ClassifyResponse
    )

def run_urgency_scorer(text: str) -> UrgencyResponse | None:
    return call_llm(
        system_prompt=URGENCY_SYSTEM_PROMPT,
        user_prompt=build_urgency_user_prompt(text),
        response_model=UrgencyResponse
    )

def run_extractor(text: str, known_location: str = None) -> ExtractionResponse | None:
    return call_llm(
        system_prompt=EXTRACT_SYSTEM_PROMPT,
        user_prompt=build_extract_user_prompt(text, known_location),
        response_model=ExtractionResponse
    )

def run_dialogue_manager(transcript_blob: str) -> DialogueState | None:
    return call_llm(
        system_prompt=DIALOGUE_SYSTEM_PROMPT,
        user_prompt=build_dialogue_user_prompt(transcript_blob),
        response_model=DialogueState
    )

def run_reply_composer(transcript_blob: str, need: str, language_name: str) -> ComposedReply | None:
    return call_llm(
        system_prompt=COMPOSE_REPLY_SYSTEM_PROMPT,
        user_prompt=build_compose_reply_user_prompt(transcript_blob, need, language_name),
        response_model=ComposedReply
    )
