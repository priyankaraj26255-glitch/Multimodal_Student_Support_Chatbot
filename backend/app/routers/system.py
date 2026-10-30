from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..services import llm, ocr, retrieval

settings = get_settings()
router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/capabilities")
def capabilities():
    return {
        "ai_configured": llm.is_configured(),
        "chat_model": settings.chat_model,
        "ocr_tesseract": ocr.tesseract_available(),
        "ocr_languages": ocr.tesseract_languages(),
        "faiss": retrieval.faiss is not None,
        "max_image_mb": settings.max_image_mb,
        "max_doc_mb": settings.max_doc_mb,
        "max_audio_mb": settings.max_audio_mb,
        "file_retention_days": settings.file_retention_days,
        "languages": ["auto", "en", "hi", "mr"],
    }
