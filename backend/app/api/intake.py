from fastapi import APIRouter, Depends, BackgroundTasks
from sqlmodel import Session

from app.db.session import get_session
from app.models.schemas import ChatMessageRequest, ChatTurnResponse
from app.pipeline.orchestrator import process_turn

router = APIRouter(prefix="/intake", tags=["Intake"])


@router.post("/message", response_model=ChatTurnResponse)
def post_chat_message(
    payload: ChatMessageRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    return process_turn(payload, session, background_tasks)
