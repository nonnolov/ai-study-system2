from pathlib import Path
from typing import Any

from pypdf import PdfReader

from app.services.ai_provider import get_ai_provider


def save_upload(file_bytes: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(file_bytes)


def _page_needs_handwriting(page_text: str) -> bool:
    compact = page_text.strip()
    if not compact:
        return True
    if len(compact) < 40:
        return True
    alpha = sum(1 for ch in compact if ch.isalpha())
    if alpha < 20:
        return True
    return False


def _page_image_bytes(page: Any) -> bytes | None:
    images = getattr(page, "images", None)
    if not images:
        return None
    best: bytes | None = None
    best_size = -1
    for image in images:
        data = getattr(image, "data", None)
        if not data:
            continue
        size = len(data)
        if size > best_size:
            best = data
            best_size = size
    return best


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    provider = get_ai_provider()
    text_parts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        page_parts: list[str] = []
        if extracted.strip():
            page_parts.append(extracted.strip())

        if _page_needs_handwriting(extracted):
            image_bytes = _page_image_bytes(page)
            if image_bytes:
                handwriting_text = provider.extract_handwriting(image_bytes, extracted, page_number)
                if handwriting_text.strip():
                    handwriting_text = handwriting_text.strip()
                    if extracted.strip() and handwriting_text in extracted.strip():
                        handwriting_text = ""
                    if handwriting_text:
                        page_parts.append(handwriting_text)

        if page_parts:
            text_parts.append("\n".join(page_parts))
    return "\n\n".join(text_parts).strip()