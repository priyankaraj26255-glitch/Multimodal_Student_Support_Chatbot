from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation, Message, User, UserPreference, utcnow
from ..schemas import (ConversationCreate, ConversationDetail, ConversationOut,
                       ConversationUpdate, MessageOut)
from ..security import get_current_user
from ..services import retention

router = APIRouter(prefix="/conversations", tags=["conversations"])


def get_owned_conversation(db: Session, user: User, conv_id: str) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if not conv or conv.user_id != user.id:  # 404 (not 403) so ids can't be probed
        raise HTTPException(404, "Conversation not found.")
    return conv


@router.get("", response_model=list[ConversationOut])
def list_conversations(q: str | None = None, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if q and q.strip():
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        in_msgs = select(Message.conversation_id).where(Message.content.ilike(like, escape="\\"))
        stmt = stmt.where(or_(Conversation.title.ilike(like, escape="\\"), Conversation.id.in_(in_msgs)))
    return db.scalars(stmt.order_by(Conversation.updated_at.desc()).limit(100)).all()


@router.post("", response_model=ConversationOut, status_code=201)
def create_conversation(data: ConversationCreate, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    prefs = db.get(UserPreference, user.id)
    conv = Conversation(user_id=user.id, title=data.title,
                        language=data.language or (prefs.language if prefs else "auto"))
    db.add(conv)
    db.commit()
    return conv


@router.get("/{conv_id}", response_model=ConversationDetail)
def get_conversation(conv_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = get_owned_conversation(db, user, conv_id)
    return ConversationDetail(id=conv.id, title=conv.title, language=conv.language,
                              created_at=conv.created_at, updated_at=conv.updated_at,
                              messages=[MessageOut.from_model(m) for m in conv.messages])


@router.patch("/{conv_id}", response_model=ConversationOut)
def update_conversation(conv_id: str, data: ConversationUpdate, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    conv = get_owned_conversation(db, user, conv_id)
    if data.title is not None:
        conv.title = data.title.strip() or conv.title
    if data.language is not None:
        conv.language = data.language
    conv.updated_at = utcnow()
    db.commit()
    return conv


@router.delete("/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = get_owned_conversation(db, user, conv_id)
    retention.delete_conversation(db, conv)
    db.commit()
