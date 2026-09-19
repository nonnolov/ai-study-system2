from pydantic import BaseModel, Field


class TopicOut(BaseModel):
    id: int
    name: str
    summary: str

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    id: int
    topic_id: int
    question_text: str
    choices: list[str]
    correct_answer: str | None = None
    explanation: str | None = None
    source_excerpt: str
    topic_name: str


class DocumentOut(BaseModel):
    id: int
    title: str
    filename: str
    status: str

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    document_id: int
    status: str


class ProcessResponse(BaseModel):
    document_id: int
    status: str
    topics_created: int
    questions_created: int


class StartQuizResponse(BaseModel):
    attempt_id: int
    document_id: int
    questions: list[QuestionOut]


class SubmitAnswerItem(BaseModel):
    question_id: int
    selected_answer: str = Field(pattern="^[ABCD]$")


class SubmitQuizRequest(BaseModel):
    answers: list[SubmitAnswerItem]


class SubmitQuizResponse(BaseModel):
    attempt_id: int
    score: int
    total_questions: int
    accuracy: float
    weak_topics: list[str]
    recommendations: list[str]


class RecommendationOut(BaseModel):
    id: int
    recommendation_text: str
    priority: int

    class Config:
        from_attributes = True
