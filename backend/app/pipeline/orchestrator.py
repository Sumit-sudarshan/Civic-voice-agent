import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Iterator, List, Literal, Optional
from datetime import datetime, timezone, timedelta
from sqlmodel import Session, select
from app.models.schemas import ComplaintInternal, ChatMessageRequest, ChatTurnRecord, ChatTurnResponse, LocationSlotsOut
from app.models.db_models import Complaint, Leader, Status, SubmissionType, PipelineStatus
from app.pipeline.stages import (
    run_gatekeeper, run_classifier, run_urgency_scorer, run_extractor,
    run_dialogue_manager, run_reply_composer, stream_reply_composer,
)
from app.pipeline.dedup import embed, find_duplicate, find_reopened, merge_complaint
from app.pipeline.language import detect_language
from app.pipeline.translation import translate_to_english
from app.pipeline.dialogue_templates import get_template
from app.llm.prompts.dialogue import DialogueState
from app.utils.logging import log_stage

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
        log_stage(logger, output.id, "classify", "needs_human_review",
                  reason="LLM failed at classification stage", level="warning")
        output.needs_human_review = True
        output.review_reason = "LLM failed at classification stage"
        return output

    output.category = classify_result.category
    log_stage(logger, output.id, "classify", "proceed", reason=f"category={classify_result.category}")

    # 2. Urgency Scoring (complaints only)
    if submission_type == SubmissionType.complaint:
        try:
            urgency_result = run_urgency_scorer(raw_text)
        except Exception as e:
            logger.error(f"[{output.id}] Urgency exception: {e}")
            urgency_result = None

        if not urgency_result:
            log_stage(logger, output.id, "urgency", "needs_human_review",
                      reason="LLM failed at urgency stage", level="warning")
            output.needs_human_review = True
            output.review_reason = "LLM failed at urgency stage"
            return output

        output.urgency_level = urgency_result.urgency
        output.urgency_reasoning = urgency_result.reasoning
        log_stage(logger, output.id, "urgency", "proceed",
                  reason=f"scored as {urgency_result.urgency} | reasoning={urgency_result.reasoning!r}",
                  urgency_level=str(urgency_result.urgency))
    else:
        log_stage(logger, output.id, "urgency", "skip", reason="submission is a suggestion")
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
        log_stage(logger, output.id, "extract", "needs_human_review",
                  reason="LLM failed at extraction stage", level="warning")
        output.needs_human_review = True
        output.review_reason = "LLM failed at extraction stage"
        return output

    log_stage(logger, output.id, "extract", "proceed", reason="extraction successful")
    output.extracted_location = extract_result.location
    output.extracted_issue_summary = extract_result.issue_summary
    output.extracted_affected_parties = extract_result.affected_parties
    output.extracted_ask = extract_result.ask

    # 4. Embedding & Deduplication
    try:
        output.embedding = embed(raw_text)
        log_stage(logger, output.id, "embed", "proceed", reason="embedding generated successfully")
    except Exception as e:
        logger.error(f"[{output.id}] Embedding exception: {e}")
        output.embedding = None

    if session and output.embedding:
        dup = find_duplicate(
            session, output.category, location_area,
            output.embedding, location_address=location_address,
        )
        if dup:
            log_stage(logger, output.id, "dedup", "merge", reason=f"found duplicate (id={dup.id})")
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
                log_stage(logger, output.id, "dedup", "insert_as_reopened",
                          reason=f"same spot resolved previously (id={reopened.id})")
                output.reopened_from = reopened.id
            else:
                log_stage(logger, output.id, "dedup", "insert", reason="no duplicate found")

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
# Two asks, not three. The reported failure had the citizen answering "area is
# same as Shriram Nagar" and still being asked twice more — by the second ask
# a citizen who hasn't produced a separate area name almost certainly doesn't
# have one, and further asking reads as the system not listening.
MAX_AREA_ATTEMPTS = 2
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
    one is a substring of the other, treat area as NOT independently
    resolved.

    Note this is only about whether the LLM supplied a *distinct* area — it
    is NOT the same question as "can we proceed". A citizen who tells us the
    locality IS the area has answered completely; that path is handled by
    DialogueState.area_same_as_address in decide_next_action, not here.
    """
    a, b = _normalize(address), _normalize(area)
    if not b:
        return True
    if not a:
        return False
    return a == b or a in b or b in a


def decide_next_action(state: DialogueState, history: List[ChatTurnRecord], vagueness_mode: bool,
                        known_pincode: Optional[str] = None) -> NextAction:
    """
    Pure Python, no LLM — turns the dialogue manager's diagnostic judgment
    into an actual next step. Address, area, and issue-clarity all give up
    gracefully rather than discarding the submission.

    Area specifically is NEVER a hard stop (this was a real, user-reported
    bug): a citizen reporting daily multi-hour power cuts, who had already
    named their locality and then said "area is same as Shriram Nagar", was
    asked three times and then told "Can't Proceed With This Request" — a
    fully actionable complaint thrown away over a missing label for a
    *larger* place that, in many towns, does not exist at all. Two things
    prevent that now: `area_same_as_address` (the citizen asserting the
    locality IS the area, honoured immediately, exactly like an explicit
    pincode decline), and, if the attempt cap is somehow still reached, a
    fall back to the address rather than a rejection. The citizen is the
    authority on their own location.

    Pincode remains a hard stop after MAX_PINCODE_ATTEMPTS, since an
    explicit "I don't know" is already accepted immediately and the FR9
    header field usually supplies it before the chat even starts.

    Deliberately re-validates a couple of the LLM's judgments rather than
    trusting them blindly (see _area_is_probably_duplicate/
    _looks_like_real_pincode) — a prompt regression or an off day from a
    small model should degrade to "ask one more question", never to
    silently accepting hallucinated location data.

    `known_pincode` is the FR9 header field's pincode, if the citizen typed
    one before starting the chat — this is the deterministic backstop for
    never re-asking it: the transcript already carries the same value as
    context for the LLM (see _build_transcript_blob), but a small/free model
    can miss or ignore that context on an off day. Resolving it here too
    means the conversation genuinely cannot ask for it twice, regardless of
    what the LLM does with it.
    """
    total_bot_turns = sum(1 for t in history if t.speaker == "bot")
    has_distinct_area = not _area_is_probably_duplicate(state.location_address, state.location_area)
    # The citizen asserting "the locality IS the area" settles the question
    # just as completely as naming a separate one — but only once they've
    # actually given a usable locality for it to refer to.
    area_asserted = bool(
        getattr(state, "area_same_as_address", False)
        and state.location_address
        and state.address_specific_enough
    )
    area_resolved = has_distinct_area or area_asserted
    effective_pincode = state.location_pincode or (
        known_pincode if _looks_like_real_pincode(known_pincode) else None
    )
    pincode_resolved = effective_pincode is not None and (
        _normalize(effective_pincode) == "not specified" or _looks_like_real_pincode(effective_pincode)
    )

    def _resolved_area() -> Optional[str]:
        """
        The area to file under. A genuinely distinct area wins; otherwise the
        citizen's own locality stands in for it (they told us it's the same
        place), which keeps dedup grouping on something real and keeps the
        leader dashboard showing a location instead of "not specified".
        """
        if has_distinct_area:
            return state.location_area
        if state.location_address and state.address_specific_enough:
            return state.location_address
        return "not specified"

    def _ready() -> NextAction:
        return NextAction(
            kind="ready",
            location_address=state.location_address or "not specified",
            location_area=_resolved_area(),
            location_pincode=effective_pincode if pincode_resolved else "not specified",
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

    # Area — ask at most MAX_AREA_ATTEMPTS times, then proceed with what the
    # citizen gave us. Never a hard stop: see this function's docstring for
    # the real complaint this discarded. If they've named a findable
    # locality, that is enough to act on and enough to route to a leader.
    if not area_resolved and _asked(history, "ask_area") < MAX_AREA_ATTEMPTS:
        return NextAction(kind="ask_area")

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


def _build_transcript_blob(history: List[ChatTurnRecord], new_message_english: str,
                            known_city: Optional[str] = None, known_pincode: Optional[str] = None) -> str:
    lines = []
    # FR9's city/pincode fields sit above the chat thread, not inside it — so
    # without this, the dialogue manager and reply composer never see them
    # and the conversation asks for the pincode again mid-chat, even though
    # the citizen already typed it before the first message. decide_next_action
    # separately re-enforces this deterministically (see its known_pincode
    # param) since a small/free model can still miss context on an off day.
    if known_city or known_pincode:
        known_parts = [p for p in (
            f"city={known_city}" if known_city else None,
            f"pincode={known_pincode}" if known_pincode else None,
        ) if p]
        lines.append(
            "[Context: the citizen already provided " + ", ".join(known_parts) + " in a form "
            "field before this conversation started. Treat this as confirmed — never ask for "
            "the pincode again if it is given here. Note 'area' is a different, smaller thing "
            "than the city: a named neighbourhood the address sits inside, not the city itself.]"
        )
    for turn in history:
        speaker = "Citizen" if turn.speaker == "citizen" else "Agent"
        lines.append(f"{speaker}: {turn.english_text}")
    lines.append(f"Citizen: {new_message_english}")
    return "\n".join(lines)


_HARD_REJECT_LABELS = {"spam_or_gibberish", "off_topic", "abusive_or_harmful", "personal_emergency"}

# Shown when every configured LLM provider (OpenRouter, then Groq) has failed
# or is rate-limited on this turn — an honest error, not a heuristic guess at
# what to ask next (see _prepare_turn/process_turn/stream_turn_reply below).
_SERVICE_UNAVAILABLE_MESSAGE = "Server down, try again later."


def _service_unavailable(detected_lang: str, new_message_english: str) -> ChatTurnResponse:
    return ChatTurnResponse(
        kind="service_unavailable",
        detected_language=detected_lang,
        new_message_english=new_message_english,
        service_unavailable_message=_SERVICE_UNAVAILABLE_MESSAGE,
    )


def _insert_rejected(raw_text: str, review_reason: str, citizen_name: str, citizen_phone: str,
                      citizen_last_name: Optional[str], session: Session,
                      owner_user_id: Optional[uuid.UUID] = None,
                      concerned_leader_id: Optional[uuid.UUID] = None) -> uuid.UUID:
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
        owner_user_id=owner_user_id,
        concerned_leader_id=concerned_leader_id,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row.id


# FR7 — per-account submission rate limit. Counts every Complaint row this
# account has created (including rejected ones), not just valid submissions:
# a spam/gibberish stream that's rejected every time still costs a gatekeeper
# call and a DB write, so it must count too, or the limit is trivially
# bypassed by staying rejected. Checked once per turn, before any LLM call,
# so a blocked account doesn't burn a gatekeeper call it's not going to get
# credit for anyway.
_HOURLY_LIMIT = 3
_DAILY_LIMIT = 10


def check_rate_limit(session: Session, owner_user_id: Optional[uuid.UUID]) -> Optional[str]:
    """Returns a citizen-facing message if the account is rate-limited, else None."""
    if owner_user_id is None:
        return None  # no verified identity to rate-limit against (shouldn't happen — /intake requires auth)

    now = datetime.now(timezone.utc)
    hourly = session.exec(
        select(Complaint.id).where(Complaint.owner_user_id == owner_user_id, Complaint.created_at >= now - timedelta(hours=1))
    ).all()
    if len(hourly) >= _HOURLY_LIMIT:
        return f"You've reached the limit of {_HOURLY_LIMIT} submissions per hour. Please try again later."

    daily = session.exec(
        select(Complaint.id).where(Complaint.owner_user_id == owner_user_id, Complaint.created_at >= now - timedelta(days=1))
    ).all()
    if len(daily) >= _DAILY_LIMIT:
        return f"You've reached the limit of {_DAILY_LIMIT} submissions per day. Please try again tomorrow."

    return None


@dataclass
class PendingQuestion:
    """
    Returned by _prepare_turn when the turn resolves to "ask the citizen one
    more thing" — everything needed to compose that reply, but not yet
    composed. Exists so process_turn (non-streaming) and stream_turn_reply
    (FR15, streaming) can share all the decision logic above this point and
    only diverge on how the actual reply text gets generated and delivered.
    """
    question_key: str
    need: str
    language_name: str
    detected_lang: str
    new_message_english: str
    transcript_blob: str
    dialogue_state: DialogueState
    submission_type: Optional[str]


def _prepare_turn(payload: ChatMessageRequest, session: Session, background_tasks=None,
                   owner_user_id: Optional[uuid.UUID] = None):
    """
    Handles exactly one citizen message. Stateless across HTTP calls — the
    frontend resends the full turn history each time (already
    English-normalized from prior responses), plus `submission_type_hint`
    (the one small piece of client-held state that lets the relatively
    expensive 7-way gatekeeper call run once per conversation, not every
    turn). `owner_user_id` is the verified logged-in citizen's Supabase auth
    id (set by the /intake route from the session cookie, never from the
    request body) and is stamped onto every Complaint row this turn creates.

    Returns either a final ChatTurnResponse (rate_limited/rejected/submitted
    — nothing further to compose), or a PendingQuestion for the caller to
    turn into a reply (see process_turn / stream_turn_reply below).
    """
    detected_lang = detect_language(payload.new_message)
    new_message_english = (
        translate_to_english(payload.new_message, detected_lang)
        if detected_lang in ("hi", "mr") else payload.new_message
    )

    rate_limit_message = check_rate_limit(session, owner_user_id)
    if rate_limit_message:
        return ChatTurnResponse(
            kind="rate_limited",
            detected_language=detected_lang,
            new_message_english=new_message_english,
            rate_limit_message=rate_limit_message,
        )

    # `concerned_leader_id` comes from the request body (the FR9 dropdown), and
    # `complaint.concerned_leader_id` is a real FK to `leader.id` — so a stale
    # or tampered id would only fail at INSERT time, several LLM calls later,
    # as an IntegrityError that surfaces to the citizen as a 500 and throws
    # away the entire conversation. Verified up front instead: an unknown id is
    # dropped (the submission is still recorded — NFR7's "never silently
    # dropped" — just unrouted) and logged loudly, since the only realistic
    # cause is a deleted leader row or a hand-crafted request.
    if payload.concerned_leader_id is not None:
        if session.get(Leader, payload.concerned_leader_id) is None:
            logger.warning(
                f"Unknown concerned_leader_id={payload.concerned_leader_id} on intake turn; "
                "recording the submission without a leader assignment"
            )
            payload.concerned_leader_id = None

    # Phase 9 load test finding: SQLAlchemy keeps a Session's connection
    # checked out from the pool for the whole transaction it auto-began on
    # check_rate_limit's SELECT above — including however long the LLM calls
    # below block (gatekeeper, dialogue manager, up to ~13s each on retries).
    # With pool_size=5/max_overflow=0, a burst of 20-50 concurrent citizens
    # exhausted the pool in ~30s and every 6th+ concurrent turn failed with
    # sqlalchemy.exc.TimeoutError (confirmed live against the deployed VM).
    # There is no pending write yet, so rollback() is a free, side-effect-free
    # way to release the connection back to the pool for the LLM-heavy
    # remainder of this turn; `session` re-acquires one automatically the
    # next time it's actually used (a rejection or the final stub insert).
    session.rollback()

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
            # Both providers exhausted (call_llm walks the whole chain before
            # returning None) — an honest "try again later", not a guess.
            return _service_unavailable(detected_lang, new_message_english)
        elif gk.label in _HARD_REJECT_LABELS:
            row_id = _insert_rejected(
                new_message_english, gk.label,
                f"{payload.citizen_first_name}", payload.citizen_phone,
                payload.citizen_last_name, session, owner_user_id, payload.concerned_leader_id,
            )
            log_stage(logger, row_id, "gatekeeper", "rejected", reason=gk.label)
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

    transcript_blob = _build_transcript_blob(
        payload.history, new_message_english,
        known_city=payload.citizen_city, known_pincode=payload.citizen_pincode,
    )

    try:
        dialogue_state = run_dialogue_manager(transcript_blob)
    except Exception as e:
        logger.error(f"Dialogue manager exception: {e}")
        dialogue_state = None

    if dialogue_state is None:
        # Both providers exhausted on this call too — same honest stop as
        # the turn-1 gatekeeper case above, rather than a heuristic guess.
        return _service_unavailable(detected_lang, new_message_english)

    next_action = decide_next_action(dialogue_state, payload.history, vagueness_mode,
                                      known_pincode=payload.citizen_pincode)

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
                payload.citizen_last_name, session, owner_user_id, payload.concerned_leader_id,
            )
            log_stage(logger, row_id, "gatekeeper_recheck", "rejected", reason=gk2.label)
            return ChatTurnResponse(
                kind="rejected", detected_language=detected_lang, new_message_english=new_message_english,
                rejection_reason=gk2.label, complaint_id=row_id,
            )

        # Default to "complaint" if still ambiguous after a second look —
        # never silently drop a submission just because its type is unclear.
        submission_type = "suggestion" if (gk2 and gk2.label == "valid_suggestion") else "complaint"
        vagueness_mode = False
        next_action = decide_next_action(dialogue_state, payload.history, vagueness_mode=False,
                                          known_pincode=payload.citizen_pincode)

    if next_action.kind == "cannot_proceed":
        row_id = _insert_rejected(
            transcript_blob, next_action.giveup_reason,
            payload.citizen_first_name, payload.citizen_phone,
            payload.citizen_last_name, session, owner_user_id, payload.concerned_leader_id,
        )
        log_stage(logger, row_id, "dialogue", "rejected", reason=next_action.giveup_reason)
        return ChatTurnResponse(
            kind="rejected", detected_language=detected_lang, new_message_english=new_message_english,
            rejection_reason=next_action.giveup_reason, complaint_id=row_id,
        )

    if next_action.kind != "ready":
        question_key = next_action.kind
        return PendingQuestion(
            question_key=question_key,
            need=_NEED_BY_QUESTION_KEY.get(question_key, question_key),
            language_name=_LANGUAGE_NAMES.get(detected_lang, "English"),
            detected_lang=detected_lang,
            new_message_english=new_message_english,
            transcript_blob=transcript_blob,
            dialogue_state=dialogue_state,
            submission_type=submission_type,
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
        owner_user_id=owner_user_id,
        concerned_leader_id=payload.concerned_leader_id,
        created_at=now,
        updated_at=now,
    )
    if payload.concerned_leader_id is None:
        # Every leader-facing query filters on concerned_leader_id, so an
        # unassigned row is accepted and stored but will not appear on any
        # dashboard. The UI requires a selection (FR9), so reaching here means
        # a direct API call or a stale client — worth surfacing in Cloud
        # Logging rather than letting the submission quietly go nowhere.
        logger.warning(f"[id={stub_id}] Submission accepted with no concerned_leader_id — it will not appear on any leader dashboard")

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


def _question_response(pq: "PendingQuestion", question_en: str, question_localized: str) -> ChatTurnResponse:
    return ChatTurnResponse(
        kind="question",
        detected_language=pq.detected_lang,
        new_message_english=pq.new_message_english,
        question_key=pq.question_key,
        question_text=question_localized,
        question_text_english=question_en,
        slots_so_far=LocationSlotsOut(
            address=pq.dialogue_state.location_address,
            area=pq.dialogue_state.location_area,
            pincode=pq.dialogue_state.location_pincode,
        ),
        submission_type_hint=pq.submission_type,
    )


def process_turn(payload: ChatMessageRequest, session: Session, background_tasks=None,
                  owner_user_id: Optional[uuid.UUID] = None) -> ChatTurnResponse:
    """Non-streaming entry point — unchanged behavior from before FR15."""
    result = _prepare_turn(payload, session, background_tasks, owner_user_id)
    if isinstance(result, ChatTurnResponse):
        return result

    pq: PendingQuestion = result
    try:
        composed = run_reply_composer(pq.transcript_blob, pq.need, pq.language_name)
    except Exception as e:
        logger.error(f"Reply composer exception: {e}")
        composed = None

    if composed:
        question_en, question_localized = composed.reply_english, composed.reply_localized
    else:
        # Both providers exhausted on the reply-composer call — honest stop,
        # same as the earlier gatekeeper/dialogue-manager checks.
        return _service_unavailable(pq.detected_lang, pq.new_message_english)

    return _question_response(pq, question_en, question_localized)


def stream_turn_reply(payload: ChatMessageRequest, session: Session, background_tasks=None,
                       owner_user_id: Optional[uuid.UUID] = None) -> "Iterator[str]":
    """
    FR15 — SSE entry point for POST /intake/message/stream. Shares all
    decision logic with process_turn via _prepare_turn; only the reply-text
    step differs. Yields pre-formatted SSE lines directly so intake.py can
    just pass them through to a StreamingResponse.

    Non-English replies (Hindi/Marathi) deliberately do NOT stream — they go
    through the exact same non-streaming ComposedReply path as process_turn,
    sent as a single "final" event, so translation quality stays exactly
    what the existing eval harness already validated. Only English replies
    get real token-by-token streaming. See MVP_roadmap.md Phase 4.
    """
    result = _prepare_turn(payload, session, background_tasks, owner_user_id)

    if isinstance(result, ChatTurnResponse):
        yield f"event: final\ndata: {result.model_dump_json()}\n\n"
        return

    pq: PendingQuestion = result

    if pq.detected_lang != "en":
        try:
            composed = run_reply_composer(pq.transcript_blob, pq.need, pq.language_name)
        except Exception as e:
            logger.error(f"Reply composer exception: {e}")
            composed = None
        if composed:
            question_en, question_localized = composed.reply_english, composed.reply_localized
            yield f"event: final\ndata: {_question_response(pq, question_en, question_localized).model_dump_json()}\n\n"
        else:
            yield f"event: final\ndata: {_service_unavailable(pq.detected_lang, pq.new_message_english).model_dump_json()}\n\n"
        return

    full_text = ""
    try:
        for chunk in stream_reply_composer(pq.transcript_blob, pq.need):
            full_text += chunk
            yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"
    except Exception as e:
        logger.error(f"Streaming reply composer exception: {e}")

    # Partial text (failed partway through, after emitting something) is used
    # as-is rather than discarded — better than nothing, and a retry can't
    # resume a stream cleanly mid-sentence. Nothing streamed at all means
    # every provider failed before emitting a single chunk — an honest stop,
    # not a static template standing in for the LLM's answer.
    if full_text.strip():
        final_text = full_text.strip()
        yield f"event: final\ndata: {_question_response(pq, final_text, final_text).model_dump_json()}\n\n"
    else:
        yield f"event: final\ndata: {_service_unavailable(pq.detected_lang, pq.new_message_english).model_dump_json()}\n\n"


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


def resume_stuck_pipelines():
    """
    Job durability (NFR7): called once at app startup. A complaint stuck in
    `pending`/`processing` means the process died mid-finalize (VM restart,
    crash) before the background task finished — every field the finalize
    pipeline needs is already on that row (raw_text, submission_type,
    citizen_*, location_*), so it can just be re-run from scratch rather than
    needing a separate resumable-job queue. Each stuck row runs in its own
    thread so a slow/stuck one can't block the others or delay app startup.
    """
    from threading import Thread
    from app.db.session import engine

    with Session(engine) as session:
        stuck = session.exec(
            select(Complaint).where(Complaint.pipeline_status.in_([PipelineStatus.pending, PipelineStatus.processing]))
        ).all()

    if not stuck:
        return

    logger.warning(f"Resuming {len(stuck)} complaint(s) stuck in pending/processing from a prior run")
    for row in stuck:
        Thread(
            target=_run_finalize_and_update,
            args=(row.id, row.raw_text, row.submission_type.value,
                  row.citizen_name, row.citizen_phone, row.citizen_last_name,
                  row.location_address, row.location_area, row.location_pincode),
            daemon=True,
        ).start()
