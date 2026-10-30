"""Orchestrates one assistant turn: routing -> context building (RAG / vision / OCR text) ->
streaming generation with tool calling -> persistence. Yields Server-Sent Events."""
import asyncio
import json
import logging

from sqlalchemy import select

from ..config import get_settings
from ..database import SessionLocal
from ..models import Conversation, Message, UploadedFile, UserPreference, utcnow
from . import images as imgsvc
from . import llm, ocr as ocrsvc, prompts, retrieval, routing, storage

settings = get_settings()
log = logging.getLogger(__name__)

HISTORY_KEEP = 12
SUMMARIZE_AFTER = 24
MAX_IMAGES = 4


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _tool(name: str, desc: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


DOC_TOOLS = [
    _tool("search_documents", "Search the user's uploaded documents for passages relevant to a query. "
          "Use it when the passages already provided are insufficient.",
          {"query": {"type": "string"}}, ["query"]),
    _tool("get_page", "Get the full text of one page/section of an uploaded document.",
          {"file_name": {"type": "string"}, "page": {"type": "integer"}}, ["file_name", "page"]),
]
IMAGE_TOOLS = [_tool("ocr_image", "Run OCR on an uploaded image to extract its text.",
                     {"file_name": {"type": "string"}}, ["file_name"])]


class TurnContext:
    def __init__(self, user_id: int, doc_ids: list[str], image_ids: list[str]):
        self.user_id, self.doc_ids, self.image_ids = user_id, doc_ids, image_ids
        self.sources: list[dict] = []

    def add_sources(self, new: list[dict]) -> None:
        keys = {(s["file_id"], s.get("page")) for s in self.sources}
        for s in new:
            if (s["file_id"], s.get("page")) not in keys:
                self.sources.append(s)


async def _run_tool(ctx: TurnContext, name: str, args_json: str) -> str:
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        return "Invalid tool arguments."
    with SessionLocal() as db:
        if name == "search_documents":
            hits = await retrieval.search(db, ctx.user_id, ctx.doc_ids, str(args.get("query", ""))[:500], k=5)
            ctx.add_sources(retrieval.dedupe_sources(hits))
            return retrieval.format_hits(hits) or "No relevant passages found."
        wanted = str(args.get("file_name", "")).lower()
        ids = ctx.doc_ids if name == "get_page" else ctx.image_ids
        files = [f for f in db.scalars(select(UploadedFile).where(
            UploadedFile.id.in_(ids), UploadedFile.user_id == ctx.user_id))]
        f = next((x for x in files if x.filename.lower() == wanted), None) or \
            next((x for x in files if wanted and wanted in x.filename.lower()), None)
        if not f:
            return "File not found. Available: " + ", ".join(x.filename for x in files)
        if name == "get_page":
            page = int(args.get("page", 0) or 0)
            text = retrieval.get_page_text(f, page)
            if text:
                ctx.add_sources([{"file_id": f.id, "filename": f.filename, "page": page,
                                  "label": retrieval.page_label(f, page), "score": None, "snippet": text[:240]}])
            return text or f"Page {page} not found (document has {f.page_count} pages)."
        if name == "ocr_image":
            try:
                res = await ocrsvc.run_ocr(storage.read_stored(f.storage_path), f.mime_type)
                return res.text
            except ocrsvc.OCRError as e:
                return f"OCR failed: {e}"
    return "Unknown tool."


def _persist_assistant(conv_id: str, content: str, sources: list[dict]) -> str | None:
    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        if not conv:
            return None
        m = Message(conversation_id=conv_id, role="assistant", content=content, sources=sources or None)
        db.add(m)
        conv.updated_at = utcnow()
        db.commit()
        return m.id


async def maybe_summarize(conv_id: str) -> None:
    """Rolling summary of older messages so long conversations stay within context."""
    with SessionLocal() as db:
        conv = db.get(Conversation, conv_id)
        if not conv:
            return
        msgs = list(conv.messages)
        if len(msgs) <= SUMMARIZE_AFTER:
            return
        older = msgs[:-HISTORY_KEEP]
        new = older[conv.summary_upto:]
        if len(new) < 6:
            return
        transcript = "\n".join(f"{m.role}: {m.content[:1500]}" for m in new)
        prompt = (f"Previous summary:\n{conv.summary or '(none)'}\n\nNew messages:\n{transcript}\n\n"
                  "Update the summary in under 250 words. Keep facts, decisions, names, and open questions.")
        try:
            conv.summary = await llm.complete([
                {"role": "system", "content": "You maintain a concise running summary of a conversation."},
                {"role": "user", "content": prompt}])
            conv.summary_upto = len(older)
            db.commit()
        except llm.AIUnavailable:
            log.info("summarization skipped")


async def stream_reply(conv_id: str, user_id: int, user_msg_id: str, input_mode: str = "text"):
    full, ctx = "", None
    try:
        # ---------- Phase 1: build everything we need (short-lived DB session) ----------
        with SessionLocal() as db:
            conv = db.get(Conversation, conv_id)
            user_msg = db.get(Message, user_msg_id)
            prefs = db.get(UserPreference, user_id)
            all_msgs = list(conv.messages)
            idx = next(i for i, m in enumerate(all_msgs) if m.id == user_msg_id)
            files = list(db.scalars(select(UploadedFile).where(
                UploadedFile.conversation_id == conv_id, UploadedFile.user_id == user_id,
                UploadedFile.status == "ready")))
            docs = [f for f in files if f.kind == "document"]
            cur_images = [f for f in files if f.kind == "image" and f.message_id == user_msg_id]
            recent_ids = {m.id for m in all_msgs[max(0, idx - 6):idx + 1]}
            imgs = cur_images or [f for f in sorted(files, key=lambda x: x.created_at, reverse=True)
                                  if f.kind == "image" and f.message_id in recent_ids]
            imgs = imgs[:MAX_IMAGES]
            text = user_msg.content
            route = routing.plan_route(text, images=len(imgs), docs=len(docs), input_mode=input_mode)
            language = conv.language if conv.language != "auto" else (prefs.language if prefs else "auto")

            sources, context_msg, hits = [], None, []
            if route.mode in ("summary", "quiz", "flashcards", "notes", "compare") and docs:
                try:
                    body, sources = await retrieval.broad_context(docs)
                    context_msg = f"Document content for this task (cite as [file name, p. N] when markers allow):\n\n{body}"
                except llm.AIUnavailable:
                    raise
            elif route.needs_retrieval:
                query = text
                if len(text.split()) < 6 and idx > 0:  # short follow-up: add previous user turn for context
                    prev = next((m.content for m in reversed(all_msgs[:idx]) if m.role == "user"), "")
                    query = f"{prev} {text}"[:800]
                hits = await retrieval.search(db, user_id, [d.id for d in docs], query, k=6)
                sources = retrieval.dedupe_sources(hits)
                if hits:
                    context_msg = ("Retrieved passages from the user's uploaded documents (cite using the label in "
                                   "parentheses):\n\n" + retrieval.format_hits(hits))
                else:
                    context_msg = ("No passages in the uploaded documents matched this question. If the question "
                                   "is about the documents, tell the user the answer could not be found in them.")

            ocr_notes = [f"Text extracted from image '{f.filename}' (OCR, may contain errors):\n{f.extracted_text}"
                         for f in imgs if f.extracted_text]
            notes = [f"'{f.filename}': {f.warning}" for f in files if f.warning and f.message_id]
            personalization = prefs.about_me if (prefs and prefs.personalization_enabled and prefs.about_me) else ""
            system = prompts.build_system(language, route, personalization=personalization,
                                          summary=conv.summary, notes=notes)
            # Merge all system context into a single system message upfront.
            # Gemini collapses all system-role entries into one system_instruction,
            # but keeping them together avoids any ordering issues.
            system_parts = [system]
            if context_msg:
                system_parts.append(context_msg)
            if ocr_notes:
                system_parts.append("\n\n".join(ocr_notes))
            merged_system = "\n\n---\n\n".join(system_parts)

            history = all_msgs[:idx][conv.summary_upto:][-40:]
            messages = [{"role": "system", "content": merged_system}]
            for m in history:
                c = m.content
                if m.role == "user" and m.files:
                    c += "\n\n[Attached: " + ", ".join(f.filename for f in m.files) + "]"
                # Gemini requires strictly alternating user/model turns.
                # Merge consecutive same-role messages to avoid API errors.
                if messages and messages[-1]["role"] == m.role and m.role != "system":
                    messages[-1]["content"] += "\n\n" + c
                else:
                    messages.append({"role": m.role, "content": c})
            if imgs:
                parts = [{"type": "text", "text": text}]
                for f in imgs:
                    parts.append({"type": "text", "text": f"(image: {f.filename})"})
                    parts.append({"type": "image_url", "image_url": {
                        "url": imgsvc.to_data_url(storage.read_stored(f.storage_path), f.mime_type)}})
                messages.append({"role": "user", "content": parts})
            else:
                messages.append({"role": "user", "content": text})

            tools = (DOC_TOOLS if docs else []) + (IMAGE_TOOLS if imgs else [])
            ctx = TurnContext(user_id, [d.id for d in docs], [f.id for f in imgs])
            ctx.add_sources(sources)

        yield sse("meta", {"route": route.to_dict(), "user_message_id": user_msg_id})

        # ---------- Phase 2: stream the model output ----------
        async def runner(name, args):
            return await _run_tool(ctx, name, args)

        async for ev in llm.stream_chat(messages, tools=tools or None, tool_runner=runner):
            if ev["type"] == "token":
                full += ev["text"]
                yield sse("token", {"text": ev["text"]})
            else:
                yield sse("tool", {"name": ev["name"]})

        # ---------- Phase 3: persist ----------
        if not full.strip():
            yield sse("error", {"message": "The model returned an empty response. Please try again."})
            return
        msg_id = _persist_assistant(conv_id, full, ctx.sources)
        yield sse("done", {"message_id": msg_id, "sources": ctx.sources})
        await maybe_summarize(conv_id)
    except llm.AIUnavailable as e:
        if full.strip():
            _persist_assistant(conv_id, full, ctx.sources if ctx else [])
        yield sse("error", {"message": str(e)})
    except (asyncio.CancelledError, GeneratorExit):
        if full.strip():  # user pressed stop: keep what was generated
            _persist_assistant(conv_id, full, ctx.sources if ctx else [])
        raise
    except Exception:
        log.exception("chat turn failed")
        yield sse("error", {"message": "Something went wrong while generating the answer. Please try again."})
