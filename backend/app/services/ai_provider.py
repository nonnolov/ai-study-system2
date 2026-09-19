from abc import ABC, abstractmethod
import re


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
            questions.append({
                "question_text": f"Which statement best matches the topic '{topic_name}'?",
                "choices": [options["A"], options["B"], options["C"], options["D"]],
                "correct_answer": correct,
                "explanation": f"This question is based on the extracted material about {topic_name}.",
                "source_excerpt": excerpt[:400],
            })
        return questions


def get_ai_provider() -> AIProvider:
    return MockAIProvider()
