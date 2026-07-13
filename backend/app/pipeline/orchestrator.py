import logging
import re
import uuid
from dataclasses import dataclass
from typing import List, Literal, Optional
from datetime import datetime, timezone
from sqlmodel import Session
from app.models.schemas import ComplaintInternal, ChatMessageRequest, ChatTurnRecord, ChatTurnResponse, LocationSlotsOut
from app.models.db_models import Complaint, Status, SubmissionType, PipelineStatus
from app.pipeline.stages import (
    run_gatekeeper, run_classifier, run_urgency_scorer, run_extractor,
    run_dialogue_manager, run_reply_composer,
)
from app.pipeline.dedup import embed, find_duplicate, find_reopened, merge_complaint
from app.pipeline.language import detect_language
from app.pipeline.translation import translate_to_english
from app.pipeline.dialogue_templates import get_template
from app.llm.prompts.dialogue import DialogueState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# finalize_submission — classify -> urgency (complaints only) -> extract ->
# embed/dedup -> ready-to-persist output. This is what today.process_submission
# used to be, minus gatekeeper (which now runs earlier, once, in process_turn)
# and minus the category-mismatch comparison (there's no citizen-selected
# category to compare against anymore — `category` is the LLM's own call).
# ---------------------------------------------------------------------------

def finalize_submission(
    raw_text: str,
    submission_type: SubmissionType,
    citizen_name: str,
    citizen_phone: str,
    citizen_last_name: Optional[str] = None,
    location_address: Optional[str] = None,
    location_area: Optional[str] = None,
    location_pincode: Optional[str] = None,
    needs_human_review: bool = False,
    review_reason: Optional[str] = None,
    session: Optional[Session] = None,
) -> ComplaintInternal:
    output = ComplaintInternal(
        id=uuid.uuid4(),
        submission_type=submission_type,
        raw_text=raw_text,
        citizen_name=citizen_name,
        citizen_last_name=citizen_last_name,
        citizen_phone=citizen_phone,
        location_address=location_address,
        location_area=location_area,
        location_pincode=location_pincode,
        status=Status.open,
        is_valid_submission=True,
        needs_human_review=needs_human_review,
        review_reason=review_reason,
        report_count=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    output.language_detected = detect_language(raw_text)

    logger.info(f"Starting finalize_submission id={output.id} type={submission_type}")

    # 1. Category Classification
    try:
        classify_result = run_classifier(raw_text)
    except Exception as e:
        logger.error(f"[{output.id}] Classifier exception: {e}")
        classify_result = None

    if not classify_result:
        logger.warning(f"[{output.id}] Stage: Classify | Decision: needs_human_review | Reason: LLM failed at classification stage")
        output.needs_human_review = True
        output.review_reason = "LLM failed at classification stage"
        return output

    output.category = classify_result.category
    logger.info(f"[{output.id}] Stage: Classify | Decision: proceed | Reason: category={classify_result.category}")

    # 2. Urgency Scoring (complaints only)
    if submission_type == SubmissionType.complaint:
        try:
            urgency_result = run_urgency_scorer(raw_text)
        except Exception as e:
            logger.error(f"[{output.id}] Urgency exception: {e}")
            urgency_result = None

        if not urgency_result:
            logger.warning(f"[{output.id}] Stage: Urgency | Decision: needs_human_review | Reason: LLM failed at urgency stage")
            output.needs_human_review = True
            output.review_reason = "LLM failed at urgency stage"
            return output

        output.urgency_level = urgency_result.urgency
        output.urgency_reasoning = urgency_result.reasoning
        logger.info(f"[{output.id}] Stage: Urgency | Decision: proceed | Reason: scored as {urgency_result.urgency} | reasoning={urgency_result.reasoning!r}")
    else:
        logger.info(f"[{output.id}] Stage: Urgency | Decision: skip | Reason: submission is a suggestion")
        output.urgency_level = None
        output.urgency_reasoning = None

    # 3. Structured Field Extraction
    known_location_parts = []
    if location_address and location_address.strip().lower() != "not specified":
        known_location_parts.append(location_address)
    if location_area and location_area.strip().lower() != "not specified":
        known_location_parts.append(f"area: {location_area}")
    if location_pincode and location_pincode.strip().lower() != "not specified":
        known_location_parts.append(f"pincode: {location_pincode}")
    known_location = "; ".join(known_location_parts) if known_location_parts else None

    try:
        extract_result = run_extractor(raw_text, known_location)
    except Exception as e:
        logger.error(f"[{output.id}] Extractor exception: {e}")
        extract_result = None

    if not extract_result:
        logger.warning(f"[{output.id}] Stage: Extract | Decision: needs_human_review | Reason: LLM failed at extraction stage")
        output.needs_human_review = True
        output.review_reason = "LLM failed at extraction stage"
        return output

    logger.info(f"[{output.id}] Stage: Extract | Decision: proceed | Reason: extraction successful")
    output.extracted_location = extract_result.location
    output.extracted_issue_summary = extract_result.issue_summary
    output.extracted_affected_parties = extract_result.affected_parties
    output.extracted_ask = extract_result.ask

    # 4. Embedding & Deduplication
    try:
        output.embedding = embed(raw_text)
        logger.info(f"[{output.id}] Stage: Embed | Decision: proceed | Reason: embedding generated successfully")
    except Exception as e:
        logger.error(f"[{output.id}] Embedding exception: {e}")
        output.embedding = None

    if session and output.embedding:
        dup = find_duplicate(
            session, output.category, location_area,
            output.embedding, location_address=location_address,
        )
        if dup:
            logger.info(f"[{output.id}] Stage: Dedup | Decision: merge | Reason: found duplicate (id={dup.id})")
            merge_complaint(
                session=session,
                existing_complaint=dup,
                raw_text=raw_text,
                citizen_name=citizen_name,
                citizen_phone=citizen_phone,
            )
            output.duplicate_of = dup.id
            output.report_count = dup.report_count
        else:
            reopened = find_reopened(session, output.category, location_area, location_address)
            if reopened:
                logger.info(f"[{output.id}] Stage: Dedup | Decision: insert_as_reopened | Reason: same spot resolved previously (id={reopened.id})")
                output.reopened_from = reopened.id
            else:
                logger.info(f"[{output.id}] Stage: Dedup | Decision: insert | Reason: no duplicate found")

    logger.info(f"finalize_submission finished for id={output.id}")
    return output


# ---------------------------------------------------------------------------
# Conversational turn handling — the dialogue manager drives location/issue
# slot-filling; gatekeeper runs once (turn 1, or once more if the opening
# message was too vague to even tell complaint from suggestion).
# ---------------------------------------------------------------------------

NextActionKind = Literal[
    "ask_address", "ask_landmark", "ask_area", "ask_pincode",
    "ask_issue_clarification", "vagueness_resolved", "ready", "cannot_proceed",
]

MAX_ADDRESS_ATTEMPTS = 2      # base ask + 1 landmark nudge
MAX_AREA_ATTEMPTS = 3
MAX_PINCODE_ATTEMPTS = 3
MAX_ISSUE_ATTEMPTS_VAGUE = 2  # attempts while complaint-vs-suggestion is still unknown
MAX_ISSUE_ATTEMPTS_NORMAL = 1
MAX_TOTAL_BOT_TURNS = 8

# question_key -> the "need" vocabulary compose_reply.py's prompt expects
_NEED_BY_QUESTION_KEY = {
    "ask_address": "address",
    "ask_landmark": "landmark",
    "ask_area": "area",
    "ask_pincode": "pincode",
    "ask_issue_clarification": "issue_clarity",
}
_LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "mr": "Marathi"}


