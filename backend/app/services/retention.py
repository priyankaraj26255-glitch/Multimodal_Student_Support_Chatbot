import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Conversation, UploadedFile, User, utcnow
from . import storage

log = logging.getLogger(__name__)


def delete_files(db: Session, files: list[UploadedFile]) -> None:
    for f in files:
        storage.delete_stored(f.storage_path)
        db.delete(f)


def delete_conversation(db: Session, conv: Conversation) -> None:
    files = list(db.scalars(select(UploadedFile).where(UploadedFile.conversation_id == conv.id)))
    delete_files(db, files)
    db.flush()
    db.delete(conv)


def purge_user(db: Session, user: User, delete_account: bool) -> None:
    delete_files(db, list(db.scalars(select(UploadedFile).where(UploadedFile.user_id == user.id))))
    db.flush()
    for conv in list(db.scalars(select(Conversation).where(Conversation.user_id == user.id))):
        db.delete(conv)
    if delete_account:
        db.flush()
        db.delete(user)
    db.commit()


def cleanup_expired_files() -> int:
    with SessionLocal() as db:
        expired = list(db.scalars(select(UploadedFile).where(
            UploadedFile.expires_at.is_not(None), UploadedFile.expires_at < utcnow())))
        delete_files(db, expired)
        db.commit()
        if expired:
            log.info("Retention cleanup removed %d expired file(s)", len(expired))
        return len(expired)
