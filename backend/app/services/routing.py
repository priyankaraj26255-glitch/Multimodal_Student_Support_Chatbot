"""Intelligent routing layer: decides which capabilities a request needs.
Deterministic and testable; it never calls a model."""
import re
from dataclasses import asdict, dataclass, field
from typing import Optional

RX = {
    "compare": re.compile(r"\b(compare|comparison|differences? between|contrast|versus|vs\.?)\b|तुलना", re.I),
    "flashcards": re.compile(r"flash ?cards?|फ्लैशकार्ड|फ्लॅशकार्ड", re.I),
    "quiz": re.compile(r"\b(quiz|mcqs?|multiple[- ]choice|test me)\b|क्विज़?|प्रश्नमंजुषा", re.I),
    "notes": re.compile(r"\b(study notes|revision notes|make notes|notes (?:on|from|of))\b|नोट्स|टिपणे", re.I),
    "summary": re.compile(r"\b(summar(?:y|ise|ize|ies)|tl;?dr|overview|gist)\b|सारांश|संक्षेप|सारांश", re.I),
    "ocr": re.compile(r"\b(ocr|extract (?:the )?text|read (?:the )?text|transcribe|handwrit\w*|what does it say)\b|हस्तलिखित|हस्तलिखित", re.I),
}


@dataclass
class Route:
    intents: list[str] = field(default_factory=lambda: ["text"])
    mode: Optional[str] = None  # summary|quiz|flashcards|notes|compare
    needs_vision: bool = False
    needs_retrieval: bool = False
    needs_ocr: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def plan_route(text: str, *, images: int = 0, docs: int = 0, input_mode: str = "text") -> Route:
    r = Route()
    if input_mode == "voice":
        r.intents.append("speech")
    if images:
        r.intents.append("image")
        r.needs_vision = True
        if RX["ocr"].search(text):
            r.intents.append("ocr")
            r.needs_ocr = True
    if docs:
        r.intents.append("document")
    mode = None
    if docs >= 2 and RX["compare"].search(text):
        mode = "compare"
    elif RX["flashcards"].search(text):
        mode = "flashcards"
    elif RX["quiz"].search(text):
        mode = "quiz"
    elif RX["notes"].search(text):
        mode = "notes"
    elif docs and RX["summary"].search(text):
        mode = "summary"
    if mode in ("summary", "compare") and not docs:
        mode = None
    r.mode = mode
    r.needs_retrieval = bool(docs) and mode is None
    if mode:
        r.intents.append(mode)
    return r
