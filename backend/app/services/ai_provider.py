from abc import ABC, abstractmethod
import base64
import json
import logging
import re

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    @abstractmethod
    def generate_mcq(self, topic_name: str, summary: str, evidence: list[str]) -> list[dict]:
        raise NotImplementedError

    def extract_handwriting(self, image_bytes: bytes, printed_text: str, page_number: int, retry_reason: str | None = None) -> str:
        return ""


class MockAIProvider(AIProvider):
    def generate_mcq(self, topic_name: str, summary: str, evidence: list[str]) -> list[dict]:
        base = " ".join(evidence) or summary or topic_name
        keywords = [w for w in re.findall(r"[A-Za-z0-9]+", base) if len(w) > 4][:4]
        focus = keywords[0] if keywords else topic_name
        questions = []
        correct_cycle = ["A", "B", "C", "D"]
        for idx in range(4):
            correct = correct_cycle[idx % 4]
            options = {
                "A": f"{focus} is the main idea",
                "B": f"{focus} is unrelated detail",
                "C": f"{focus} is only a definition",
                "D": f"{focus} is a distractor concept",
            }
            questions.append(
                {
                    "question_text": f"Which statement best matches the topic '{topic_name}'?",
                    "choices": [options["A"], options["B"], options["C"], options["D"]],
                    "correct_answer": correct,
                    "explanation": f"This question is based on the extracted material about {topic_name}.",
                    "source_excerpt": evidence[0] if evidence else summary[:400],
                }
            )
        return questions


class OpenAICompatibleProvider(AIProvider):
    def _post_chat(self, messages: list[dict], model: str | None = None) -> str | None:
        if not settings.ai_api_key or not settings.ai_base_url:
            return None
        response = requests.post(
            f"{settings.ai_base_url.rstrip('/')}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
            json={
                "model": model or settings.handwriting_ocr_model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 3000,
            },
            timeout=60,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def generate_mcq(self, topic_name: str, summary: str, evidence: list[str]) -> list[dict]:
        if not settings.ai_api_key or not settings.ai_base_url:
            return MockAIProvider().generate_mcq(topic_name, summary, evidence)
        evidence_text = "\n\n".join(evidence)
        prompt = (
            "Generate 4 multiple-choice questions grounded ONLY in the supplied PDF evidence. "
            "Use ONLY the evidence. Do not invent facts. Do not copy sentences verbatim. "
            "If the evidence is insufficient for a valid question, return fewer questions rather than inventing one. "
            "Return strict JSON as an array of objects with keys: question_text, choices (array of 4 strings), correct_answer (A/B/C/D), explanation, source_excerpt. "
            f"Topic: {topic_name}\nSummary: {summary}\nPDF evidence:\n{evidence_text}"
        )
        try:
            content = self._post_chat(
                [
                    {"role": "system", "content": "You generate grounded study questions using only provided evidence."},
                    {"role": "user", "content": prompt},
                ],
                model="gpt-4o-mini",
            )
            if content:
                data = json.loads(content)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return MockAIProvider().generate_mcq(topic_name, summary, evidence)

    def extract_handwriting(self, image_bytes: bytes, printed_text: str, page_number: int, retry_reason: str | None = None) -> str:
        if not settings.handwriting_ocr_enabled or not settings.ai_api_key or not settings.ai_base_url:
            return ""
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        prompt = (
            f"Page {page_number} may contain handwritten content or annotations. "
            "Transcribe the entire visible handwriting exactly as written, preserving reading order. "
            "Preserve English spelling, Thai characters, line breaks, and visible word boundaries. "
            "Do not summarize, normalize, autocorrect, translate, or invent missing text. "
            "Ignore printed text already extracted by pypdf. "
            "Reconstruct broken character spacing only when the visual evidence clearly shows one word. "
            "If a character cannot be determined, use [unclear]. "
            "Do not stop early; transcribe the full handwritten sentence or block."
        )
        if retry_reason:
            prompt += f" Retry reason: {retry_reason}. Be stricter, more literal, and complete."
        try:
            logger.info("handwriting_ocr page=%s retry=%s", page_number, bool(retry_reason))
            content = self._post_chat(
                [
                    {"role": "system", "content": "You extract handwritten study notes from page images."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"{prompt}\nPrinted text already extracted:\n{printed_text}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                        ],
                    },
                ],
                model=settings.handwriting_ocr_model,
            )
            return content.strip() if content else ""
        except Exception:
            return ""


def get_ai_provider() -> AIProvider:
    if settings.ai_provider.lower() == "openai":
        return OpenAICompatibleProvider()
    return MockAIProvider()
