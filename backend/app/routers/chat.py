from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Message, UploadedFile, User, utcnow
from ..ratelimit import ai_limiter
from ..schemas import ChatIn
from ..security import get_current_user
from ..services import chat_engine, llm
from .conversations import get_owned_conversation

router = APIRouter(prefix="/conversations", tags=["chat"], dependencies=[Depends(ai_limiter)])
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"}


def _require_ai():
    if not llm.is_configured():
        raise HTTPException(503, "AI is not configured on the server. Set GEMINI_API_KEY in .env and restart.")


@router.post("/{conv_id}/messages")
def send_message(conv_id: str, data: ChatIn, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Streams the assistant reply as Server-Sent Events (meta, token, tool, done, error)."""
    _require_ai()
    conv = get_owned_conversation(db, user, conv_id)
    ids = list(dict.fromkeys(data.attachment_ids))
    files = []
    if ids:
        files = list(db.scalars(select(UploadedFile).where(
            UploadedFile.id.in_(ids), UploadedFile.user_id == user.id)))
        if len(files) != len(ids):
            raise HTTPException(404, "One or more attachments were not found (they may have expired).")
        if any(f.message_id for f in files):
            raise HTTPException(400, "An attachment was already used in another message.")
    first = not conv.messages
    msg = Message(conversation_id=conv.id, role="user", content=data.content.strip())
    db.add(msg)
    db.flush()
    for f in files:
        f.message_id, f.conversation_id = msg.id, conv.id
    if data.language:
        conv.language = data.language
    if first and conv.title == "New chat":
        conv.title = (data.content.strip().replace("\n", " ")[:60] or "New chat")
    conv.updated_at = utcnow()
    db.commit()
    return StreamingResponse(chat_engine.stream_reply(conv.id, user.id, msg.id, data.input_mode),
                             media_type="text/event-stream", headers=HEADERS)


@router.post("/{conv_id}/regenerate")
def regenerate(conv_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_ai()
    conv = get_owned_conversation(db, user, conv_id)
    msgs = list(conv.messages)
    if msgs and msgs[-1].role == "assistant":
        db.delete(msgs[-1])
        msgs = msgs[:-1]
    if not msgs or msgs[-1].role != "user":
        raise HTTPException(400, "There is no message to regenerate a reply for.")
    db.commit()
    return StreamingResponse(chat_engine.stream_reply(conv.id, user.id, msgs[-1].id),
                             media_type="text/event-stream", headers=HEADERS)
