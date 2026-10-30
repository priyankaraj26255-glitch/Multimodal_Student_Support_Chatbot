from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import UploadedFile, User
from ..ratelimit import ai_limiter
from ..schemas import DocGenerateIn, DocQueryIn
from ..security import get_current_user
from ..services import llm, prompts, retrieval, routing

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(ai_limiter)])


def _owned_docs(db: Session, user: User, ids: list[str]) -> list[UploadedFile]:
    ids = list(dict.fromkeys(ids))
    docs = list(db.scalars(select(UploadedFile).where(
        UploadedFile.id.in_(ids), UploadedFile.user_id == user.id, UploadedFile.kind == "document")))
    if len(docs) != len(ids):
        raise HTTPException(404, "One or more documents were not found.")
    return docs


@router.post("/query")
async def query(data: DocQueryIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Non-streaming RAG: retrieve passages, answer with citations, say so when not found."""
    docs = _owned_docs(db, user, data.file_ids)
    hits = await retrieval.search(db, user.id, [d.id for d in docs], data.question, k=6)
    if not hits:
        return {"answer": "I couldn't find anything relevant to this question in the selected documents.",
                "sources": [], "found": False}
    system = prompts.build_system(data.language, routing.Route())
    answer = await llm.complete([
        {"role": "system", "content": system},
        {"role": "system", "content": "Retrieved passages (cite using the label in parentheses):\n\n" + retrieval.format_hits(hits)},
        {"role": "user", "content": data.question}])
    return {"answer": answer, "sources": retrieval.dedupe_sources(hits), "found": True}


@router.post("/generate")
async def generate(data: DocGenerateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Summaries, quizzes, flashcards, study notes and multi-document comparison."""
    docs = _owned_docs(db, user, data.file_ids)
    if data.mode == "compare" and len(docs) < 2:
        raise HTTPException(400, "Select at least two documents to compare.")
    body, sources = await retrieval.broad_context(docs)
    route = routing.Route(mode=data.mode)
    content = await llm.complete([
        {"role": "system", "content": prompts.build_system(data.language, route)},
        {"role": "system", "content": "Document content:\n\n" + body},
        {"role": "user", "content": f"Perform the task: {data.mode}."}])
    return {"content": content, "sources": sources}
