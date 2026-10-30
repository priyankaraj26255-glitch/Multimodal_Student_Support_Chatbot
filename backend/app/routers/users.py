from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, UserPreference
from ..schemas import PreferencesIO
from ..security import get_current_user
from ..services import retention

router = APIRouter(tags=["users"])


def _prefs(db: Session, user: User) -> UserPreference:
    p = db.get(UserPreference, user.id)
    if not p:
        p = UserPreference(user_id=user.id)
        db.add(p)
        db.flush()
    return p


@router.get("/preferences", response_model=PreferencesIO)
def get_preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _prefs(db, user)


@router.put("/preferences", response_model=PreferencesIO)
def put_preferences(data: PreferencesIO, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = _prefs(db, user)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    if not p.personalization_enabled:
        p.about_me = ""  # opt-out clears the stored personal notes
    db.commit()
    return p


@router.delete("/me/history", status_code=204)
def delete_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete all conversations, messages, uploaded files and embeddings."""
    retention.purge_user(db, user, delete_account=False)


@router.delete("/me", status_code=204)
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    retention.purge_user(db, user, delete_account=True)
