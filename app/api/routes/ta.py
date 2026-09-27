"""TA workspace: assigned exams, review queue, review detail, history."""

import uuid
from datetime import UTC, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import TAUser
from app.api.permissions import exam_scope, require_submission_access, ta_exam_ids
from app.db.models import (
    TA_QUEUE_STATUSES,
    Course,
    Exam,
    ReviewAudit,
    ReviewStatus,
    StudentSubmission,
    SubmissionStatus,
)
from app.db.session import get_db
from app.schemas.academic import TAExamResponse
from app.schemas.dashboard import TADashboardResponse
from app.schemas.review import (
    QueueSort,
    QueueStatusFilter,
    ReviewDetailResponse,
    ReviewHistoryItem,
    ReviewHistoryResponse,
    ReviewQueueResponse,
)
from app.services.academic import build_exam_responses
from app.services.activity import recent_activity
from app.services.review_queue import review_detail, review_queue

router = APIRouter()

TA_DECISIONS = ("approve", "override", "escalate")


def _my_eligible(user):
    return (
        StudentSubmission.exam_id.in_(ta_exam_ids(user)),
        or_(StudentSubmission.assigned_ta_id.is_(None), StudentSubmission.assigned_ta_id == user.id),
    )


@router.get("/dashboard", response_model=TADashboardResponse)
async def ta_dashboard(user: TAUser, db: AsyncSession = Depends(get_db)) -> TADashboardResponse:
    assigned = await db.scalar(select(func.count()).select_from(ta_exam_ids(user).subquery())) or 0
    pending = await db.scalar(
        select(func.count()).where(
            *_my_eligible(user),
            StudentSubmission.status == SubmissionStatus.EVALUATED,
            StudentSubmission.review_status.in_(TA_QUEUE_STATUSES),
        )
    ) or 0
    start_of_day = datetime.combine(datetime.now(UTC).date(), time.min, tzinfo=UTC)
    reviewed_today = await db.scalar(
        select(func.count(func.distinct(ReviewAudit.submission_id))).where(
            ReviewAudit.reviewer_id == user.id,
            ReviewAudit.action.in_(TA_DECISIONS),
            ReviewAudit.created_at >= start_of_day,
        )
    ) or 0
    total_reviewed = await db.scalar(
        select(func.count(func.distinct(ReviewAudit.submission_id))).where(
            ReviewAudit.reviewer_id == user.id, ReviewAudit.action.in_(TA_DECISIONS)
        )
    ) or 0
    overrides = await db.scalar(
        select(func.count(func.distinct(ReviewAudit.submission_id))).where(
            ReviewAudit.reviewer_id == user.id, ReviewAudit.action == "override"
        )
    ) or 0
    esc_open = await db.scalar(
        select(func.count()).where(
            StudentSubmission.escalated_by == user.id, StudentSubmission.review_status == ReviewStatus.ESCALATED
        )
    ) or 0
    esc_total = await db.scalar(
        select(func.count(func.distinct(ReviewAudit.submission_id))).where(
            ReviewAudit.reviewer_id == user.id, ReviewAudit.action == "escalate"
        )
    ) or 0
    return TADashboardResponse(
        assigned_exams=assigned,
        pending_reviews=pending,
        reviewed_today=reviewed_today,
        total_reviewed=total_reviewed,
        overrides=overrides,
        escalations_open=esc_open,
        escalations_total=esc_total,
        recent_activity=await recent_activity(
            db,
            exam_filter=exam_scope(user),
            review_filter=ReviewAudit.reviewer_id == user.id,
            include_exam_events=False,
            limit=10,
        ),
    )


@router.get("/exams", response_model=list[TAExamResponse])
async def ta_exams(user: TAUser, db: AsyncSession = Depends(get_db)) -> list[TAExamResponse]:
    exams = list((await db.execute(select(Exam).where(exam_scope(user)).order_by(Exam.created_at.desc()))).scalars())
    responses = await build_exam_responses(db, exams, TAExamResponse)
    for resp in responses:
        row = (
            await db.execute(
                select(
                    func.count().filter(StudentSubmission.review_status.in_(TA_QUEUE_STATUSES)),
                ).where(
                    StudentSubmission.exam_id == resp.id,
                    StudentSubmission.status == SubmissionStatus.EVALUATED,
                    or_(StudentSubmission.assigned_ta_id.is_(None), StudentSubmission.assigned_ta_id == user.id),
                )
            )
        ).one()
        resp.my_pending = row[0]
        resp.my_reviewed = await db.scalar(
            select(func.count(func.distinct(ReviewAudit.submission_id)))
            .join(StudentSubmission, StudentSubmission.id == ReviewAudit.submission_id)
            .where(
                StudentSubmission.exam_id == resp.id,
                ReviewAudit.reviewer_id == user.id,
                ReviewAudit.action.in_(TA_DECISIONS),
            )
        ) or 0
    return responses


@router.get("/reviews", response_model=ReviewQueueResponse)
async def ta_review_queue(
    user: TAUser,
    exam_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    status: QueueStatusFilter | str = "pending",
    min_confidence: float | None = Query(None, ge=0, le=1),
    max_confidence: float | None = Query(None, ge=0, le=1),
    integrity: bool = False,
    manual: bool = False,
    student: str | None = Query(None, max_length=128),
    question: str | None = Query(None, max_length=32),
    sort: QueueSort = "confidence_asc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ReviewQueueResponse:
    try:
        return await review_queue(
            db, user, exam_id=exam_id, course_id=course_id, status=status,
            min_confidence=min_confidence, max_confidence=max_confidence,
            integrity_only=integrity, manual_only=manual, student=student, question=question,
            sort=sort, limit=limit, offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Unknown status filter '{status}'") from exc


@router.get("/reviews/{submission_id}", response_model=ReviewDetailResponse)
async def ta_review_detail(
    submission_id: uuid.UUID, user: TAUser, db: AsyncSession = Depends(get_db)
) -> ReviewDetailResponse:
    sub = await require_submission_access(db, submission_id, user)
    return await review_detail(db, sub, user)


@router.get("/history", response_model=ReviewHistoryResponse)
async def ta_history(
    user: TAUser,
    action: str | None = Query(None, max_length=32),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> ReviewHistoryResponse:
    conditions = [ReviewAudit.reviewer_id == user.id]
    if action:
        conditions.append(ReviewAudit.action == action)
    total = await db.scalar(select(func.count()).select_from(ReviewAudit).where(*conditions)) or 0
    rows = (
        await db.execute(
            select(ReviewAudit, StudentSubmission.student_id, Exam.id, Exam.name, Course.course_code)
            .join(StudentSubmission, StudentSubmission.id == ReviewAudit.submission_id)
            .outerjoin(Exam, Exam.id == StudentSubmission.exam_id)
            .outerjoin(Course, Course.id == Exam.course_id)
            .where(*conditions)
            .order_by(ReviewAudit.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return ReviewHistoryResponse(
        total=total,
        items=[
            ReviewHistoryItem(
                id=a.id,
                submission_id=a.submission_id,
                student_id=student_id,
                exam_id=exam_id,
                exam_name=exam_name,
                course_code=course_code,
                action=a.action,
                question=a.question,
                old_marks=a.old_marks,
                new_marks=a.new_marks,
                reason=a.reason,
                notes=a.notes,
                from_status=a.from_status,
                to_status=a.to_status,
                created_at=a.created_at,
            )
            for a, student_id, exam_id, exam_name, course_code in rows
        ],
    )
