"""Database CRUD helpers."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    HUMAN_REVIEWED_STATUSES,
    TA_QUEUE_STATUSES,
    BatchJob,
    BatchJobStatus,
    EvaluationLog,
    ExtractedAnswer,
    PlagiarismReport,
    ReviewAudit,
    ReviewStatus,
    Rubric,
    StudentSubmission,
    SubmissionStatus,
    User,
    UserRole,
)


# --- Users ---


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    hashed_password: str,
    full_name: str,
    role: UserRole = UserRole.TA,
) -> User:
    user = User(
        email=email.lower(),
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def list_users(session: AsyncSession, skip: int = 0, limit: int = 50) -> list[User]:
    result = await session.execute(select(User).offset(skip).limit(limit))
    return list(result.scalars().all())


async def update_user(session: AsyncSession, user: User, **fields: Any) -> User:
    for key, value in fields.items():
        setattr(user, key, value)
    await session.flush()
    return user


# --- Rubrics ---


async def create_rubric(
    session: AsyncSession,
    *,
    name: str,
    source_filename: str,
    source_type: str,
    structured_data: dict,
    file_path: str | None = None,
    owner_id: uuid.UUID | None = None,
) -> Rubric:
    rubric = Rubric(
        name=name,
        source_filename=source_filename,
        source_type=source_type,
        structured_data=structured_data,
        file_path=file_path,
        owner_id=owner_id,
    )
    session.add(rubric)
    await session.flush()
    return rubric


async def get_rubric(session: AsyncSession, rubric_id: uuid.UUID) -> Rubric | None:
    result = await session.execute(select(Rubric).where(Rubric.id == rubric_id))
    return result.scalar_one_or_none()


# --- Submissions ---


async def create_submission(
    session: AsyncSession,
    *,
    student_id: str,
    source_filename: str,
    file_path: str,
    rubric_id: uuid.UUID | None = None,
    batch_job_id: uuid.UUID | None = None,
    uploaded_by: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    exam_id: uuid.UUID | None = None,
    student_record_id: uuid.UUID | None = None,
) -> StudentSubmission:
    submission = StudentSubmission(
        student_id=student_id,
        source_filename=source_filename,
        file_path=file_path,
        rubric_id=rubric_id,
        batch_job_id=batch_job_id,
        uploaded_by=uploaded_by,
        course_id=course_id,
        exam_id=exam_id,
        student_record_id=student_record_id,
        status=SubmissionStatus.UPLOADED,
        review_status=ReviewStatus.NOT_EVALUATED,
    )
    session.add(submission)
    await session.flush()
    return submission


async def get_submission(session: AsyncSession, submission_id: uuid.UUID) -> StudentSubmission | None:
    result = await session.execute(
        select(StudentSubmission).where(StudentSubmission.id == submission_id)
    )
    return result.scalar_one_or_none()


async def list_submissions(
    session: AsyncSession,
    *,
    rubric_id: uuid.UUID | None = None,
    batch_job_id: uuid.UUID | None = None,
    review_status: ReviewStatus | None = None,
    skip: int = 0,
    limit: int = 100,
    scope: ColumnElement[bool] | None = None,
) -> list[StudentSubmission]:
    q = select(StudentSubmission)
    if scope is not None:
        q = q.where(scope)
    if rubric_id:
        q = q.where(StudentSubmission.rubric_id == rubric_id)
    if batch_job_id:
        q = q.where(StudentSubmission.batch_job_id == batch_job_id)
    if review_status:
        q = q.where(StudentSubmission.review_status == review_status)
    q = q.order_by(StudentSubmission.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


async def count_submissions(
    session: AsyncSession,
    rubric_id: uuid.UUID | None = None,
    scope: ColumnElement[bool] | None = None,
) -> int:
    q = select(func.count()).select_from(StudentSubmission)
    if scope is not None:
        q = q.where(scope)
    if rubric_id:
        q = q.where(StudentSubmission.rubric_id == rubric_id)
    result = await session.execute(q)
    return int(result.scalar_one() or 0)


async def update_submission(
    session: AsyncSession,
    submission: StudentSubmission,
    **fields: Any,
) -> StudentSubmission:
    for key, value in fields.items():
        setattr(submission, key, value)
    await session.flush()
    return submission


async def delete_extracted_answers(session: AsyncSession, submission_id: uuid.UUID) -> None:
    """Remove OCR rows from a previous run so re-processing does not duplicate them."""
    await session.execute(
        delete(ExtractedAnswer).where(ExtractedAnswer.submission_id == submission_id)
    )


async def list_extracted_answers(
    session: AsyncSession, submission_id: uuid.UUID
) -> list[ExtractedAnswer]:
    result = await session.execute(
        select(ExtractedAnswer)
        .where(ExtractedAnswer.submission_id == submission_id)
        .order_by(ExtractedAnswer.page_index, ExtractedAnswer.question_number)
    )
    return list(result.scalars().all())


async def save_extracted_answers(
    session: AsyncSession,
    submission_id: uuid.UUID,
    answers: list[dict],
) -> list[ExtractedAnswer]:
    records = []
    for ans in answers:
        record = ExtractedAnswer(
            submission_id=submission_id,
            question_number=ans["question_number"],
            page_index=ans["page_index"],
            bbox=ans["bbox"],
            extracted_text=ans.get("extracted_text", ""),
            is_blank=ans.get("is_blank", False),
            ocr_confidence=ans.get("ocr_confidence"),
        )
        session.add(record)
        records.append(record)
    await session.flush()
    return records


async def add_evaluation_log(
    session: AsyncSession,
    submission_id: uuid.UUID,
    stage: str,
    message: str,
    metadata: dict | None = None,
) -> EvaluationLog:
    log = EvaluationLog(
        submission_id=submission_id,
        stage=stage,
        message=message,
        metadata_=metadata,
    )
    session.add(log)
    await session.flush()
    return log


async def list_evaluation_logs(
    session: AsyncSession, submission_id: uuid.UUID
) -> list[EvaluationLog]:
    result = await session.execute(
        select(EvaluationLog)
        .where(EvaluationLog.submission_id == submission_id)
        .order_by(EvaluationLog.created_at)
    )
    return list(result.scalars().all())


# --- Batch jobs ---


async def create_batch_job(
    session: AsyncSession,
    *,
    rubric_id: uuid.UUID,
    submission_ids: list[str],
    run_plagiarism: bool = True,
    created_by: uuid.UUID | None = None,
    exam_id: uuid.UUID | None = None,
) -> BatchJob:
    job = BatchJob(
        rubric_id=rubric_id,
        exam_id=exam_id,
        submission_ids=submission_ids,
        total_count=len(submission_ids),
        run_plagiarism=run_plagiarism,
        created_by=created_by,
        status=BatchJobStatus.QUEUED,
    )
    session.add(job)
    await session.flush()
    return job


async def get_batch_job(session: AsyncSession, job_id: uuid.UUID) -> BatchJob | None:
    result = await session.execute(select(BatchJob).where(BatchJob.id == job_id))
    return result.scalar_one_or_none()


async def update_batch_job(session: AsyncSession, job: BatchJob, **fields: Any) -> BatchJob:
    for key, value in fields.items():
        setattr(job, key, value)
    await session.flush()
    return job


# --- Review ---


async def add_review_audit(
    session: AsyncSession,
    *,
    submission_id: uuid.UUID,
    action: str,
    reviewer_id: uuid.UUID | None = None,
    question: str | None = None,
    old_marks: float | None = None,
    new_marks: float | None = None,
    old_remarks: str | None = None,
    new_remarks: str | None = None,
    notes: str | None = None,
    reason: str | None = None,
    actor_role: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
) -> ReviewAudit:
    audit = ReviewAudit(
        submission_id=submission_id,
        reviewer_id=reviewer_id,
        action=action,
        question=question,
        old_marks=old_marks,
        new_marks=new_marks,
        old_remarks=old_remarks,
        new_remarks=new_remarks,
        notes=notes,
        reason=reason,
        actor_role=actor_role,
        from_status=from_status,
        to_status=to_status,
        # Application clock, not the DB's transaction-scoped now(): several audit
        # rows written in one transaction must keep their order.
        created_at=datetime.now(UTC),
    )
    session.add(audit)
    await session.flush()
    return audit


async def list_review_audits(
    session: AsyncSession, submission_id: uuid.UUID
) -> list[ReviewAudit]:
    result = await session.execute(
        select(ReviewAudit)
        .where(ReviewAudit.submission_id == submission_id)
        .order_by(ReviewAudit.created_at.desc())
    )
    return list(result.scalars().all())


# --- Plagiarism ---


async def save_plagiarism_report(
    session: AsyncSession,
    *,
    rubric_id: uuid.UUID,
    flags: list[dict],
    matrix: dict | None = None,
    batch_job_id: uuid.UUID | None = None,
    exam_id: uuid.UUID | None = None,
) -> PlagiarismReport:
    report = PlagiarismReport(
        rubric_id=rubric_id,
        exam_id=exam_id,
        batch_job_id=batch_job_id,
        flags=flags,
        matrix=matrix,
    )
    session.add(report)
    await session.flush()
    return report


async def get_latest_plagiarism_report(
    session: AsyncSession, rubric_id: uuid.UUID
) -> PlagiarismReport | None:
    result = await session.execute(
        select(PlagiarismReport)
        .where(PlagiarismReport.rubric_id == rubric_id)
        .order_by(PlagiarismReport.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# --- Analytics ---


async def analytics_for_rubric(
    session: AsyncSession,
    rubric_id: uuid.UUID,
    scope: ColumnElement[bool] | None = None,
) -> dict:
    subs = await list_submissions(session, rubric_id=rubric_id, limit=500, scope=scope)
    evaluated = [s for s in subs if s.evaluation_result and s.status == SubmissionStatus.EVALUATED]

    if not evaluated:
        return {
            "rubric_id": str(rubric_id),
            "submission_count": len(subs),
            "evaluated_count": 0,
            "average_marks": 0,
            "max_total": 0,
            "toppers": [],
            "question_averages": {},
            "pass_fail": {"pass": 0, "fail": 0},
            "hardest_question": None,
            "easiest_question": None,
        }

    totals = [float(s.total_marks or 0) for s in evaluated]
    max_total = float(evaluated[0].evaluation_result.get("max_total", 0) or 0)
    pass_threshold = max_total * 0.4 if max_total else 0

    q_sums: dict[str, list[float]] = {}
    q_max: dict[str, float] = {}
    for s in evaluated:
        for r in s.evaluation_result.get("results", []):
            q = r.get("question", "?")
            q_sums.setdefault(q, []).append(float(r.get("marks_awarded", 0)))
            q_max[q] = float(r.get("max_marks", 0))

    q_avg = {q: round(sum(v) / len(v), 2) for q, v in q_sums.items() if v}
    hardest = min(q_avg, key=q_avg.get) if q_avg else None
    easiest = max(q_avg, key=q_avg.get) if q_avg else None

    toppers = sorted(
        [{"student_id": s.student_id, "total": float(s.total_marks or 0)} for s in evaluated],
        key=lambda x: x["total"],
        reverse=True,
    )[:10]

    return {
        "rubric_id": str(rubric_id),
        "submission_count": len(subs),
        "evaluated_count": len(evaluated),
        "average_marks": round(sum(totals) / len(totals), 2),
        "max_total": max_total,
        "toppers": toppers,
        "question_averages": q_avg,
        "pass_fail": {
            "pass": sum(1 for t in totals if t >= pass_threshold),
            "fail": sum(1 for t in totals if t < pass_threshold),
        },
        "hardest_question": hardest,
        "easiest_question": easiest,
        "review_pending": sum(1 for s in evaluated if s.review_status in TA_QUEUE_STATUSES),
        "review_approved": sum(1 for s in evaluated if s.review_status in HUMAN_REVIEWED_STATUSES),
    }
