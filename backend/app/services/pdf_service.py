from io import BytesIO
from pathlib import Path
import logging
import re
from difflib import SequenceMatcher

from PIL import Image
from pypdf import PdfReader
import pypdfium2 as pdfium

from app.core.config import settings
from app.services.ai_provider import get_ai_provider

logger = logging.getLogger(__name__)


def save_upload(file_bytes: bytes, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(file_bytes)


def _page_needs_handwriting(page_text: str) -> bool:
    compact = page_text.strip()
    if len(compact) < 30:
        return True
    alpha = sum(1 for ch in compact if ch.isalpha())
    return alpha < 20


def _render_page_to_png_bytes(pdf_path: Path, page_index: int, scale: float = 4.5) -> bytes:
    pdf = pdfium.PdfDocument(str(pdf_path))
    page = pdf[page_index]
    bitmap = page.render(scale=scale).to_pil()
    if bitmap.mode not in ("RGB", "RGBA"):
        bitmap = bitmap.convert("RGB")
    if bitmap.mode == "RGBA":
        background = Image.new("RGB", bitmap.size, (255, 255, 255))
        background.paste(bitmap, mask=bitmap.split()[-1])
        bitmap = background
    buffer = BytesIO()
    bitmap.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _normalize_spacing(line: str) -> str:
    line = re.sub(r"(?<=[\u0E00-\u0E7F])\s+(?=[\u0E00-\u0E7F])", "", line)
    line = re.sub(r"(?<=[A-Za-z])\s+(?=[A-Za-z])", " ", line)
    line = re.sub(r"\s+", " ", line)
    return line.strip()


def _split_blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]


def _dedupe_overlapping_blocks(blocks: list[str]) -> list[str]:
    cleaned: list[str] = []
    for block in blocks:
        normalized = _normalize_spacing(block)
        duplicate = False
        for existing in cleaned:
            existing_norm = _normalize_spacing(existing)
            if normalized == existing_norm:
                duplicate = True
                break
            if normalized in existing_norm or existing_norm in normalized:
                duplicate = True
                break
            if SequenceMatcher(None, normalized, existing_norm).ratio() >= 0.88:
                duplicate = True
                break
        if not duplicate:
            cleaned.append(block)
    return cleaned


def _clean_handwriting_text(text: str) -> str:
    blocks = []
    for block in _split_blocks(text):
        lines = []
        last = ""
        for raw_line in block.splitlines():
            line = _normalize_spacing(raw_line)
            if not line:
                continue
            if line == last:
                continue
            lines.append(line)
            last = line
        if lines:
            blocks.append("\n".join(lines).strip())
    blocks = _dedupe_overlapping_blocks(blocks)
    return "\n\n".join(blocks).strip()


def _needs_retry(ocr_text: str, page_text: str) -> str | None:
    if not ocr_text.strip():
        return "empty_transcription"
    if len(ocr_text.strip()) < 20:
        return "too_short"
    if len(page_text.strip()) and len(ocr_text.strip()) < max(60, int(len(page_text.strip()) * 0.7)):
        return "possible_truncation"
    return None


def extract_text_from_pdf(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    provider = get_ai_provider()
    text_parts: list[str] = []
    for page_number, page in enumerate(reader.pages, start=1):
        extracted = page.extract_text() or ""
        page_parts: list[str] = []
        if extracted.strip():
            page_parts.append(extracted.strip())
        handwriting_text = ""
        if settings.handwriting_ocr_enabled and _page_needs_handwriting(extracted):
            try:
                image_bytes = _render_page_to_png_bytes(pdf_path, page_number - 1)
                handwriting_text = _clean_handwriting_text(provider.extract_handwriting(image_bytes, extracted, page_number))
                retry_reason = _needs_retry(handwriting_text, extracted)
                if retry_reason:
                    logger.info("handwriting_ocr_retry page=%s reason=%s", page_number, retry_reason)
                    retry_bytes = _render_page_to_png_bytes(pdf_path, page_number - 1, scale=5.5)
                    retry_text = _clean_handwriting_text(provider.extract_handwriting(retry_bytes, extracted, page_number, retry_reason=retry_reason))
                    if len(retry_text.strip()) >= len(handwriting_text.strip()):
                        handwriting_text = retry_text
                if handwriting_text.strip():
                    if extracted.strip() and handwriting_text.strip() == extracted.strip():
                        handwriting_text = ""
                    elif extracted.strip() and handwriting_text.strip() in extracted.strip():
                        handwriting_text = ""
            except Exception:
                pass
        if handwriting_text.strip():
            page_parts.append(handwriting_text.strip())
        if page_parts:
            text_parts.append("\n".join(page_parts))
    return "\n\n".join(text_parts).strip()
