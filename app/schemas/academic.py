"""Course / student / TA / exam / rubric API schemas."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.db.models import (
    CourseStatus,
    EnrollmentStatus,
    ExamStatus,
    ReviewStatus,
    SubmissionStatus,
    UserRole,
)
from app.schemas.batch import BatchJobResponse
from app.schemas.common import ApiModel
from app.schemas.rubric import RubricSchema


class UserSummary(ApiModel):
    id: UUID
    email: str
    full_name: str
    role: UserRole

    model_config = {"from_attributes": True}


# --- Courses ------------------------------------------------------------------------


class CourseCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)
    course_code: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=5000)
    semester: str | None = Field(default=None, max_length=64)
    academic_year: str | None = Field(default=None, max_length=16)

    @field_validator("course_code")
    @classmethod
    def _normalise_code(cls, v: str) -> str:
        return v.strip().upper()


class CourseUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    course_code: str | None = Field(default=None, min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=5000)
    semester: str | None = Field(default=None, max_length=64)
    academic_year: str | None = Field(default=None, max_length=16)
    status: CourseStatus | None = None


class CourseStats(ApiModel):
    student_count: int = 0
    ta_count: int = 0
    exam_count: int = 0
    active_exam_count: int = 0
    submission_count: int = 0
    pending_reviews: int = 0
    escalated: int = 0
    # Mean final score as a percentage of max, over evaluated submissions.
    average_score_pct: float | None = None


class CourseResponse(ApiModel):
    id: UUID
    name: str
    course_code: str
    description: str | None
    semester: str | None
    academic_year: str | None
    status: CourseStatus
    professor: UserSummary
    created_at: datetime | None
    updated_at: datetime | None
    stats: CourseStats


# --- Students -------------------------------------------------------------------------


class StudentIn(ApiModel):
    student_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.\-]+$")
    name: str = Field(default="", max_length=255)
    email: EmailStr | None = None


class StudentImportRequest(ApiModel):
    students: list[StudentIn] = Field(min_length=1, max_length=5000)


class StudentImportResponse(ApiModel):
    created: int
    enrolled: int
    already_enrolled: int
    reactivated: int = 0
    errors: list[str] = Field(default_factory=list)


class StudentResponse(ApiModel):
    id: UUID
    student_id: str
    name: str
    email: str | None
    enrollment_status: EnrollmentStatus
    enrolled_at: datetime | None


# --- TAs ------------------------------------------------------------------------------


class TAAddRequest(ApiModel):
    """Add an existing TA account by email, or create one if a password is given."""

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class ExamRef(ApiModel):
    id: UUID
    name: str


class TAWorkload(ApiModel):
    user: UserSummary
    active: bool
    assigned_exams: list[ExamRef] = Field(default_factory=list)
    # Submissions in the TA's assigned exams that they are eligible to review.
    assigned_submissions: int = 0
    reviewed: int = 0
    pending: int = 0
    escalated: int = 0
    overrides: int = 0


class ExamTAAssign(ApiModel):
    ta_id: UUID


class DistributeRequest(ApiModel):
    ta_ids: list[UUID] | None = None
    # Also re-assign submissions that already have a TA (still awaiting review).
    rebalance: bool = False


class DistributeResponse(ApiModel):
    assigned: dict[str, int]
    total: int


# --- Rubrics --------------------------------------------------------------------------


class RubricSummary(ApiModel):
    id: UUID
    name: str
    source_filename: str
    source_type: str
    question_count: int
    total_marks: float
    created_at: datetime | None
    used_by_exams: list[ExamRef] = Field(default_factory=list)


class RubricDetail(RubricSummary):
    structured_data: RubricSchema


class RubricUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    structured_data: RubricSchema | None = None


class ExamRubricLink(ApiModel):
    rubric_id: UUID


# --- Exams ----------------------------------------------------------------------------

ExamType = Literal["quiz", "midterm", "final", "assignment", "exam", "other"]
ExamStage = Literal[
    "setup", "ai_processing", "ta_review", "professor_approval", "approved", "locked", "published"
]


class ExamCreate(ApiModel):
    course_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    exam_type: ExamType = "exam"
    total_marks: float | None = Field(default=None, gt=0, le=10000)
    exam_date: date | None = None
    rubric_id: UUID | None = None


class ExamUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    exam_type: ExamType | None = None
    total_marks: float | None = Field(default=None, gt=0, le=10000)
    exam_date: date | None = None


class ExamCounts(ApiModel):
    submissions: int = 0
    uploaded: int = 0
    processing: int = 0
    processed: int = 0  # AI evaluation complete
    failed: int = 0
    awaiting_ta: int = 0  # AI_EVALUATED + TA_PENDING
    ta_reviewed: int = 0  # TA_APPROVED + TA_OVERRIDDEN
    escalated: int = 0
    professor_approved: int = 0
    published: int = 0
    needs_manual_grading: int = 0
    integrity_open: int = 0


class ExamResponse(ApiModel):
    id: UUID
    course_id: UUID
    course_code: str
    course_name: str
    name: str
    description: str | None
    exam_type: str
    total_marks: float | None
    exam_date: date | None
    status: ExamStatus
    stage: ExamStage
    rubric: RubricSummary | None
    tas: list[UserSummary] = Field(default_factory=list)
    counts: ExamCounts
    average_score: float | None = None
    max_score: float | None = None
    created_at: datetime | None
    updated_at: datetime | None
    approved_at: datetime | None
    locked_at: datetime | None
    published_at: datetime | None


class ExamAuditItem(ApiModel):
    id: UUID
    action: str
    actor: UserSummary | None
    from_status: str | None
    to_status: str | None
    notes: str | None
    details: dict | None
    created_at: datetime | None


class ExamDetailResponse(ExamResponse):
    latest_job: BatchJobResponse | None = None
    audit: list[ExamAuditItem] = Field(default_factory=list)


class TAExamResponse(ExamResponse):
    my_pending: int = 0
    my_reviewed: int = 0


class EvaluateExamRequest(ApiModel):
    # Re-run AI evaluation on already-evaluated submissions (resets their review).
    reevaluate: bool = False
    run_plagiarism_check: bool = True


# --- Submissions ----------------------------------------------------------------------


class SubmissionRow(ApiModel):
    id: UUID
    exam_id: UUID | None
    student_id: str
    student_name: str | None
    source_filename: str
    status: SubmissionStatus
    review_status: ReviewStatus
    total_marks: float | None
    max_total: float | None
    ai_total_marks: float | None
    ta_total_marks: float | None
    professor_total_marks: float | None
    min_confidence: float | None
    needs_manual_grading: bool
    integrity_open: int = 0
    assigned_ta: UserSummary | None = None
    reviewed_by: UserSummary | None = None
    escalation_reason: str | None = None
    error_message: str | None = None
    created_at: datetime | None
    updated_at: datetime | None


class SubmissionListResponse(ApiModel):
    items: list[SubmissionRow]
    total: int


class MappingItemIn(ApiModel):
    filename: str = Field(min_length=1, max_length=512)
    student_id: str | None = Field(default=None, max_length=128)


class MappingValidateRequest(ApiModel):
    items: list[MappingItemIn] = Field(min_length=1, max_length=2000)


class MappingItemResult(ApiModel):
    filename: str
    student_id: str | None
    student_name: str | None = None
    status: Literal["ok", "not_enrolled", "duplicate_in_upload", "already_submitted", "invalid"]
    message: str | None = None


class MappingValidateResponse(ApiModel):
    items: list[MappingItemResult]
    ok: int
    problems: int


class SubmissionUploadItem(ApiModel):
    id: UUID
    student_id: str
    student_name: str | None
    filename: str


class SubmissionUploadResponse(ApiModel):
    uploaded: list[SubmissionUploadItem]
    failed: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- Finalisation ---------------------------------------------------------------------


class FinalizationSummary(ApiModel):
    exam_id: UUID
    status: ExamStatus
    total: int
    evaluated: int
    not_evaluated: int
    failed: int
    awaiting_ta: int
    ta_reviewed: int
    escalated: int
    professor_approved: int
    published: int
    ta_overrides: int
    professor_overrides: int
    integrity_open: int
    needs_manual_grading: int
    can_approve: bool
    can_lock: bool
    can_publish: bool
    can_reopen: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExamTransitionRequest(ApiModel):
    notes: str | None = Field(default=None, max_length=2000)


class PublishRequest(ExamTransitionRequest):
    acknowledge_integrity_flags: bool = False


class ReopenRequest(ApiModel):
    reason: str = Field(min_length=5, max_length=2000)
