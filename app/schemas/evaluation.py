"""Evaluation result schemas."""

from uuid import UUID

from pydantic import BaseModel, Field


class QuestionResult(BaseModel):
    question: str
    marks_awarded: float
    max_marks: float
    justification: str
    confidence: float
    is_blank: bool = False
    key_points_matched: list[str] = Field(default_factory=list)
    key_points_missed: list[str] = Field(default_factory=list)
    negative_triggers: list[str] = Field(default_factory=list)


class PlagiarismFlag(BaseModel):
    question: str
    student_id_a: str
    student_id_b: str
    similarity: float
    note: str


class EvaluationResponse(BaseModel):
    submission_id: UUID
    student_id: str
    results: list[QuestionResult]
    total: float
    max_total: float
    plagiarism_flags: list[PlagiarismFlag] = Field(default_factory=list)
    annotated_pdf_url: str | None = None
    review_status: str = "pending"


class EvaluateAllRequest(BaseModel):
    rubric_id: UUID
    submission_ids: list[UUID] | None = None
    run_plagiarism_check: bool = True


class EvaluateAllResponse(BaseModel):
    job_id: UUID | None = None
    status: str = "completed"
    total_processed: int
    success_count: int
    failed_count: int
    current: int = 0
    errors: list[dict] = Field(default_factory=list)
