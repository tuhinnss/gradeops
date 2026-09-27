"""TA workload figures (from persisted assignments and review audits)."""

import uuid
from collections import defaultdict

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TA_QUEUE_STATUSES,
    CourseMember,
    Exam,
    ExamTA,
    ReviewAudit,
    ReviewStatus,
    StudentSubmission,
    SubmissionStatus,
    User,
)
from app.schemas.academic import ExamRef, TAWorkload
from app.services.academic import user_summary

REVIEW_DECISIONS = ("approve", "override", "escalate")


async def ta_workloads(db: AsyncSession, course_id: uuid.UUID) -> list[TAWorkload]:
    members = (
        await db.execute(
            select(CourseMember, User)
            .join(User, User.id == CourseMember.user_id)
            .where(CourseMember.course_id == course_id)
            .order_by(CourseMember.active.desc(), User.full_name)
        )
    ).all()
    if not members:
        return []
    ta_ids = [u.id for _, u in members]
    exam_ids_in_course = select(Exam.id).where(Exam.course_id == course_id)

    assignments: dict[uuid.UUID, list[ExamRef]] = defaultdict(list)
    for ta_id, exam_id, name in (
        await db.execute(
            select(ExamTA.ta_id, Exam.id, Exam.name)
            .join(Exam, Exam.id == ExamTA.exam_id)
            .where(Exam.course_id == course_id, ExamTA.active.is_(True), ExamTA.ta_id.in_(ta_ids))
            .order_by(Exam.created_at)
        )
    ).all():
        assignments[ta_id].append(ExamRef(id=exam_id, name=name))

    eligible: dict[uuid.UUID, tuple[int, int]] = {}
    for ta_id in ta_ids:
        exam_ids = [e.id for e in assignments.get(ta_id, [])]
        if not exam_ids:
            eligible[ta_id] = (0, 0)
            continue
        row = (
            await db.execute(
                select(
                    func.count(),
                    func.count().filter(StudentSubmission.review_status.in_(TA_QUEUE_STATUSES)),
                ).where(
                    StudentSubmission.exam_id.in_(exam_ids),
                    StudentSubmission.status == SubmissionStatus.EVALUATED,
                    or_(
                        StudentSubmission.assigned_ta_id.is_(None),
                        StudentSubmission.assigned_ta_id == ta_id,
                    ),
                )
            )
        ).one()
        eligible[ta_id] = (row[0], row[1])

    audit_rows = (
        await db.execute(
            select(
                ReviewAudit.reviewer_id,
                func.count(func.distinct(ReviewAudit.submission_id)),
                func.count(func.distinct(ReviewAudit.submission_id)).filter(
                    ReviewAudit.action == "override"
                ),
            )
            .join(StudentSubmission, StudentSubmission.id == ReviewAudit.submission_id)
            .where(
                ReviewAudit.reviewer_id.in_(ta_ids),
                ReviewAudit.action.in_(REVIEW_DECISIONS),
                StudentSubmission.exam_id.in_(exam_ids_in_course),
            )
            .group_by(ReviewAudit.reviewer_id)
        )
    ).all()
    reviewed = {rid: (n, ov) for rid, n, ov in audit_rows}

    escalated = dict(
        (
            await db.execute(
                select(StudentSubmission.escalated_by, func.count())
                .where(
                    and_(
                        StudentSubmission.escalated_by.in_(ta_ids),
                        StudentSubmission.review_status == ReviewStatus.ESCALATED,
                        StudentSubmission.exam_id.in_(exam_ids_in_course),
                    )
                )
                .group_by(StudentSubmission.escalated_by)
            )
        ).all()
    )

    out = []
    for member, user in members:
        total, pending = eligible.get(user.id, (0, 0))
        n_reviewed, n_overrides = reviewed.get(user.id, (0, 0))
        out.append(
            TAWorkload(
                user=user_summary(user),
                active=member.active,
                assigned_exams=assignments.get(user.id, []),
                assigned_submissions=total,
                reviewed=n_reviewed,
                pending=pending,
                escalated=escalated.get(user.id, 0),
                overrides=n_overrides,
            )
        )
    return out
