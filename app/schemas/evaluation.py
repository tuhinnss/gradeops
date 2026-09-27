"""Evaluation result schemas."""

from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel


class CriterionScore(ApiModel):
    """Evidence for one rubric criterion (shown to reviewers next to the AI score)."""

    criterion: str
    kind: Literal["key_point", "partial_rule", "penalty"] = "key_point"
    max_marks: float
    awarded: float
    status: Literal["met", "partial", "missed", "applied", "not_applied"]
    semantic_similarity: float | None = None
    keyword_overlap: float = 0.0


class QuestionResult(ApiModel):
    question: str
    marks_awarded: float
    max_marks: float
    justification: str
    confidence: float
    is_blank: bool = False
    key_points_matched: list[str] = Field(default_factory=list)
    key_points_missed: list[str] = Field(default_factory=list)
    negative_triggers: list[str] = Field(default_factory=list)
    # Additive fields (older stored results simply omit them).
    key_points_partial: list[str] = Field(default_factory=list)
    criteria: list[CriterionScore] = Field(default_factory=list)
    # True when the AI could not assess correctness and a human must grade it.
    requires_manual_grading: bool = False
    # Original AI mark, preserved when a reviewer overrides ``marks_awarded``.
    ai_marks_awarded: float | None = None
    # "semantic" (embedding model) or "lexical" (keyword-only fallback).
    scoring_method: str | None = None
    # Reviewer's explanation when marks were overridden (AI justification is kept).
    reviewer_comment: str | None = None


class PlagiarismFlag(ApiModel):
    question: str
    student_id_a: str
    student_id_b: str
    similarity: float
    note: str
    excerpt_a: str | None = None
    excerpt_b: str | None = None


class EvaluationResponse(ApiModel):
    submission_id: UUID
    student_id: str
    results: list[QuestionResult]
    total: float
    max_total: float
    plagiarism_flags: list[PlagiarismFlag] = Field(default_factory=list)
    annotated_pdf_url: str | None = None
    review_status: str = "pending"


class EvaluateAllRequest(ApiModel):
    rubric_id: UUID
    submission_ids: list[UUID] | None = None
    run_plagiarism_check: bool = True


class EvaluateAllResponse(ApiModel):
    job_id: UUID | None = None
    status: str = "completed"
    total_processed: int
    success_count: int
    failed_count: int
    current: int = 0
    errors: list[dict] = Field(default_factory=list)
