from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app import models
from app.services.ai_provider import get_ai_provider


def generate_questions(db: Session, document: models.Document) -> int:
    provider = get_ai_provider()
    count = 0
    for topic in document.topics:
        excerpt = topic.summary
        generated = provider.generate_mcq(topic.name, topic.summary, excerpt)
        for item in generated:
            choices = item["choices"]
            if len(choices) != 4:
                continue
            question = models.Question(
                document_id=document.id,
                topic_id=topic.id,
                question_text=item["question_text"],
                choices_json=choices,
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
