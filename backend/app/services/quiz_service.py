from collections import defaultdict
from datetime import datetime
import re

from sqlalchemy.orm import Session

from app import models
from app.services.ai_provider import get_ai_provider

MAX_REGEN_ATTEMPTS = 2


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _evidence_chunks(topic: models.Topic) -> list[str]:
    chunks: list[str] = []
    if topic.section and topic.section.content:
        chunks.append(topic.section.content.strip())
    if topic.summary and topic.summary not in chunks:
        chunks.append(topic.summary.strip())
    return [chunk for chunk in chunks if chunk]


def _extract_question_evidence(evidence: list[str], question_text: str, choices: list[str]) -> str:
    haystack = "\n".join(evidence)
    tokens = [token for token in re.findall(r"[A-Za-z0-9]{4,}", question_text) if token.lower() not in {"which", "statement", "best", "matches", "topic"}]
    tokens.extend(token for choice in choices for token in re.findall(r"[A-Za-z0-9]{4,}", choice))
    for token in tokens:
        pattern = re.compile(re.escape(token), re.IGNORECASE)
        match = pattern.search(haystack)
        if match:
            start = max(0, match.start() - 80)
            end = min(len(haystack), match.end() + 160)
            return haystack[start:end].strip()
    return evidence[0][:400] if evidence else ""


def _is_supported(question_text: str, choices: list[str], correct_answer: str, source_excerpt: str, evidence: list[str]) -> bool:
    if not question_text.strip() or len(choices) != 4 or correct_answer not in {"A", "B", "C", "D"}:
        return False
    if not source_excerpt.strip() or source_excerpt.strip() not in "\n".join(evidence):
        return False
    normalized_evidence = _normalize(" ".join(evidence))
    normalized_excerpt = _normalize(source_excerpt)
    if normalized_excerpt not in normalized_evidence:
        return False
    return len({choice.strip() for choice in choices if choice.strip()}) == 4


def generate_questions(db: Session, document: models.Document) -> int:
    provider = get_ai_provider()
    count = 0
    for topic in document.topics:
        evidence = _evidence_chunks(topic)
        if not evidence:
            continue
        generated = []
        attempts = 0
        while attempts <= MAX_REGEN_ATTEMPTS and len(generated) < 4:
            attempts += 1
            candidates = provider.generate_mcq(topic.name, topic.summary, evidence)
            for item in candidates:
                question_text = (item.get("question_text") or "").strip()
                choices = item.get("choices") or []
                correct_answer = (item.get("correct_answer") or "").strip()
                explanation = (item.get("explanation") or "").strip()
                source_excerpt = (item.get("source_excerpt") or "").strip() or _extract_question_evidence(evidence, question_text, choices)
                if not _is_supported(question_text, choices, correct_answer, source_excerpt, evidence):
                    continue
                generated.append(
                    {
                        "question_text": question_text,
                        "choices": choices,
                        "correct_answer": correct_answer,
                        "explanation": explanation[:240],
                        "source_excerpt": source_excerpt,
                    }
                )
                if len(generated) >= 4:
                    break
            if len(generated) < 4 and attempts > MAX_REGEN_ATTEMPTS:
                break
        for item in generated:
            question = models.Question(
                document_id=document.id,
                topic_id=topic.id,
                question_text=item["question_text"],
                choices_json=item["choices"],
                correct_answer=item["correct_answer"],
                explanation=item["explanation"],
                source_excerpt=item["source_excerpt"],
                difficulty="medium",
            )
            db.add(question)
            count += 1
    db.commit()
    return count


def grade_attempt(db: Session, attempt: models.QuizAttempt, answers: list[dict]) -> dict:
    question_map = {q.id: q for q in db.query(models.Question).filter(models.Question.document_id == attempt.document_id).all()}
    topic_correct = defaultdict(int)
    topic_total = defaultdict(int)
    score = 0
    for answer in answers:
        question = question_map.get(answer["question_id"])
        if not question:
            continue
        is_correct = answer["selected_answer"] == question.correct_answer
        awarded = 1 if is_correct else 0
        score += awarded
        topic_total[question.topic_id] += 1
        if is_correct:
            topic_correct[question.topic_id] += 1
        db.add(models.QuizAnswer(
            attempt_id=attempt.id,
            question_id=question.id,
            selected_answer=answer["selected_answer"],
            is_correct=is_correct,
            score_awarded=awarded,
        ))
    total = len(question_map)
    attempt.score = score
    attempt.total_questions = total
    attempt.completed = True
    attempt.completed_at = datetime.utcnow()
    db.commit()

    weak_topics = []
    recommendations = []
    for topic in db.query(models.Topic).filter(models.Topic.document_id == attempt.document_id).all():
        total_q = topic_total.get(topic.id, 0)
        correct_q = topic_correct.get(topic.id, 0)
        accuracy = (correct_q / total_q) if total_q else 0.0
        weakness = "high" if accuracy < 0.5 else "medium" if accuracy < 0.8 else "low"
        perf = models.TopicPerformance(topic_id=topic.id, accuracy_rate=accuracy, weakness_level=weakness, last_practiced_at=datetime.utcnow())
        db.add(perf)
        if weakness != "low":
            weak_topics.append(topic.name)
            recommendations.append(f"Review {topic.name} again and focus on the summarized points from the PDF.")
    db.add(models.Recommendation(document_id=attempt.document_id, topic_id=None, recommendation_text="Revisit weak topics before retaking the quiz.", priority=1))
    for topic_name in weak_topics:
        db.add(models.Recommendation(document_id=attempt.document_id, topic_id=None, recommendation_text=f"Spend more time on {topic_name} and practice the related concepts.", priority=2))
    db.commit()

    return {"score": score, "total_questions": total, "weak_topics": weak_topics, "recommendations": recommendations}
