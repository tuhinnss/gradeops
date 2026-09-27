"""Recent activity feeds built from persisted audit rows (never synthesised)."""

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Exam, ExamAudit, ReviewAudit, StudentSubmission
from app.schemas.dashboard import ActivityItem
from app.services.academic import user_summary, users_by_id


async def recent_activity(
    db: AsyncSession,
    *,
    exam_filter: ColumnElement[bool],
    review_filter: ColumnElement[bool] | None = None,
    include_exam_events: bool = True,
    limit: int = 15,
) -> list[ActivityItem]:
    review_q = (
        select(ReviewAudit, StudentSubmission.student_id, Exam.id, Exam.name)
        .join(StudentSubmission, StudentSubmission.id == ReviewAudit.submission_id)
        .join(Exam, Exam.id == StudentSubmission.exam_id)
        .where(exam_filter)
        .order_by(ReviewAudit.created_at.desc())
        .limit(limit)
    )
    if review_filter is not None:
        review_q = review_q.where(review_filter)
    review_rows = (await db.execute(review_q)).all()
    exam_rows = []
    if include_exam_events:
        exam_rows = (
            await db.execute(
                select(ExamAudit, Exam.name)
                .join(Exam, Exam.id == ExamAudit.exam_id)
                .where(exam_filter)
                .order_by(ExamAudit.created_at.desc())
                .limit(limit)
            )
        ).all()
    users = await users_by_id(
        db, [a.reviewer_id for a, *_ in review_rows] + [a.actor_id for a, _ in exam_rows]
    )
    items = [
        ActivityItem(
            kind="review",
            action=a.action,
            actor=user_summary(users.get(a.reviewer_id)) if a.reviewer_id else None,
            exam_id=exam_id,
            exam_name=exam_name,
            submission_id=a.submission_id,
            student_id=student_id,
            question=a.question,
            old_marks=a.old_marks,
            new_marks=a.new_marks,
            notes=a.reason or a.notes,
            created_at=a.created_at,
        )
        for a, student_id, exam_id, exam_name in review_rows
    ] + [
        ActivityItem(
            kind="exam",
            action=a.action,
            actor=user_summary(users.get(a.actor_id)) if a.actor_id else None,
            exam_id=a.exam_id,
            exam_name=exam_name,
            notes=a.notes,
            created_at=a.created_at,
        )
        for a, exam_name in exam_rows
    ]
    items.sort(key=lambda i: i.created_at or 0, reverse=True)
    return items[:limit]