@dataclass
class NextAction:
    kind: NextActionKind
    location_address: Optional[str] = None
    location_area: Optional[str] = None
    location_pincode: Optional[str] = None
    giveup_reason: Optional[str] = None  # set only when kind == "cannot_proceed"


def _asked(history: List[ChatTurnRecord], question_key: str) -> int:
    return sum(1 for t in history if t.speaker == "bot" and t.question_key == question_key)


_PINCODE_RE = re.compile(r"^\d{6}$")


def _looks_like_real_pincode(value: Optional[str]) -> bool:
    return bool(value) and bool(_PINCODE_RE.match(value.strip()))


def _normalize(text: Optional[str]) -> str:
    return (text or "").strip().lower()


def _area_is_probably_duplicate(address: Optional[str], area: Optional[str]) -> bool:
    """
    Defensive guard against a real, observed failure mode: a small/fast LLM
    sometimes copies location_address's text (or a landmark-style phrase)
    into location_area rather than leaving it null when no genuinely
    distinct area name was given. If area is empty, identical to address, or
    one is a substring of the other, treat area as NOT actually resolved —
    forces one more question rather than silently accepting a duplicate.
    """
    a, b = _normalize(address), _normalize(area)
    if not b:
        return True
    if not a:
        return False
    return a == b or a in b or b in a


