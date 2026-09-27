"""Similarity (integrity) flag listing and resolution."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Course,
    Exam,
    IntegrityFlag,
    IntegrityFlagStatus,
    StudentSubmission,
    User,
)
from app.schemas.dashboard import IntegrityFlagResponse, IntegritySide
from app.services.academic import student_names, user_summary, users_by_id


async def list_integrity_flags(
    db: AsyncSession,
    professor: User,
    *,
    exam_id: uuid.UUID | None = None,
    status: IntegrityFlagStatus | None = None,
) -> list[IntegrityFlagResponse]:
    q = (
        select(IntegrityFlag, Exam, Course)
        .join(Exam, Exam.id == IntegrityFlag.exam_id)
        .join(Course, Course.id == Exam.course_id)
        .where(Course.professor_id == professor.id)
        .order_by(IntegrityFlag.status, IntegrityFlag.similarity.desc())
    )
    if exam_id:
        q = q.where(IntegrityFlag.exam_id == exam_id)
    if status:
        q = q.where(IntegrityFlag.status == status)
    rows = (await db.execute(q)).all()
    if not rows:
        return []
    sub_ids = {f.submission_a_id for f, _, _ in rows} | {f.submission_b_id for f, _, _ in rows}
    subs = {
        s.id: s
        for s in (await db.execute(select(StudentSubmission).where(StudentSubmission.id.in_(sub_ids)))).scalars()
    }
    names = await student_names(db, (s.student_record_id for s in subs.values()))
    resolvers = await users_by_id(db, (f.resolved_by for f, _, _ in rows))

    def side(sub_id: uuid.UUID, student: str, excerpt: str | None) -> IntegritySide:
        sub = subs.get(sub_id)
        return IntegritySide(
            submission_id=sub_id,
            student_id=student,
            student_name=names.get(sub.student_record_id) if sub and sub.student_record_id else None,
            score=sub.total_marks if sub else None,
            excerpt=excerpt,
        )

    out = []
    for flag, exam, course in rows:
        evidence = flag.evidence or {}
        out.append(
            IntegrityFlagResponse(
                id=flag.id,
                exam_id=exam.id,
                exam_name=exam.name,
                course_code=course.course_code,
                question=flag.question,
                similarity=flag.similarity,
                a=side(flag.submission_a_id, flag.student_a, evidence.get("excerpt_a")),
                b=side(flag.submission_b_id, flag.student_b, evidence.get("excerpt_b")),
                note=flag.note,
                status=flag.status,
                resolution_notes=flag.resolution_notes,
                resolved_by=user_summary(resolvers.get(flag.resolved_by)) if flag.resolved_by else None,
                resolved_at=flag.resolved_at,
                created_at=flag.created_at,
            )
        )
    return out


def resolve_flag(flag: IntegrityFlag, user: User, status: IntegrityFlagStatus, notes: str | None) -> None:
    flag.status = status
    flag.resolution_notes = notes
    if status == IntegrityFlagStatus.OPEN:
        flag.resolved_by = None
        flag.resolved_at = None
    else:
        flag.resolved_by = user.id
        flag.resolved_at = datetime.now(UTC)
