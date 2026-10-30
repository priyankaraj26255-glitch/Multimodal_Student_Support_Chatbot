from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..database import get_db
from ..models import DocumentChunk, UploadedFile, User, utcnow
from ..ratelimit import ai_limiter
from ..schemas import FileOut, OCRIn, TextIn
from ..security import get_current_user
from ..services import documents, images, ocr, retention, retrieval, storage
from .conversations import get_owned_conversation

settings = get_settings()
router = APIRouter(prefix="/files", tags=["files"])
MB = 1024 * 1024
SUPPORTED = "Images: JPG, PNG, WEBP, GIF, BMP. Documents: PDF, DOCX, TXT, MD, CSV."


def classify(filename: str, data: bytes) -> str | None:
    if images.looks_like_image(data):
        return "image"
    ext = Path(filename).suffix.lower()
    if data[:5] == b"%PDF-" or (ext == ".docx" and data[:2] == b"PK") or ext in (".txt", ".md", ".csv"):
        return "document"
    return None


def get_owned_file(db: Session, user: User, file_id: str) -> UploadedFile:
    f = db.get(UploadedFile, file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(404, "File not found.")
    return f


@router.post("/upload", response_model=FileOut, status_code=201, dependencies=[Depends(ai_limiter)])
async def upload(file: UploadFile = File(...), conversation_id: str | None = Form(None),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = await storage.read_limited(file, max(settings.max_doc_mb, settings.max_image_mb) * MB)
    name = storage.safe_filename(file.filename)
    kind = classify(name, data)
    if kind is None:
        raise HTTPException(415, f"Unsupported file type. {SUPPORTED} (HEIC/HEIF is not supported – convert to JPG/PNG.)")
    if kind == "image" and len(data) > settings.max_image_mb * MB:
        raise HTTPException(413, f"Image too large. The maximum is {settings.max_image_mb} MB.")
    if kind == "document" and len(data) > settings.max_doc_mb * MB:
        raise HTTPException(413, f"Document too large. The maximum is {settings.max_doc_mb} MB.")
    if conversation_id:
        get_owned_conversation(db, user, conversation_id)
    used = db.scalar(select(func.coalesce(func.sum(UploadedFile.size_bytes), 0)).where(UploadedFile.user_id == user.id))
    if used + len(data) > settings.user_storage_mb * MB:
        raise HTTPException(413, "Storage quota reached. Delete some old files or conversations and try again.")
    expires = utcnow() + timedelta(days=settings.file_retention_days) if settings.file_retention_days > 0 else None

    path = None
    try:
        if kind == "image":
            try:
                out, mime, _, _ = await run_in_threadpool(images.process_image, data)
            except images.ImageError as e:
                raise HTTPException(422, str(e))
            path = storage.store_bytes(user.id, out, ".png" if mime == "image/png" else ".jpg")
            rec = UploadedFile(user_id=user.id, conversation_id=conversation_id, kind="image", filename=name,
                               mime_type=mime, size_bytes=len(out), storage_path=path, expires_at=expires)
            db.add(rec)
            db.commit()
            return FileOut.from_model(rec)
        try:
            ext = await run_in_threadpool(documents.extract_document, name, data)
        except documents.DocumentError as e:
            raise HTTPException(422, str(e))
        path = storage.store_bytes(user.id, data, Path(name).suffix.lower() or ".bin")
        rec = UploadedFile(user_id=user.id, conversation_id=conversation_id, kind="document", filename=name,
                           mime_type=ext.mime, size_bytes=len(data), storage_path=path,
                           page_count=ext.page_count, extracted_text=ext.marked_text,
                           warning=" ".join(ext.warnings) or None, expires_at=expires)
        rec.chunks = [DocumentChunk(user_id=user.id, page=p, chunk_index=i, text=t)
                      for p, i, t in documents.chunk_pages(ext.pages)]
        db.add(rec)
        db.commit()
        await retrieval.embed_file(db, rec)
        return FileOut.from_model(rec)
    except HTTPException:
        if path:
            storage.delete_stored(path)
        raise
    except Exception:
        db.rollback()
        if path:
            storage.delete_stored(path)
        raise


@router.get("/{file_id}/content")
def content(file_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = get_owned_file(db, user, file_id)
    if not Path(f.storage_path).exists():
        raise HTTPException(404, "The file is no longer stored (it may have expired).")
    if f.kind == "image":
        return FileResponse(f.storage_path, media_type=f.mime_type)
    return FileResponse(f.storage_path, media_type="application/octet-stream", filename=f.filename)


@router.get("/{file_id}/text")
def get_text(file_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = get_owned_file(db, user, file_id)
    return {"filename": f.filename, "kind": f.kind, "editable": f.kind == "image",
            "text": (f.extracted_text or "")[:200000]}


@router.put("/{file_id}/text", response_model=FileOut)
def save_text(file_id: str, data: TextIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = get_owned_file(db, user, file_id)
    if f.kind != "image":
        raise HTTPException(400, "Only extracted image text can be edited.")
    f.extracted_text = data.text.strip() or None
    db.commit()
    return FileOut.from_model(f)


@router.post("/{file_id}/ocr", dependencies=[Depends(ai_limiter)])
async def run_file_ocr(file_id: str, data: OCRIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    f = get_owned_file(db, user, file_id)
    if f.kind != "image":
        raise HTTPException(400, "OCR can only be run on images. Scanned PDFs are OCR'd automatically on upload.")
    try:
        res = await ocr.run_ocr(storage.read_stored(f.storage_path), f.mime_type, data.engine)
    except ocr.OCRError as e:
        raise HTTPException(422, str(e))
    f.extracted_text = res.text
    db.commit()
    return {"text": res.text, "engine": res.engine, "confidence": res.confidence, "warnings": res.warnings}


@router.delete("/{file_id}", status_code=204)
def delete_file(file_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = get_owned_file(db, user, file_id)
    retention.delete_files(db, [f])
    db.commit()