def decide_next_action(state: DialogueState, history: List[ChatTurnRecord], vagueness_mode: bool) -> NextAction:
    """
    Pure Python, no LLM — turns the dialogue manager's diagnostic judgment
    into an actual next step. Address and issue-clarity caps give up
    gracefully (stored as "not specified"/left as-is) since those aren't
    strictly required to act on a submission. Area and pincode are required:
    exhausting their attempt caps (MAX_AREA_ATTEMPTS / MAX_PINCODE_ATTEMPTS)
    without a resolution is a hard stop ("cannot_proceed") that ends the
    conversation, not a silent fallback — an explicit pincode decline
    ("I don't know") is the one exception, accepted immediately as resolved.

    Deliberately re-validates a couple of the LLM's judgments rather than
    trusting them blindly (see _area_is_probably_duplicate/
    _looks_like_real_pincode) — a prompt regression or an off day from a
    small model should degrade to "ask one more question", never to
    silently accepting hallucinated location data.
    """
    total_bot_turns = sum(1 for t in history if t.speaker == "bot")
    area_resolved = not _area_is_probably_duplicate(state.location_address, state.location_area)
    pincode_resolved = state.location_pincode is not None and (
        _normalize(state.location_pincode) == "not specified" or _looks_like_real_pincode(state.location_pincode)
    )

    def _ready() -> NextAction:
        return NextAction(
            kind="ready",
            location_address=state.location_address or "not specified",
            location_area=state.location_area if area_resolved else "not specified",
            location_pincode=state.location_pincode if pincode_resolved else "not specified",
        )

    if total_bot_turns >= MAX_TOTAL_BOT_TURNS:
        return _ready()

    if vagueness_mode:
        if not state.issue_clear and _asked(history, "ask_issue_clarification") < MAX_ISSUE_ATTEMPTS_VAGUE:
            return NextAction(kind="ask_issue_clarification")
        # Issue is either clear now, or we've given it enough attempts —
        # either way, complaint-vs-suggestion is still unknown. The caller
        # re-runs gatekeeper once (synchronously, same request) and calls
        # this function again with vagueness_mode=False.
        return NextAction(kind="vagueness_resolved")

    # Address: one base ask, one landmark nudge if still not specific enough
    if not (state.location_address and state.address_specific_enough):
        if _asked(history, "ask_address") == 0:
            return NextAction(kind="ask_address")
        if not state.address_specific_enough and _asked(history, "ask_landmark") == 0:
            return NextAction(kind="ask_landmark")
        # give up tightening the address further, fall through

    # Area — ask up to MAX_AREA_ATTEMPTS times; if the citizen still hasn't
    # given a genuine area after that, this is a hard stop (not a silent
    # "not specified" fallback) — the area is required to proceed.
    if not area_resolved:
        if _asked(history, "ask_area") < MAX_AREA_ATTEMPTS:
            return NextAction(kind="ask_area")
        return NextAction(kind="cannot_proceed", giveup_reason="area_missing")

    # Pincode — an explicit decline ("I don't know") is accepted immediately
    # and treated as resolved. Only genuinely unanswered/unusable replies
    # count against the attempt cap; after MAX_PINCODE_ATTEMPTS of those,
    # this is also a hard stop.
    if not pincode_resolved and not state.pincode_declined:
        if _asked(history, "ask_pincode") < MAX_PINCODE_ATTEMPTS:
            return NextAction(kind="ask_pincode")
        return NextAction(kind="cannot_proceed", giveup_reason="pincode_missing")

    # Issue clarity recheck (vagueness-mode already spent its own attempts)
    if not state.issue_clear and _asked(history, "ask_issue_clarification") < MAX_ISSUE_ATTEMPTS_NORMAL:
        return NextAction(kind="ask_issue_clarification")

    return _ready()


