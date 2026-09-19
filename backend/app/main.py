from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app import models
from app.schemas import DocumentOut, ProcessResponse, RecommendationOut, StartQuizResponse, SubmitQuizRequest, SubmitQuizResponse, TopicOut, UploadResponse
from app.services.pdf_service import extract_text_from_pdf, save_upload
from app.services.quiz_service import generate_questions, grade_attempt
from app.services.topic_service import extract_topics_from_sections, split_into_sections

Base.metadata.create_all(bind=engine)
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def db_session():
    return SessionLocal()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF file")
    upload_dir = Path(settings.upload_dir)
    filename = f"{uuid4()}-{file.filename}"
    path = upload_dir / filename
    save_upload(content, path)
    db = db_session()
    document = models.Document(title=file.filename.rsplit(".", 1)[0], filename=file.filename, storage_path=str(path), status="uploaded")
    db.add(document)
    db.commit()
    db.refresh(document)
    db.close()
    return UploadResponse(document_id=document.id, status=document.status)


@app.post("/documents/{document_id}/process", response_model=ProcessResponse)
def process_document(document_id: int):
    db = db_session()
    document = db.get(models.Document, document_id)
    if not document:
        db.close()
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        document.status = "processing"
        db.commit()
        text = extract_text_from_pdf(Path(document.storage_path))
        document.extracted_text = text
        sections = split_into_sections(text)
        for section in sections:
            db.add(models.DocumentSection(document_id=document.id, section_order=section.order, title=section.title, content=section.content))
        db.commit()
        db.refresh(document)
        topics = extract_topics_from_sections(sections)
        for idx, topic in enumerate(topics):
            section = db.query(models.DocumentSection).filter_by(document_id=document.id, section_order=idx + 1).first()
            db.add(models.Topic(document_id=document.id, section_id=section.id if section else None, name=topic["name"], summary=topic["summary"], confidence_score=topic["confidence_score"]))
        db.commit()
        document.status = "ready"
        db.commit()
        questions_created = generate_questions(db, document)
        topics_created = len(topics)
        db.close()
        return ProcessResponse(document_id=document_id, status="ready", topics_created=topics_created, questions_created=questions_created)
    except Exception as exc:
        document.status = "failed"
        db.commit()
        db.close()
        raise HTTPException(status_code=500, detail=f"Processing failed: {exc}")


@app.get("/documents", response_model=list[DocumentOut])
def list_documents():
    db = db_session()
    docs = db.query(models.Document).order_by(models.Document.created_at.desc()).all()
    db.close()
    return docs


@app.get("/documents/{document_id}/topics", response_model=list[TopicOut])
def get_topics(document_id: int):
    db = db_session()
    topics = db.query(models.Topic).filter(models.Topic.document_id == document_id).all()
    db.close()
    return topics


@app.get("/documents/{document_id}/quiz", response_model=StartQuizResponse)
def start_quiz(document_id: int):
    db = db_session()
    document = db.get(models.Document, document_id)
    if not document:
        db.close()
        raise HTTPException(status_code=404, detail="Document not found")
    questions = db.query(models.Question).filter(models.Question.document_id == document_id).all()
    attempt = models.QuizAttempt(document_id=document_id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    payload = []
    topic_map = {t.id: t.name for t in db.query(models.Topic).filter(models.Topic.document_id == document_id).all()}
    for q in questions:
        payload.append({"id": q.id, "topic_id": q.topic_id, "question_text": q.question_text, "choices": q.choices_json, "correct_answer": None, "explanation": None, "source_excerpt": q.source_excerpt, "topic_name": topic_map.get(q.topic_id, "Topic")})
    db.close()
    return {"attempt_id": attempt.id, "document_id": document_id, "questions": payload}


@app.post("/quizzes/{attempt_id}/submit", response_model=SubmitQuizResponse)
def submit_quiz(attempt_id: int, request: SubmitQuizRequest):
    db = db_session()
    attempt = db.get(models.QuizAttempt, attempt_id)
    if not attempt:
        db.close()
        raise HTTPException(status_code=404, detail="Attempt not found")
    result = grade_attempt(db, attempt, [item.model_dump() for item in request.answers])
    recs = db.query(models.Recommendation).filter(models.Recommendation.document_id == attempt.document_id).order_by(models.Recommendation.priority.asc()).all()
    db.close()
    accuracy = result["score"] / result["total_questions"] if result["total_questions"] else 0.0
    return SubmitQuizResponse(attempt_id=attempt_id, score=result["score"], total_questions=result["total_questions"], accuracy=accuracy, weak_topics=result["weak_topics"], recommendations=[r.recommendation_text for r in recs])


@app.get("/documents/{document_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(document_id: int):
    db = db_session()
    recs = db.query(models.Recommendation).filter(models.Recommendation.document_id == document_id).order_by(models.Recommendation.priority.asc()).all()
    db.close()
    return recs
