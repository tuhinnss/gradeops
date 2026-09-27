"""Human-in-the-loop review schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.db.models import (
    ExamStatus,
    IntegrityFlagStatus,
    ReviewStatus,
    SubmissionStatus,
)
from app.schemas.academic import UserSummary
from app.schemas.common import ApiModel
from app.schemas.evaluation import CriterionScore, QuestionResult
from app.schemas.rubric import PartialCreditRule

ReviewAction = Literal["approve", "override", "escalate", "resolve", "return_to_ta", "reject"]

EscalationReason = Literal[
    "ambiguous_answer",
    "ocr_unreliable",
    "rubric_unclear",
    "integrity_concern",
    "ai_grading_incorrect",
    "other",
]
ESCALATION_REASON_LABELS: dict[str, str] = {
    "ambiguous_answer": "Ambiguous answer",
    "ocr_unreliable": "OCR unreliable",
    "rubric_unclear": "Rubric unclear",
    "integrity_concern": "Potential integrity issue",
    "ai_grading_incorrect": "AI grading appears incorrect",
    "other": "Other",
    "legacy_rejected": "Rejected (legacy review)",
}


class QuestionOverride(ApiModel):
    question: str = Field(min_length=1, max_length=32)
    marks_awarded: float
    justification: str | None = Field(default=None, max_length=2000)


class ReviewActionRequest(ApiModel):
    """One endpoint for every review decision.

    * ``approve`` — TA: accept the current marks (TA_APPROVED). Professor: sign off
      (PROFESSOR_APPROVED).
    * ``override`` — change marks for one or more questions; ``reason`` required.
    * ``escalate`` (TA) — send to the professor with an ``EscalationReason``.
    * ``resolve`` (professor) — close an escalation, optionally with overrides.
    * ``return_to_ta`` (professor) — send back to the TA queue; ``notes`` required.
    * ``reject`` — legacy alias of ``escalate`` (reason ``ai_grading_incorrect``).
    """

    action: str = Field(description="approve | override | escalate | resolve | return_to_ta | reject")
    notes: str | None = Field(default=None, max_length=5000)
    reason: str | None = Field(default=None, max_length=500)
    overrides: list[QuestionOverride] = Field(default_factory=list, max_length=200)
    # Optimistic concurrency: reject if the status changed since the reviewer loaded it.
    expected_review_status: ReviewStatus | None = None


class ReviewAuditItem(ApiModel):
    id: UUID
    action: str
    question: str | None
    old_marks: float | None
    new_marks: float | None
    notes: str | None
    created_at: str | None
    reason: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    actor_role: str | None = None
    reviewer: UserSummary | None = None


class SubmissionReviewResponse(ApiModel):
    submission_id: UUID
    student_id: str
    review_status: ReviewStatus
    reviewer_notes: str | None
    results: list[QuestionResult]
    total: float
    max_total: float
    audit_history: list[ReviewAuditItem] = Field(default_factory=list)
    exam_id: UUID | None = None
    ai_total: float | None = None
    ta_total: float | None = None
    professor_total: float | None = None
    escalation_reason: str | None = None
    escalation_notes: str | None = None


# --- Review queue ------------------------------------------------------------------------

QueueStatusFilter = Literal["pending", "reviewed", "escalated", "approved", "all"]
QueueSort = Literal["confidence_asc", "confidence_desc", "newest", "oldest"]


class FocusQuestion(ApiModel):
    question: str
    marks_awarded: float
    max_marks: float
    confidence: float
    requires_manual_grading: bool = False


class ReviewQueueItem(ApiModel):
    submission_id: UUID
    student_id: str
    student_name: str | None
    exam_id: UUID | None
    exam_name: str | None
    course_code: str | None
    total: float | None
    ai_total: float | None
    max_total: float | None
    min_confidence: float | None
    focus: FocusQuestion | None
    review_status: ReviewStatus
    needs_manual_grading: bool
    integrity_flags: int = 0
    escalation_reason: str | None = None
    assigned_to_me: bool = False
    updated_at: datetime | None


class ReviewQueueResponse(ApiModel):
    items: list[ReviewQueueItem]
    total: int


# --- Review detail -----------------------------------------------------------------------


class RubricCriteria(ApiModel):
    key_points: list[str] = Field(default_factory=list)
    partial_credit_rules: list[PartialCreditRule] = Field(default_factory=list)
    negative_conditions: list[str] = Field(default_factory=list)


class AnswerRegion(ApiModel):
    text: str
    ocr_confidence: float | None
    page_index: int | None
    bbox: dict | None
    is_blank: bool = False


class ReviewQuestion(ApiModel):
    question: str
    max_marks: float
    marks_awarded: float
    ai_marks_awarded: float | None
    confidence: float
    justification: str
    reviewer_comment: str | None = None
    is_blank: bool
    requires_manual_grading: bool
    scoring_method: str | None
    criteria: list[CriterionScore] = Field(default_factory=list)
    key_points_matched: list[str] = Field(default_factory=list)
    key_points_partial: list[str] = Field(default_factory=list)
    key_points_missed: list[str] = Field(default_factory=list)
    negative_triggers: list[str] = Field(default_factory=list)
    rubric: RubricCriteria
    answer: AnswerRegion | None


class IntegrityFlagBrief(ApiModel):
    id: UUID
    question: str
    similarity: float
    other_student_id: str
    other_submission_id: UUID
    status: IntegrityFlagStatus


class ReviewPermissions(ApiModel):
    can_approve: bool
    can_override: bool
    can_escalate: bool
    can_resolve: bool
    can_return: bool
    read_only_reason: str | None = None


class ReviewNavigation(ApiModel):
    prev_id: UUID | None
    next_id: UUID | None
    # Next submission (wrapping) that still needs this reviewer's decision.
    next_pending_id: UUID | None = None
    position: int | None
    queue_size: int


class ReviewSubmissionInfo(ApiModel):
    id: UUID
    student_id: str
    student_name: str | None
    source_filename: str
    status: SubmissionStatus
    review_status: ReviewStatus
    page_count: int | None
    total: float
    max_total: float
    ai_total: float | None
    ta_total: float | None
    professor_total: float | None
    min_confidence: float | None
    needs_manual_grading: bool
    reviewer_notes: str | None
    escalation_reason: str | None
    escalation_notes: str | None
    escalated_by: UserSummary | None
    escalated_at: datetime | None
    reviewed_by: UserSummary | None
    reviewed_at: datetime | None
    approved_by: UserSummary | None
    approved_at: datetime | None
    assigned_ta: UserSummary | None
    has_annotated_pdf: bool


class ReviewExamInfo(ApiModel):
    id: UUID
    name: str
    status: ExamStatus
    course_code: str
    course_name: str


class ReviewDetailResponse(ApiModel):
    submission: ReviewSubmissionInfo
    exam: ReviewExamInfo | None
    questions: list[ReviewQuestion]
    integrity_flags: list[IntegrityFlagBrief] = Field(default_factory=list)
    audit_history: list[ReviewAuditItem] = Field(default_factory=list)
    permissions: ReviewPermissions
    navigation: ReviewNavigation


# --- History / escalations ----------------------------------------------------------------


class ReviewHistoryItem(ApiModel):
    id: UUID
    submission_id: UUID
    student_id: str
    exam_id: UUID | None
    exam_name: str | None
    course_code: str | None
    action: str
    question: str | None
    old_marks: float | None
    new_marks: float | None
    reason: str | None
    notes: str | None
    from_status: str | None
    to_status: str | None
    created_at: datetime | None


class ReviewHistoryResponse(ApiModel):
    items: list[ReviewHistoryItem]
    total: int


class EscalationResponse(ApiModel):
    submission_id: UUID
    student_id: str
    student_name: str | None
    exam_id: UUID | None
    exam_name: str | None
    course_code: str | None
    escalated_by: UserSummary | None
    reason: str | None
    reason_label: str | None
    notes: str | None
    escalated_at: datetime | None
    ai_score: float | None
    ta_score: float | None
    current_score: float | None
    max_score: float | None
    min_confidence: float | None
    review_status: ReviewStatus
