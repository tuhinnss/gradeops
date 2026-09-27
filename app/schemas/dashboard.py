"""Dashboard, analytics, gradebook and integrity schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.db.models import ExamStatus, IntegrityFlagStatus, ReviewStatus
from app.schemas.academic import ExamResponse, UserSummary
from app.schemas.common import ApiModel


class ActivityItem(ApiModel):
    """One persisted audit event (review or exam-level)."""

    kind: str  # "review" | "exam"
    action: str
    actor: UserSummary | None
    exam_id: UUID | None
    exam_name: str | None
    submission_id: UUID | None = None
    student_id: str | None = None
    question: str | None = None
    old_marks: float | None = None
    new_marks: float | None = None
    notes: str | None = None
    created_at: datetime | None


class ProfessorDashboardResponse(ApiModel):
    active_courses: int
    active_exams: int
    students: int
    submissions: int
    pending_ta_reviews: int
    awaiting_professor_approval: int
    escalated: int
    integrity_flags_open: int
    ready_to_publish: int
    exams: list[ExamResponse] = Field(default_factory=list)
    recent_activity: list[ActivityItem] = Field(default_factory=list)


class TADashboardResponse(ApiModel):
    assigned_exams: int
    pending_reviews: int
    reviewed_today: int
    total_reviewed: int
    overrides: int
    escalations_open: int
    escalations_total: int
    recent_activity: list[ActivityItem] = Field(default_factory=list)


# --- Gradebook ---------------------------------------------------------------------------


class GradebookRow(ApiModel):
    submission_id: UUID | None
    student_id: str
    student_name: str | None
    ai_score: float | None
    ta_score: float | None
    professor_score: float | None
    final_score: float | None
    max_score: float | None
    percentage: float | None
    review_status: ReviewStatus | None
    status_label: str
    integrity_flags: int = 0
    reviewed_by: str | None = None
    approved_by: str | None = None
    overridden: bool = False
    question_scores: dict[str, float] = Field(default_factory=dict)


class GradebookResponse(ApiModel):
    exam_id: UUID
    exam_name: str
    course_code: str
    status: ExamStatus
    max_score: float | None
    questions: list[str]
    rows: list[GradebookRow]
    is_final: bool


# --- Analytics ---------------------------------------------------------------------------


class ScoreSummary(ApiModel):
    count: int
    average: float | None
    median: float | None
    highest: float | None
    lowest: float | None
    std_dev: float | None
    max_total: float | None
    average_pct: float | None


class DistributionBucket(ApiModel):
    label: str
    lower_pct: float
    upper_pct: float
    count: int


class QuestionStats(ApiModel):
    question: str
    max_marks: float
    attempts: int
    average: float
    average_pct: float
    ai_average: float | None
    full_credit_pct: float
    partial_pct: float
    zero_pct: float
    average_confidence: float | None
    overridden: int


class CriterionStats(ApiModel):
    question: str
    criterion: str
    evaluated: int
    missed_rate: float
    partial_rate: float


class ReviewStats(ApiModel):
    ai_evaluated: int
    awaiting_ta: int
    ta_reviewed: int
    escalated: int
    professor_approved: int
    published: int
    ta_override_rate: float | None
    professor_override_rate: float | None
    ai_ta_disagreement_rate: float | None
    ai_ta_mean_abs_diff: float | None


class IntegrityStats(ApiModel):
    open: int
    dismissed: int
    confirmed: int


class StudentScore(ApiModel):
    submission_id: UUID
    student_id: str
    student_name: str | None
    final_score: float | None
    percentage: float | None


class ExamAnalyticsResponse(ApiModel):
    exam_id: UUID
    exam_name: str
    summary: ScoreSummary
    distribution: list[DistributionBucket]
    questions: list[QuestionStats]
    criteria: list[CriterionStats]
    review: ReviewStats
    integrity: IntegrityStats
    # Omitted for TAs (limited analytics).
    students: list[StudentScore] | None = None


class CourseExamSummary(ApiModel):
    exam_id: UUID
    exam_name: str
    status: ExamStatus
    summary: ScoreSummary


class CourseAnalyticsResponse(ApiModel):
    course_id: UUID
    exams: list[CourseExamSummary]
    overall: ScoreSummary


# --- Integrity ---------------------------------------------------------------------------


class IntegritySide(ApiModel):
    submission_id: UUID
    student_id: str
    student_name: str | None
    score: float | None
    excerpt: str | None


class IntegrityFlagResponse(ApiModel):
    id: UUID
    exam_id: UUID
    exam_name: str
    course_code: str
    question: str
    similarity: float
    a: IntegritySide
    b: IntegritySide
    note: str | None
    status: IntegrityFlagStatus
    resolution_notes: str | None
    resolved_by: UserSummary | None
    resolved_at: datetime | None
    created_at: datetime | None


class IntegrityFlagUpdate(ApiModel):
    status: IntegrityFlagStatus
    notes: str | None = Field(default=None, max_length=5000)
