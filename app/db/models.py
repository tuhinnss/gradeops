"""SQLAlchemy ORM models."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    INSTRUCTOR = "instructor"
    TA = "ta"


class SubmissionStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    OCR_COMPLETE = "ocr_complete"
    EVALUATED = "evaluated"
    FAILED = "failed"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    OVERRIDDEN = "overridden"
    REJECTED = "rejected"


class BatchJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


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


class Rubric(Base):
    __tablename__ = "rubrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(1024))
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[list["StudentSubmission"]] = relationship(back_populates="rubric")
    batch_jobs: Mapped[list["BatchJob"]] = relationship(back_populates="rubric")


class BatchJob(Base):
    __tablename__ = "batch_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False, index=True
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
    student_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    rubric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=True, index=True
    )
    batch_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_jobs.id"), nullable=True, index=True
    )
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.UPLOADED, nullable=False, index=True
    )
    review_status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus), default=ReviewStatus.PENDING, nullable=False, index=True
    )
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    page_count: Mapped[int | None] = mapped_column(Integer)
    extracted_text: Mapped[dict | None] = mapped_column(JSONB)
    evaluation_result: Mapped[dict | None] = mapped_column(JSONB)
    annotated_pdf_path: Mapped[str | None] = mapped_column(String(1024))
    total_marks: Mapped[float | None] = mapped_column(Float)
    plagiarism_score: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    rubric: Mapped["Rubric | None"] = relationship(back_populates="submissions")
    batch_job: Mapped["BatchJob | None"] = relationship(back_populates="submissions")
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
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str | None] = mapped_column(String(32))
    old_marks: Mapped[float | None] = mapped_column(Float)
    new_marks: Mapped[float | None] = mapped_column(Float)
    old_remarks: Mapped[str | None] = mapped_column(Text)
    new_remarks: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submission: Mapped["StudentSubmission"] = relationship(back_populates="review_audits")
    reviewer: Mapped["User | None"] = relationship(back_populates="review_audits")


class PlagiarismReport(Base):
    __tablename__ = "plagiarism_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rubric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rubrics.id"), nullable=False, index=True
    )
    batch_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("batch_jobs.id"), nullable=True
    )
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    matrix: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
