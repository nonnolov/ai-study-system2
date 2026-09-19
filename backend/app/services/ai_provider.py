from abc import ABC, abstractmethod
import json
import re

import requests

from app.core.config import settings


class AIProvider(ABC):
    @abstractmethod
    def generate_mcq(self, topic_name: str, summary: str, excerpt: str) -> list[dict]:
        raise NotImplementedError


class MockAIProvider(AIProvider):
    def generate_mcq(self, topic_name: str, summary: str, excerpt: str) -> list[dict]:
        base = summary or excerpt or topic_name
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
                    "source_excerpt": excerpt[:400],
                }
            )
        return questions


class OpenAICompatibleProvider(AIProvider):
    def generate_mcq(self, topic_name: str, summary: str, excerpt: str) -> list[dict]:
        if not settings.ai_api_key or not settings.ai_base_url:
            return MockAIProvider().generate_mcq(topic_name, summary, excerpt)
        prompt = (
            "Generate 4 multiple-choice questions grounded only in the source material. "
            "Do not invent facts. Do not copy sentences verbatim. "
            "Return strict JSON as an array of objects with keys: question_text, choices (array of 4 strings), correct_answer (A/B/C/D), explanation, source_excerpt. "
            f"Topic: {topic_name}\nSummary: {summary}\nSource excerpt: {excerpt}"
        )
        try:
            response = requests.post(
                f"{settings.ai_base_url.rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": "You generate grounded study questions."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return MockAIProvider().generate_mcq(topic_name, summary, excerpt)


def get_ai_provider() -> AIProvider:
    if settings.ai_provider.lower() == "openai":
        return OpenAICompatibleProvider()
    return MockAIProvider()
