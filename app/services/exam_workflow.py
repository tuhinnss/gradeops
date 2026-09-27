"""Exam-level state transitions driven by the processing pipeline."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Exam,
    ExamAudit,
    ExamStatus,
    IntegrityFlag,
    StudentSubmission,
    SubmissionStatus,
)
from app.schemas.evaluation import PlagiarismFlag

logger = logging.getLogger(__name__)


async def add_exam_audit(
    session: AsyncSession,
    exam: Exam,
    *,
    action: str,
    actor_id: uuid.UUID | None,
    from_status: ExamStatus | None = None,
    notes: str | None = None,
    details: dict | None = None,
) -> ExamAudit:
    audit = ExamAudit(
        exam_id=exam.id,
        actor_id=actor_id,
        action=action,
        from_status=from_status.value if from_status else None,
        to_status=exam.status.value,
        notes=notes,
        details=details,
        created_at=datetime.now(UTC),
    )
    session.add(audit)
    await session.flush()
    return audit


async def mark_exam_processing(
    session: AsyncSession, exam: Exam, actor_id: uuid.UUID | None, submission_count: int
) -> None:
    previous = exam.status
    exam.status = ExamStatus.PROCESSING
    await add_exam_audit(
        session,
        exam,
        action="processing_started",
        actor_id=actor_id,
        from_status=previous,
        details={"submissions": submission_count},
    )


async def finish_exam_processing(session: AsyncSession, exam_id: uuid.UUID) -> None:
    """PROCESSING → TA_REVIEW once evaluated submissions exist (else back to DRAFT)."""
    exam = await session.get(Exam, exam_id)
    if not exam or exam.status != ExamStatus.PROCESSING:
        return
    evaluated = (
        await session.execute(
            select(func.count())
            .select_from(StudentSubmission)
            .where(
                StudentSubmission.exam_id == exam_id,
                StudentSubmission.status == SubmissionStatus.EVALUATED,
            )
        )
    ).scalar_one()
    previous = exam.status
    exam.status = ExamStatus.TA_REVIEW if evaluated else ExamStatus.DRAFT
    await add_exam_audit(
        session,
        exam,
        action="processing_finished",
        actor_id=None,
        from_status=previous,
        details={"evaluated": int(evaluated)},
    )


async def persist_integrity_flags(
    session: AsyncSession,
    exam_id: uuid.UUID,
    flags: list[PlagiarismFlag],
) -> int:
    """Upsert similarity flags for an exam, keeping any professor decision already made."""
    if not flags:
        return 0
    rows = (
        await session.execute(
            select(StudentSubmission.id, StudentSubmission.student_id, StudentSubmission.created_at)
            .where(StudentSubmission.exam_id == exam_id)
            .order_by(StudentSubmission.created_at)
        )
    ).all()
    # Latest submission per student ID wins (re-uploads replace earlier sheets).
    by_student = {student_id: sub_id for sub_id, student_id, _ in rows}
    saved = 0
    for flag in flags:
        a = by_student.get(flag.student_id_a)
        b = by_student.get(flag.student_id_b)
        if not a or not b or a == b:
            continue
        if str(a) > str(b):  # canonical pair order so re-runs hit the same row
            a, b = b, a
            student_a, student_b = flag.student_id_b, flag.student_id_a
            excerpt_a, excerpt_b = flag.excerpt_b, flag.excerpt_a
        else:
            student_a, student_b = flag.student_id_a, flag.student_id_b
            excerpt_a, excerpt_b = flag.excerpt_a, flag.excerpt_b
        stmt = insert(IntegrityFlag).values(
            id=uuid.uuid4(),
            exam_id=exam_id,
            question=flag.question,
            submission_a_id=a,
            submission_b_id=b,
            student_a=student_a,
            student_b=student_b,
            similarity=flag.similarity,
            note=flag.note,
            evidence={"excerpt_a": excerpt_a, "excerpt_b": excerpt_b},
            created_at=datetime.now(UTC),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_integrity_pair",
            set_={
                "similarity": stmt.excluded.similarity,
                "note": stmt.excluded.note,
                "evidence": stmt.excluded.evidence,
            },
        )
        await session.execute(stmt)
        saved += 1
    return saved
