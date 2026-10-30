"""Embedding-based retrieval (FAISS, numpy fallback) with a keyword fallback so the app
still works when the embeddings API is unavailable."""
import asyncio
import math
import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DocumentChunk, UploadedFile
from . import documents, llm

try:
    import faiss
except ImportError:  # pragma: no cover
    faiss = None

MIN_SCORE = 0.12


@dataclass
class Hit:
    file_id: str
    filename: str
    page: int
    label: str
    text: str
    score: float

    def source(self) -> dict:
        return {"file_id": self.file_id, "filename": self.filename, "page": self.page,
                "label": self.label, "score": round(float(self.score), 3),
                "snippet": self.text[:240]}


def page_label(f: UploadedFile, page: int) -> str:
    return f"{f.filename}, p. {page}" if f.mime_type == "application/pdf" else f"{f.filename}, section {page}"


async def embed_file(db: Session, file: UploadedFile) -> None:
    chunks = sorted(file.chunks, key=lambda c: c.chunk_index)
    note = None
    if not llm.is_configured():
        note = "Semantic indexing skipped (AI not configured) – keyword search will be used."
    else:
        try:
            vecs = await llm.embed([c.text for c in chunks])
            for c, v in zip(chunks, vecs):
                c.embedding = v.astype(np.float32).tobytes()
        except llm.AIUnavailable:
            note = "Semantic indexing failed – keyword search will be used for this document."
    if note:
        file.warning = f"{file.warning} {note}".strip() if file.warning else note
    db.commit()


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"\w+", s.lower()) if len(t) > 1]


def _keyword_scores(query: str, chunks: list[DocumentChunk]) -> np.ndarray:
    q = set(_tokens(query))
    if not q:
        return np.zeros(len(chunks), dtype=np.float32)
    docs = [set(_tokens(c.text)) for c in chunks]
    df = {t: sum(t in d for d in docs) for t in q}
    n = len(chunks)
    scores = []
    for d in docs:
        s = sum(math.log(1 + n / (1 + df[t])) for t in q if t in d)
        scores.append(s / (len(q) ** 0.5))
    arr = np.asarray(scores, dtype=np.float32)
    return arr / arr.max() if arr.max() > 0 else arr


async def search(db: Session, user_id: int, file_ids: list[str], query: str, k: int = 6) -> list[Hit]:
    """Ownership is enforced here: only chunks of the user's own files are ever searched."""
    files = {f.id: f for f in db.scalars(select(UploadedFile).where(
        UploadedFile.id.in_(file_ids), UploadedFile.user_id == user_id, UploadedFile.kind == "document"))}
    if not files:
        return []
    chunks = list(db.scalars(select(DocumentChunk).where(
        DocumentChunk.file_id.in_(list(files)), DocumentChunk.user_id == user_id)))
    if not chunks:
        return []
    scores = None
    if llm.is_configured() and all(c.embedding for c in chunks):
        try:
            q = (await llm.embed([query]))[0]
            mat = np.vstack([np.frombuffer(c.embedding, dtype=np.float32) for c in chunks])
            if faiss is not None:
                index = faiss.IndexFlatIP(mat.shape[1])
                index.add(mat)
                d, i = index.search(q[None, :], min(k, len(chunks)))
                scores = np.zeros(len(chunks), dtype=np.float32)
                scores[i[0]] = d[0]
                scores[scores == 0] = -1
            else:
                scores = mat @ q
        except llm.AIUnavailable:
            scores = None
    if scores is None:
        scores = _keyword_scores(query, chunks)
    order = np.argsort(-scores)[:k]
    hits = []
    for idx in order:
        if scores[idx] < MIN_SCORE:
            continue
        c = chunks[idx]
        f = files[c.file_id]
        hits.append(Hit(f.id, f.filename, c.page, page_label(f, c.page), c.text, float(scores[idx])))
    return hits


def format_hits(hits: list[Hit]) -> str:
    return "\n\n".join(f"[{i}] ({h.label})\n{h.text}" for i, h in enumerate(hits, 1))


def dedupe_sources(hits: list[Hit]) -> list[dict]:
    seen, out = set(), []
    for h in hits:
        key = (h.file_id, h.page)
        if key not in seen:
            seen.add(key)
            out.append(h.source())
    return out


async def _condense(name: str, text: str, share: int) -> str:
    window = 14000
    wins = [text[i:i + window] for i in range(0, len(text), window)]
    sampled = len(wins) > 12
    if sampled:
        step = len(wins) / 12
        wins = [wins[int(i * step)] for i in range(12)]
    sem = asyncio.Semaphore(4)

    async def one(w: str) -> str:
        async with sem:
            return await llm.complete([
                {"role": "system", "content": "Condense the following document excerpt faithfully. Keep key facts, "
                 "figures, definitions and names. Keep the [Page N]/[Section N] markers next to the facts they "
                 f"support. Aim for about {max(300, share // len(wins))} characters. Do not add anything new."},
                {"role": "user", "content": w}])
    parts = await asyncio.gather(*[one(w) for w in wins])
    out = "\n\n".join(parts)
    if sampled:
        out = "(Note: this long document was sampled; coverage is partial.)\n\n" + out
    return out


async def broad_context(docs: list[UploadedFile], budget: int = 48000) -> tuple[str, list[dict]]:
    """Whole-document context for summaries/quizzes/comparisons (map-reduce when too long)."""
    share = budget // max(1, len(docs))
    blocks, sources = [], []
    for d in docs:
        text = d.extracted_text or ""
        if len(text) > share:
            text = await _condense(d.filename, text, share)
        blocks.append(f"### Document: {d.filename}\n{text}")
        sources.append({"file_id": d.id, "filename": d.filename, "page": None, "label": d.filename,
                        "score": None, "snippet": ""})
    return "\n\n".join(blocks), sources


def get_page_text(f: UploadedFile, page: int) -> str:
    return documents.split_marked(f.extracted_text or "").get(page, "")
