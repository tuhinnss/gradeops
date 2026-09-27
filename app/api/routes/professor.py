"""Professor-wide views: dashboard, escalations, integrity, submissions."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import ProfessorUser
from app.api.permissions import exam_scope, owned_course_ids
from app.db.models import (
    TA_QUEUE_STATUSES,
    TA_REVIEWED_STATUSES,
    Course,
    CourseStatus,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamStatus,
    IntegrityFlag,
    IntegrityFlagStatus,
    ReviewStatus,
    StudentSubmission,
)
from app.db.session import get_db
from app.schemas.dashboard import (
    IntegrityFlagResponse,
    IntegrityFlagUpdate,
    ProfessorDashboardResponse,
)
from app.schemas.review import (
    ESCALATION_REASON_LABELS,
    EscalationResponse,
    QueueSort,
    QueueStatusFilter,
    ReviewQueueResponse,
)
from app.services.academic import (
    ACTIVE_EXAM_STATUSES,
    build_exam_responses,
    student_names,
    submission_max_total,
    user_summary,
    users_by_id,
)
from app.services.activity import recent_activity
from app.services.integrity import list_integrity_flags, resolve_flag
from app.services.review_queue import review_queue

router = APIRouter()


def _owned_exam_ids(user):
    return select(Exam.id).where(Exam.course_id.in_(owned_course_ids(user)))


@router.get("/dashboard", response_model=ProfessorDashboardResponse)
async def professor_dashboard(user: ProfessorUser, db: AsyncSession = Depends(get_db)) -> ProfessorDashboardResponse:
    active_course_ids = select(Course.id).where(Course.professor_id == user.id, Course.status == CourseStatus.ACTIVE)
    active_courses = await db.scalar(select(func.count()).select_from(active_course_ids.subquery())) or 0
    active_exams = list(
        (
            await db.execute(
                select(Exam)
                .where(Exam.course_id.in_(active_course_ids), Exam.status.in_(ACTIVE_EXAM_STATUSES))
                .order_by(Exam.updated_at.desc())
            )
        ).scalars()
    )
    students = await db.scalar(
        select(func.count(func.distinct(Enrollment.student_id))).where(
            Enrollment.course_id.in_(active_course_ids), Enrollment.status == EnrollmentStatus.ACTIVE
        )
    ) or 0
    owned_exams = _owned_exam_ids(user)
    row = (
        await db.execute(
            select(
                func.count(),
                func.count().filter(StudentSubmission.review_status.in_(TA_QUEUE_STATUSES)),
                func.count().filter(StudentSubmission.review_status.in_(TA_REVIEWED_STATUSES)),
                func.count().filter(StudentSubmission.review_status == ReviewStatus.ESCALATED),
            ).where(StudentSubmission.exam_id.in_(owned_exams))
        )
    ).one()
    flags = await db.scalar(
        select(func.count()).where(
            IntegrityFlag.exam_id.in_(owned_exams), IntegrityFlag.status == IntegrityFlagStatus.OPEN
        )
    ) or 0
    ready = sum(1 for e in active_exams if e.status in (ExamStatus.APPROVED, ExamStatus.LOCKED))
    return ProfessorDashboardResponse(
        active_courses=active_courses,
        active_exams=len(active_exams),
        students=students,
        submissions=row[0],
        pending_ta_reviews=row[1],
        awaiting_professor_approval=row[2],
        escalated=row[3],
        integrity_flags_open=flags,
        ready_to_publish=ready,
        exams=await build_exam_responses(db, active_exams[:8]),
        recent_activity=await recent_activity(db, exam_filter=exam_scope(user)),
    )


@router.get("/escalations", response_model=list[EscalationResponse])
async def list_escalations(
    user: ProfessorUser,
    exam_id: uuid.UUID | None = None,
    include_resolved: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[EscalationResponse]:
    q = (
        select(StudentSubmission, Exam, Course)
        .join(Exam, Exam.id == StudentSubmission.exam_id)
        .join(Course, Course.id == Exam.course_id)
        .where(Course.professor_id == user.id, StudentSubmission.escalated_at.isnot(None))
        .order_by(StudentSubmission.escalated_at.desc())
    )
    if not include_resolved:
        q = q.where(StudentSubmission.review_status == ReviewStatus.ESCALATED)
    if exam_id:
        q = q.where(StudentSubmission.exam_id == exam_id)
    rows = (await db.execute(q)).all()
    users = await users_by_id(db, (s.escalated_by for s, _, _ in rows))
    names = await student_names(db, (s.student_record_id for s, _, _ in rows))
    return [
        EscalationResponse(
            submission_id=s.id,
            student_id=s.student_id,
            student_name=names.get(s.student_record_id) if s.student_record_id else None,
            exam_id=exam.id,
            exam_name=exam.name,
            course_code=course.course_code,
            escalated_by=user_summary(users.get(s.escalated_by)) if s.escalated_by else None,
            reason=s.escalation_reason,
            reason_label=ESCALATION_REASON_LABELS.get(s.escalation_reason or "", s.escalation_reason),
            notes=s.escalation_notes,
            escalated_at=s.escalated_at,
            ai_score=s.ai_total_marks,
            ta_score=s.ta_total_marks,
            current_score=s.total_marks,
            max_score=submission_max_total(s),
            min_confidence=s.min_confidence,
            review_status=s.review_status,
        )
        for s, exam, course in rows
    ]


@router.get("/integrity", response_model=list[IntegrityFlagResponse])
async def list_integrity(
    user: ProfessorUser,
    exam_id: uuid.UUID | None = None,
    status: IntegrityFlagStatus | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[IntegrityFlagResponse]:
    return await list_integrity_flags(db, user, exam_id=exam_id, status=status)


@router.patch("/integrity/{flag_id}", response_model=IntegrityFlagResponse)
async def update_integrity_flag(
    flag_id: uuid.UUID, body: IntegrityFlagUpdate, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> IntegrityFlagResponse:
    """The professor makes the final determination on a similarity flag."""
    flag = await db.get(IntegrityFlag, flag_id)
    if not flag:
        raise HTTPException(status_code=404, detail="Flag not found")
    exam = await db.get(Exam, flag.exam_id)
    course = await db.get(Course, exam.course_id) if exam else None
    if not course or course.professor_id != user.id:
        raise HTTPException(status_code=404, detail="Flag not found")
    if body.status != IntegrityFlagStatus.OPEN and not (body.notes or "").strip():
        raise HTTPException(status_code=400, detail="Record a note explaining the determination")
    resolve_flag(flag, user, body.status, body.notes)
    await db.flush()
    flags = await list_integrity_flags(db, user, exam_id=flag.exam_id)
    return next(f for f in flags if f.id == flag_id)


@router.get("/submissions", response_model=ReviewQueueResponse)
async def list_submissions(
    user: ProfessorUser,
    exam_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    status: QueueStatusFilter | str = "all",
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
