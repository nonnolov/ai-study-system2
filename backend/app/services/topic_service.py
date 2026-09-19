import re
from dataclasses import dataclass


@dataclass
class Section:
    title: str
    content: str
    order: int


def split_into_sections(text: str) -> list[Section]:
    chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
    if not chunks:
        return []
    sections: list[Section] = []
    for index, chunk in enumerate(chunks[:8], start=1):
        first_line = chunk.splitlines()[0][:80]
        title = first_line if len(first_line.split()) <= 8 else f"Section {index}"
        sections.append(Section(title=title, content=chunk, order=index))
    return sections


def extract_topics_from_sections(sections: list[Section]) -> list[dict]:
    topics = []
    for section in sections:
        sentences = re.split(r"(?<=[.!?])\s+", section.content)
        summary = " ".join(sentences[:2]).strip()
        summary = summary[:280] if summary else section.content[:280]
        topics.append({"name": section.title, "summary": summary, "confidence_score": 0.75})
    return topics
