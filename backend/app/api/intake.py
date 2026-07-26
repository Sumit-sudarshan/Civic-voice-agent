from fastapi import APIRouter, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.db.session import get_session
from app.models.schemas import ChatMessageRequest, ChatTurnResponse
from app.pipeline.orchestrator import process_turn, stream_turn_reply
from app.auth.deps import CurrentUser, get_current_user

router = APIRouter(prefix="/intake", tags=["Intake"])


@router.post("/message", response_model=ChatTurnResponse)
def post_chat_message(
    payload: ChatMessageRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    return process_turn(payload, session, background_tasks, owner_user_id=current_user.id)


@router.post("/message/stream")
def post_chat_message_stream(
    payload: ChatMessageRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    FR15 — same turn as POST /message, delivered as Server-Sent Events so the
    citizen sees the reply appear token-by-token instead of all at once.
    Emits zero or more `event: chunk` frames (English replies only — see
    stream_turn_reply's docstring), then exactly one `event: final` frame
    carrying the complete ChatTurnResponse the frontend needs either way.
    """
    return StreamingResponse(
        stream_turn_reply(payload, session, background_tasks, owner_user_id=current_user.id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
