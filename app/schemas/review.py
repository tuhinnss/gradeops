"""Human-in-the-loop review schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import ReviewStatus
from app.schemas.evaluation import QuestionResult


class QuestionOverride(BaseModel):
    question: str
    marks_awarded: float
    justification: str | None = None


class ReviewActionRequest(BaseModel):
    action: str = Field(description="approve | reject | override")
    notes: str | None = None
    overrides: list[QuestionOverride] = Field(default_factory=list)


class ReviewAuditItem(BaseModel):
    id: UUID
    action: str
    question: str | None
    old_marks: float | None
    new_marks: float | None
    notes: str | None
    created_at: str | None


class SubmissionReviewResponse(BaseModel):
    submission_id: UUID
    student_id: str
    review_status: ReviewStatus
    reviewer_notes: str | None
    results: list[QuestionResult]
    total: float
    max_total: float
    audit_history: list[ReviewAuditItem] = Field(default_factory=list)