def _build_transcript_blob(history: List[ChatTurnRecord], new_message_english: str) -> str:
    lines = []
    for turn in history:
        speaker = "Citizen" if turn.speaker == "citizen" else "Agent"
        lines.append(f"{speaker}: {turn.english_text}")
    lines.append(f"Citizen: {new_message_english}")
    return "\n".join(lines)


_HARD_REJECT_LABELS = {"spam_or_gibberish", "off_topic", "abusive_or_harmful", "personal_emergency"}


def _insert_rejected(raw_text: str, review_reason: str, citizen_name: str, citizen_phone: str,
                      citizen_last_name: Optional[str], session: Session) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    row = Complaint(
        submission_type=SubmissionType.complaint,
        raw_text=raw_text,
        citizen_name=citizen_name,
        citizen_last_name=citizen_last_name,
        citizen_phone=citizen_phone,
        status=Status.open,
        pipeline_status=PipelineStatus.done,
        is_valid_submission=False,
        review_reason=review_reason,
        report_count=1,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.id


def process_turn(payload: ChatMessageRequest, session: Session, background_tasks=None) -> ChatTurnResponse:
    """
    Handles exactly one citizen message. Stateless across HTTP calls — the
    frontend resends the full turn history each time (already
    English-normalized from prior responses), plus `submission_type_hint`
    (the one small piece of client-held state that lets the relatively
    expensive 7-way gatekeeper call run once per conversation, not every
    turn).
    """
    detected_lang = detect_language(payload.new_message)
    new_message_english = (
        translate_to_english(payload.new_message, detected_lang)
        if detected_lang in ("hi", "mr") else payload.new_message
    )

    is_turn_1 = len(payload.history) == 0
    vagueness_mode = payload.submission_type_hint is None and not is_turn_1
    submission_type: Optional[str] = payload.submission_type_hint

    if is_turn_1:
        try:
            gk = run_gatekeeper(new_message_english)
        except Exception as e:
            logger.error(f"Gatekeeper exception on turn 1: {e}")
            gk = None

        if gk is None:
            # LLM failure — degrade to asking for clarification rather than
            # crashing the conversation or silently accepting.
            vagueness_mode = True
            submission_type = None
        elif gk.label in _HARD_REJECT_LABELS:
            row_id = _insert_rejected(
                new_message_english, gk.label,
                f"{payload.citizen_first_name}", payload.citizen_phone,
                payload.citizen_last_name, session,
            )
            logger.info(f"[{row_id}] Stage: Gatekeeper | Decision: rejected | Reason: {gk.label}")
            return ChatTurnResponse(
                kind="rejected",
                detected_language=detected_lang,
                new_message_english=new_message_english,
                rejection_reason=gk.label,
                complaint_id=row_id,
            )
        elif gk.label == "valid_complaint":
            submission_type = "complaint"
        elif gk.label == "valid_suggestion":
            submission_type = "suggestion"
        else:  # too_vague_to_process
            vagueness_mode = True
            submission_type = None

    transcript_blob = _build_transcript_blob(payload.history, new_message_english)

    try:
        dialogue_state = run_dialogue_manager(transcript_blob)
    except Exception as e:
        logger.error(f"Dialogue manager exception: {e}")
        dialogue_state = None

    if dialogue_state is None:
        # Graceful fallback — keep the conversation moving with a safe default
        dialogue_state = DialogueState(issue_clear=False)

    next_action = decide_next_action(dialogue_state, payload.history, vagueness_mode)

    if next_action.kind == "vagueness_resolved":
        try:
            gk2 = run_gatekeeper(transcript_blob)
        except Exception as e:
            logger.error(f"Gatekeeper recheck exception: {e}")
            gk2 = None

        if gk2 and gk2.label in _HARD_REJECT_LABELS:
            row_id = _insert_rejected(
                transcript_blob, gk2.label,
                payload.citizen_first_name, payload.citizen_phone,
                payload.citizen_last_name, session,
            )
            logger.info(f"[{row_id}] Stage: Gatekeeper (recheck) | Decision: rejected | Reason: {gk2.label}")
            return ChatTurnResponse(
                kind="rejected", detected_language=detected_lang, new_message_english=new_message_english,
                rejection_reason=gk2.label, complaint_id=row_id,
            )

        # Default to "complaint" if still ambiguous after a second look —
        # never silently drop a submission just because its type is unclear.
        submission_type = "suggestion" if (gk2 and gk2.label == "valid_suggestion") else "complaint"
        vagueness_mode = False
        next_action = decide_next_action(dialogue_state, payload.history, vagueness_mode=False)

    if next_action.kind == "cannot_proceed":
        row_id = _insert_rejected(
            transcript_blob, next_action.giveup_reason,
            payload.citizen_first_name, payload.citizen_phone,
            payload.citizen_last_name, session,
        )
        logger.info(f"[{row_id}] Stage: Dialogue | Decision: rejected | Reason: {next_action.giveup_reason}")
        return ChatTurnResponse(
            kind="rejected", detected_language=detected_lang, new_message_english=new_message_english,
            rejection_reason=next_action.giveup_reason, complaint_id=row_id,
        )

    if next_action.kind != "ready":
        question_key = next_action.kind
        need = _NEED_BY_QUESTION_KEY.get(question_key, question_key)
        language_name = _LANGUAGE_NAMES.get(detected_lang, "English")

        try:
            composed = run_reply_composer(transcript_blob, need, language_name)
        except Exception as e:
            logger.error(f"Reply composer exception: {e}")
            composed = None

        if composed:
            question_en = composed.reply_english
            question_localized = composed.reply_localized
        else:
            # Graceful fallback — static template, never crash the turn on a
            # single bad LLM response.
            question_en = get_template(question_key, "en")
            question_localized = get_template(question_key, detected_lang)

        return ChatTurnResponse(
            kind="question",
            detected_language=detected_lang,
            new_message_english=new_message_english,
            question_key=question_key,
            question_text=question_localized,
            question_text_english=question_en,
            slots_so_far=LocationSlotsOut(
                address=dialogue_state.location_address,
                area=dialogue_state.location_area,
                pincode=dialogue_state.location_pincode,
            ),
            submission_type_hint=submission_type,
        )

    # ready — persist a pending stub now, run finalize_submission in the background
    now = datetime.now(timezone.utc)
    stub_id = uuid.uuid4()
    stub = Complaint(
        id=stub_id,
        submission_type=SubmissionType(submission_type),
        raw_text=transcript_blob,
        citizen_name=payload.citizen_first_name,
        citizen_last_name=payload.citizen_last_name,
        citizen_phone=payload.citizen_phone,
        location_address=next_action.location_address,
        location_area=next_action.location_area,
        location_pincode=next_action.location_pincode,
        status=Status.open,
        pipeline_status=PipelineStatus.pending,
        report_count=1,
        created_at=now,
        updated_at=now,
    )
    session.add(stub)
    session.commit()
    session.refresh(stub)

    if background_tasks is not None:
        background_tasks.add_task(
            _run_finalize_and_update,
            stub_id, transcript_blob, submission_type,
            payload.citizen_first_name, payload.citizen_phone, payload.citizen_last_name,
            next_action.location_address, next_action.location_area, next_action.location_pincode,
        )

    confirmation_key = "submitted_complaint" if submission_type == "complaint" else "submitted_suggestion"
    return ChatTurnResponse(
        kind="submitted",
        detected_language=detected_lang,
        new_message_english=new_message_english,
        submission_type=submission_type,
        complaint_id=stub_id,
        pipeline_status=PipelineStatus.pending.value,
        confirmation_text=get_template(confirmation_key, detected_lang),
    )


def _run_finalize_and_update(
    stub_id: uuid.UUID, raw_text: str, submission_type: str,
    citizen_name: str, citizen_phone: str, citizen_last_name: Optional[str],
    location_address: Optional[str], location_area: Optional[str], location_pincode: Optional[str],
):
    """Background task: mirrors api/complaints.py's _run_pipeline_and_update pattern."""
    from app.db.session import engine

    with Session(engine) as session:
        db_row = session.get(Complaint, stub_id)
        if not db_row:
            return

        db_row.pipeline_status = PipelineStatus.processing
        db_row.updated_at = datetime.now(timezone.utc)
        session.add(db_row)
        session.commit()

        try:
            result = finalize_submission(
                raw_text=raw_text,
                submission_type=SubmissionType(submission_type),
                citizen_name=citizen_name,
                citizen_phone=citizen_phone,
                citizen_last_name=citizen_last_name,
                location_address=location_address,
                location_area=location_area,
                location_pincode=location_pincode,
                session=session,
            )

            db_row = session.get(Complaint, stub_id)
            if not db_row:
                return  # deleted as a duplicate-merge during finalize_submission

            if getattr(result, "duplicate_of", None) and session.get(Complaint, result.duplicate_of):
                session.delete(db_row)
                session.commit()
                return

            db_row.language_detected = result.language_detected
            db_row.is_valid_submission = result.is_valid_submission
            db_row.category = result.category
            db_row.urgency_level = result.urgency_level
            db_row.urgency_reasoning = result.urgency_reasoning
            db_row.extracted_location = result.extracted_location
            db_row.extracted_issue_summary = result.extracted_issue_summary
            db_row.extracted_affected_parties = result.extracted_affected_parties
            db_row.extracted_ask = result.extracted_ask
            db_row.reopened_from = result.reopened_from
            db_row.needs_human_review = result.needs_human_review
            db_row.review_reason = result.review_reason
            db_row.embedding = result.embedding

            stage_failed = bool(result.review_reason and result.review_reason.startswith("LLM failed"))
            db_row.pipeline_status = PipelineStatus.failed if stage_failed else PipelineStatus.done
            db_row.updated_at = datetime.now(timezone.utc)
            session.add(db_row)
            session.commit()
            logger.info(f"[id={stub_id}] finalize_submission finished -> pipeline_status={db_row.pipeline_status}")

        except Exception as e:
            logger.error(f"[id={stub_id}] Background finalize error: {e}")
            try:
                db_row = session.get(Complaint, stub_id)
                if db_row:
                    db_row.pipeline_status = PipelineStatus.failed
                    db_row.review_reason = f"pipeline_error: {str(e)[:200]}"
                    db_row.needs_human_review = True
                    db_row.updated_at = datetime.now(timezone.utc)
                    session.add(db_row)
                    session.commit()
            except Exception as inner_e:
                logger.error(f"[id={stub_id}] Failed to mark pipeline_status=failed: {inner_e}")
