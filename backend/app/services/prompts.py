from .routing import Route

LANG_NAMES = {"en": "English", "hi": "Hindi (Devanagari script)", "mr": "Marathi (Devanagari script)"}

BASE = """You are a helpful, accurate multimodal AI assistant inside a chat application.
Format answers in Markdown (tables, lists and fenced code blocks with a language tag when useful).

Honesty rules (very important):
- Only say you have seen, read or analysed an attachment if its content is actually provided to you in this
  conversation. If an attachment is missing or could not be processed, say so plainly.
- Never invent facts, quotes, page numbers or citations. Do not claim to have run code, performed actions
  or verified facts that you did not.
- When you use uploaded-document passages, cite them inline like [file name, p. 3] using the labels provided.
- If the user asks about their uploaded documents and the provided passages do not contain the answer, say
  clearly that the answer could not be found in the uploaded documents. You may then offer general knowledge,
  clearly labelled as not coming from the documents.
- For general questions unrelated to attachments, answer normally.
- If a request is ambiguous, ask one short clarifying question.
- Explain complex topics clearly, step by step, with examples when helpful."""

MODES = {
    "summary": "Write a well-structured summary: a 2-3 sentence overview, key points, and notable details. Cite pages/sections where possible.",
    "quiz": "Create a quiz of about 8 multiple-choice questions (A-D). After the questions, give an answer key with a one-line explanation each. Base questions on the provided material when available; cite pages.",
    "flashcards": "Create about 12 flashcards as a Markdown table with columns: # | Question | Answer. Base them on the provided material when available.",
    "notes": "Write organised study notes with headings, definitions, key takeaways and a short revision checklist. Cite pages/sections where possible.",
    "compare": "Compare the documents: give a short overview of each, then a Markdown table of similarities and differences, and a conclusion. Attribute every point to its document.",
}


def build_system(language: str, route: Route, *, personalization: str = "", summary: str = "",
                 notes: list[str] | None = None) -> str:
    parts = [BASE]
    if language in LANG_NAMES:
        parts.append(f"Always reply in {LANG_NAMES[language]}, even if the user writes in another language, unless they "
                     "explicitly ask otherwise. Keep code, file names and proper nouns unchanged.")
    else:
        parts.append("Reply in the language the user writes in. Handle mixed-language messages (e.g. Hinglish) naturally.")
    if route.mode:
        parts.append("Task: " + MODES[route.mode])
    if personalization:
        parts.append("The user opted in to personalization. Background they shared about themselves "
                     f"(use only when relevant):\n{personalization}")
    if summary:
        parts.append(f"Summary of the earlier part of this conversation:\n{summary}")
    if notes:
        parts.append("Attachment notes:\n- " + "\n- ".join(notes))
    return "\n\n".join(parts)
