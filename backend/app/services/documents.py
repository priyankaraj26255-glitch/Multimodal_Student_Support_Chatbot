"""Safe text extraction from PDFs / DOCX / plain text, with page tracking and OCR fallback."""
import io
import re
import zipfile
from dataclasses import dataclass, field

import pymupdf as fitz  # PyMuPDF

from ..config import get_settings
from . import ocr

settings = get_settings()
PAGE_RE = re.compile(r"^\[(?:Page|Section) (\d+)\]$", re.M)
MIME = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain", "md": "text/markdown", "csv": "text/csv",
}


class DocumentError(ValueError):
    pass


@dataclass
class Extracted:
    pages: list[tuple[int, str]]
    mime: str
    kind: str  # pdf | docx | text
    ocr_pages: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def marked_text(self) -> str:
        label = "Page" if self.kind == "pdf" else "Section"
        return "\n\n".join(f"[{label} {p}]\n{t}" for p, t in self.pages)


def _sections(text: str, size: int = 3000) -> list[tuple[int, str]]:
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for p in paras:
        while len(p) > size:  # very long paragraph
            if cur:
                out.append(cur); cur = ""
            out.append(p[:size]); p = p[size:]
        if len(cur) + len(p) > size and cur:
            out.append(cur); cur = ""
        cur = f"{cur}\n\n{p}".strip()
    if cur:
        out.append(cur)
    return [(i + 1, s) for i, s in enumerate(out)]


def _pdf(data: bytes) -> Extracted:
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise DocumentError("This PDF is corrupted or could not be opened.")
    with doc:
        if doc.needs_pass:
            raise DocumentError("This PDF is password-protected. Remove the password and upload it again.")
        if doc.page_count > settings.max_pdf_pages:
            raise DocumentError(f"This PDF has {doc.page_count} pages; the limit is {settings.max_pdf_pages}.")
        pages, ocr_pages, skipped = [], 0, 0
        can_ocr = ocr.tesseract_available()
        for i, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if len(text) < 25:  # likely scanned / image-only page
                if can_ocr and ocr_pages < settings.max_ocr_pages:
                    try:
                        res = ocr.run_tesseract(page.get_pixmap(dpi=200).tobytes("png"))
                        text = res.text or text
                        ocr_pages += 1
                    except Exception:
                        skipped += 1
                elif len(text) == 0:
                    skipped += 1
            if text:
                pages.append((i, text))
    warns = []
    if ocr_pages:
        warns.append(f"OCR was used on {ocr_pages} scanned page(s); text may contain errors.")
    if skipped:
        warns.append(f"{skipped} page(s) had no extractable text"
                     + ("" if can_ocr else " (OCR is not available on the server)") + ".")
    if not pages:
        raise DocumentError("No text could be extracted from this PDF. If it is a scan, enable OCR "
                            "(install Tesseract) or upload clearer pages.")
    return Extracted(pages, MIME["pdf"], "pdf", ocr_pages, warns)


def _docx(data: bytes) -> Extracted:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:  # zip-bomb guard
            if sum(i.file_size for i in z.infolist()) > 120 * 1024 * 1024:
                raise DocumentError("This DOCX file expands to an unsafe size.")
        import docx
        d = docx.Document(io.BytesIO(data))
    except DocumentError:
        raise
    except Exception:
        raise DocumentError("This DOCX file is corrupted or not a valid Word document.")
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    text = "\n\n".join(parts)
    if not text.strip():
        raise DocumentError("No text could be extracted from this document.")
    return Extracted(_sections(text), MIME["docx"], "docx")


def _text(data: bytes, ext: str) -> Extracted:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise DocumentError("This file is not valid UTF-8 text.")
    if "\x00" in text:
        raise DocumentError("This looks like a binary file, not a text document.")
    if not text.strip():
        raise DocumentError("The text file is empty.")
    return Extracted(_sections(text), MIME.get(ext, "text/plain"), "text")


def extract_document(filename: str, data: bytes) -> Extracted:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if data[:5] == b"%PDF-":
        return _pdf(data)
    if data[:2] == b"PK" and ext == "docx":
        return _docx(data)
    if ext in ("txt", "md", "csv"):
        return _text(data, ext)
    raise DocumentError("Unsupported document type. Supported: PDF, DOCX, TXT, MD, CSV.")


def chunk_pages(pages: list[tuple[int, str]], size: int = 1000, overlap: int = 150):
    """Yield (page, chunk_index, text) with paragraph/sentence-aware boundaries."""
    idx = 0
    for page, raw in pages:
        text = re.sub(r"\n{3,}", "\n\n", raw).strip()
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                cut = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end),
                          text.rfind("\n", start, end), text.rfind("।", start, end))
                if cut > start + size * 0.5:
                    end = cut + 1
            piece = text[start:end].strip()
            if piece:
                yield page, idx, piece
                idx += 1
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)


def split_marked(text: str) -> dict[int, str]:
    """Split stored '[Page N]' marked text back into {page: text}."""
    parts = PAGE_RE.split(text or "")
    return {int(parts[i]): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
