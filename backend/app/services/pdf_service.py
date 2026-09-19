from pathlib import Path
from io import BytesIO

from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium

from app.core.config import settings
from app.services.ai_provider import get_ai_provider


def save_upload(file_bytes: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(file_bytes)


def _page_needs_handwriting(page_text: str) -> bool:
    compact = page_text.strip()
    if len(compact) < 30:
        return True
    alpha = sum(1 for ch in compact if ch.isalpha())
    return alpha < 20


def _render_page_to_png_bytes(pdf_path: Path, page_index: int) -> bytes:
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[page_index]
    bitmap = page.render(scale=2.0).to_pil()
    buffer = BytesIO()
    bitmap.save(buffer, format="PNG")
    return buffer.getvalue()


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    provider = get_ai_provider()
    text_parts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        page_parts: list[str] = []
        if extracted.strip():
            page_parts.append(extracted.strip())
        if settings.handwriting_ocr_enabled and _page_needs_handwriting(extracted):
            try:
                image_bytes = _render_page_to_png_bytes(pdf_path, page_number - 1)
                handwriting = provider.extract_handwriting(image_bytes, extracted, page_number)
                if handwriting.strip():
                    page_parts.append(handwriting.strip())
            except Exception:
                pass
        if page_parts:
            text_parts.append("\n".join(page_parts))
    return "\n\n".join(text_parts).strip()
