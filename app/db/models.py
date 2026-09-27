"""SQLAlchemy ORM models.

Academic hierarchy::

    User (professor) ─owns─> Course ─> Exam ─> Rubric
                              │         ├─> ExamTA (explicit TA assignment)
                              │         └─> StudentSubmission ─> ExtractedAnswer
                              ├─> CourseMember (TAs)             ├─> ReviewAudit
                              └─> Enrollment ─> Student          └─> EvaluationLog

Schema changes are managed by Alembic (``alembic/versions``). Enum columns are
native PostgreSQL enums that store the member *names* (e.g. ``TA_APPROVED``).
"""

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    # Fetch server-generated values (created_at/updated_at) with RETURNING on flush,
    # so async code never triggers an implicit lazy load when reading them.
    __mapper_args__ = {"eager_defaults": True}


class UserRole(str, enum.Enum):
    PROFESSOR = "professor"
    TA = "ta"


class SubmissionStatus(str, enum.Enum):
    """Processing status of the answer sheet (OCR / AI pipeline)."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    OCR_COMPLETE = "ocr_complete"
    EVALUATED = "evaluated"
    FAILED = "failed"


class ReviewStatus(str, enum.Enum):
    """Human review lifecycle. An AI grade is never final on its own.

    AI_EVALUATED → (TA_PENDING) → TA_APPROVED | TA_OVERRIDDEN | ESCALATED
    → PROFESSOR_APPROVED → PUBLISHED
    """

    NOT_EVALUATED = "not_evaluated"
    AI_EVALUATED = "ai_evaluated"
    TA_PENDING = "ta_pending"
    TA_APPROVED = "ta_approved"
    TA_OVERRIDDEN = "ta_overridden"
    ESCALATED = "escalated"
    PROFESSOR_APPROVED = "professor_approved"
    PUBLISHED = "published"


# Awaiting a TA decision.
TA_QUEUE_STATUSES = (ReviewStatus.AI_EVALUATED, ReviewStatus.TA_PENDING)
# Reviewed by a TA, awaiting professor approval.
TA_REVIEWED_STATUSES = (ReviewStatus.TA_APPROVED, ReviewStatus.TA_OVERRIDDEN)
# A human (TA or professor) has signed off.
HUMAN_REVIEWED_STATUSES = (
    ReviewStatus.TA_APPROVED,
    ReviewStatus.TA_OVERRIDDEN,
    ReviewStatus.PROFESSOR_APPROVED,
    ReviewStatus.PUBLISHED,
)


class BatchJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CourseStatus(str, enum.Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class EnrollmentStatus(str, enum.Enum):
    ACTIVE = "active"
    DROPPED = "dropped"


class ExamStatus(str, enum.Enum):
    DRAFT = "draft"  # set-up: rubric, roster, uploads
    PROCESSING = "processing"  # OCR + AI evaluation running
    TA_REVIEW = "ta_review"  # AI grades available; human review in progress
    APPROVED = "approved"  # professor approved every submission
    LOCKED = "locked"  # grades frozen
    PUBLISHED = "published"  # released; changes require an explicit reopen


# Exam states in which grades may no longer be changed without reopening.
FROZEN_EXAM_STATUSES = (ExamStatus.LOCKED, ExamStatus.PUBLISHED)


class IntegrityFlagStatus(str, enum.Enum):
    OPEN = "open"  # review required
    DISMISSED = "dismissed"  # professor found no concern
    CONFIRMED = "confirmed"  # professor confirmed a concern


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.TA, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    review_audits: Mapped[list["ReviewAudit"]] = relationship(back_populates="reviewer")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint(
            "professor_id", "course_code", "semester", "academic_year", name="uq_course_offering"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    course_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    semester: Mapped[str | None] = mapped_column(String(64))
    academic_year: Mapped[str | None] = mapped_column(String(16))
    professor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    status: Mapped[CourseStatus] = mapped_column(
        Enum(CourseStatus), default=CourseStatus.ACTIVE, nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    exams: Mapped[list["Exam"]] = relationship(back_populates="course")
    members: Mapped[list["CourseMember"]] = relationship(back_populates="course")


class CourseMember(Base):
    """Course staff other than the owning professor (currently TAs)."""

    __tablename__ = "course_members"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_member"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.TA, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped["Course"] = relationship(back_populates="members")


class Student(Base):
    """A student identified by an institution-wide student ID."""

    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str | None] = mapped_column(String(255))
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "student_id", name="uq_enrollment"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        Enum(EnrollmentStatus), default=EnrollmentStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Professor who uploaded it. NULL only for rows created before ownership existed.
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list["StudentSubmission"]] = relationship(back_populates="rubric")
    batch_jobs: Mapped[list["BatchJob"]] = relationship(back_populates="rubric")


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    exam_type: Mapped[str] = mapped_column(String(32), nullable=False, default="exam")
    total_marks: Mapped[float | None] = mapped_column(Float)
    exam_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[ExamStatus] = mapped_column(
        Enum(ExamStatus), default=ExamStatus.DRAFT, nullable=False, index=True
    )
    rubric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=True, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    course: Mapped["Course"] = relationship(back_populates="exams")
    rubric: Mapped["Rubric | None"] = relationship()


class ExamTA(Base):
    """Explicit TA assignment: a TA only sees exams they are actively assigned to."""

    __tablename__ = "exam_tas"
    __table_args__ = (UniqueConstraint("exam_id", "ta_id", name="uq_exam_ta"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExamAudit(Base):
    """Exam-level audit trail (approve / lock / publish / reopen / …)."""

    __tablename__ = "exam_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    notes: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False, index=True
    )
    exam_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id"), nullable=True, index=True
    )
    status: Mapped[BatchJobStatus] = mapped_column(
        Enum(BatchJobStatus), default=BatchJobStatus.QUEUED, nullable=False, index=True
    )
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    submission_ids: Mapped[list] = mapped_column(JSONB, default=list)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    run_plagiarism: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rubric: Mapped["Rubric"] = relationship(back_populates="batch_jobs")
    submissions: Mapped[list["StudentSubmission"]] = relationship(back_populates="batch_job")


class StudentSubmission(Base):
    __tablename__ = "student_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Student identifier as written on the sheet / used by the legacy API.
    student_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rubric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=True, index=True
    )
    batch_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_jobs.id"), nullable=True, index=True
    )
    # Academic context. NULL for legacy (pre-course) uploads — see README "Migrations".
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=True, index=True
    )
    exam_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id"), nullable=True, index=True
    )
    student_record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=True, index=True
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    # Optional per-submission TA; NULL means any TA assigned to the exam may review.
    assigned_ta_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.UPLOADED, nullable=False, index=True
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.NOT_EVALUATED, nullable=False, index=True
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    # Last TA/professor who reviewed (approve / override).
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Professor sign-off.
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalation_reason: Mapped[str | None] = mapped_column(String(64))
    escalation_notes: Mapped[str | None] = mapped_column(Text)
    escalated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text: Mapped[dict | None] = mapped_column(JSONB)
    evaluation_result: Mapped[dict | None] = mapped_column(JSONB)
    annotated_pdf_path: Mapped[str | None] = mapped_column(String(1024))
    # Current (final) total; per-stage totals below feed the gradebook.
    total_marks: Mapped[float | None] = mapped_column(Float)
    ai_total_marks: Mapped[float | None] = mapped_column(Float)
    ta_total_marks: Mapped[float | None] = mapped_column(Float)
    professor_total_marks: Mapped[float | None] = mapped_column(Float)
    # Lowest per-question AI confidence (queue sorting / filtering).
    min_confidence: Mapped[float | None] = mapped_column(Float, index=True)
    needs_manual_grading: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    plagiarism_score: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rubric: Mapped["Rubric | None"] = relationship(back_populates="submissions")
    batch_job: Mapped["BatchJob | None"] = relationship(back_populates="submissions")
    exam: Mapped["Exam | None"] = relationship()
    answers: Mapped[list["ExtractedAnswer"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    evaluation_logs: Mapped[list["EvaluationLog"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )
    review_audits: Mapped[list["ReviewAudit"]] = relationship(
        back_populates="submission", cascade="all, delete-orphan"
    )


class ExtractedAnswer(Base):
    __tablename__ = "extracted_answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("student_submissions.id"), nullable=False, index=True
    )
    question_number: Mapped[str] = mapped_column(String(32), nullable=False)
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    is_blank: Mapped[bool] = mapped_column(default=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["StudentSubmission"] = relationship(back_populates="answers")


class EvaluationLog(Base):
    __tablename__ = "evaluation_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("student_submissions.id"), nullable=False, index=True
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["StudentSubmission"] = relationship(back_populates="evaluation_logs")


class ReviewAudit(Base):
    __tablename__ = "review_audits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("student_submissions.id"), nullable=False, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str | None] = mapped_column(String(32))
    old_marks: Mapped[float | None] = mapped_column(Float)
    new_marks: Mapped[float | None] = mapped_column(Float)
    old_remarks: Mapped[str | None] = mapped_column(Text)
    new_remarks: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Override / escalation reason code.
    reason: Mapped[str | None] = mapped_column(String(64))
    actor_role: Mapped[str | None] = mapped_column(String(16))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["StudentSubmission"] = relationship(back_populates="review_audits")
    reviewer: Mapped["User | None"] = relationship(back_populates="review_audits")


class PlagiarismReport(Base):
    __tablename__ = "plagiarism_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False, index=True
    )
    exam_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id"), nullable=True, index=True
    )
    batch_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_jobs.id"), nullable=True
    )
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    matrix: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IntegrityFlag(Base):
    """A similarity flag between two submissions of the same exam.

    Evidence for professor review — never an automatic finding of misconduct.
    """

    __tablename__ = "integrity_flags"
    __table_args__ = (
        UniqueConstraint(
            "exam_id", "question", "submission_a_id", "submission_b_id", name="uq_integrity_pair"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(String(32), nullable=False)
    submission_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("student_submissions.id", ondelete="CASCADE"), nullable=False
    )
    submission_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("student_submissions.id", ondelete="CASCADE"), nullable=False
    )
    student_a: Mapped[str] = mapped_column(String(128), nullable=False)
    student_b: Mapped[str] = mapped_column(String(128), nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[IntegrityFlagStatus] = mapped_column(
        Enum(IntegrityFlagStatus), default=IntegrityFlagStatus.OPEN, nullable=False, index=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
