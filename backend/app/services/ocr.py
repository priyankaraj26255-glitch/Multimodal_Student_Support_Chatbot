import io
import logging
import shutil
from dataclasses import dataclass, field

from PIL import Image, ImageOps

from ..config import get_settings
from . import llm

settings = get_settings()
log = logging.getLogger(__name__)

try:
    import pytesseract
    from pytesseract import Output
except ImportError:  # pragma: no cover
    pytesseract = None


class OCRError(Exception):
    pass


@dataclass
class OCRResult:
    text: str
    engine: str
    confidence: float | None = None
    warnings: list[str] = field(default_factory=list)


def tesseract_available() -> bool:
    return pytesseract is not None and shutil.which("tesseract") is not None


def tesseract_languages() -> list[str]:
    if not tesseract_available():
        return []
    try:
        return pytesseract.get_languages(config="")
    except Exception:
        return []


def _langs() -> str:
    wanted = [l for l in settings.tesseract_langs.split("+") if l]
    have = set(tesseract_languages())
    use = [l for l in wanted if l in have] or (["eng"] if "eng" in have else [])
    return "+".join(use) or "eng"


def run_tesseract(image_bytes: bytes) -> OCRResult:
    if not tesseract_available():
        raise OCRError("Tesseract is not installed on the server.")
    with Image.open(io.BytesIO(image_bytes)) as im:
        im = ImageOps.exif_transpose(im).convert("L")
        im = ImageOps.autocontrast(im)
        if min(im.size) < 1000:
            im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
        d = pytesseract.image_to_data(im, lang=_langs(), output_type=Output.DICT)
    lines: dict[tuple, list[str]] = {}
    confs = []
    for i, word in enumerate(d["text"]):
        word = word.strip()
        if not word:
            continue
        try:
            c = float(d["conf"][i])
        except ValueError:
            c = -1
        if c >= 0:
            confs.append(c)
        lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(word)
    text = "\n".join(" ".join(w) for _, w in sorted(lines.items()))
    conf = sum(confs) / len(confs) if confs else None
    warnings = []
    if conf is not None and conf < 60:
        warnings.append("OCR confidence is low – please review the text carefully.")
    return OCRResult(text=text.strip(), engine="tesseract", confidence=conf, warnings=warnings)


async def run_vision(image_bytes: bytes, mime: str) -> OCRResult:
    from .images import to_data_url
    text = await llm.complete([
        {"role": "system", "content": "You are an OCR engine. Transcribe ALL visible text in the image "
         "exactly as written (printed or handwritten), preserving line breaks and language/script. "
         "Output only the transcription. If there is no legible text, output exactly: [NO TEXT]. "
         "Mark unreadable words as [illegible]."},
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": to_data_url(image_bytes, mime)}}]},
    ])
    text = text.strip()
    if text == "[NO TEXT]":
        text = ""
    return OCRResult(text=text, engine="vision",
                     warnings=["Transcribed by the AI vision model – verify important details."] if text else [])


async def run_ocr(image_bytes: bytes, mime: str, engine: str = "auto") -> OCRResult:
    from starlette.concurrency import run_in_threadpool
    result: OCRResult | None = None
    if engine in ("auto", "tesseract"):
        try:
            result = await run_in_threadpool(run_tesseract, image_bytes)
        except OCRError as e:
            if engine == "tesseract":
                raise
            log.info("tesseract unavailable: %s", e)
        except Exception:
            log.exception("tesseract failed")
            if engine == "tesseract":
                raise OCRError("Tesseract failed to process this image.")
    weak = result is None or len(result.text) < 10 or (result.confidence or 0) < 55
    if engine == "vision" or (engine == "auto" and weak and llm.is_configured()):
        try:
            v = await run_vision(image_bytes, mime)
            if v.text or result is None:
                result = v
        except llm.AIUnavailable as e:
            if engine == "vision" or result is None:
                raise OCRError(str(e))
    if result is None:
        raise OCRError("No OCR engine is available. Install Tesseract or configure GEMINI_API_KEY.")
    if not result.text:
        raise OCRError("No readable text was found. Try a sharper, well-lit, higher-resolution image.")
    return result
