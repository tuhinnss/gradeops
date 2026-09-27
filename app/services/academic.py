"""Aggregate queries and response builders for courses, exams and submissions."""

import uuid
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import Float, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TA_QUEUE_STATUSES,
    TA_REVIEWED_STATUSES,
    Course,
    CourseMember,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamStatus,
    ExamTA,
    IntegrityFlag,
    IntegrityFlagStatus,
    ReviewStatus,
    Rubric,
    Student,
    StudentSubmission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.schemas.academic import (
    CourseResponse,
    CourseStats,
    ExamCounts,
    ExamRef,
    ExamResponse,
    RubricSummary,
    SubmissionRow,
    UserSummary,
)
from app.services.text_utils import rubric_total_marks
from app.schemas.rubric import RubricSchema

ACTIVE_EXAM_STATUSES = (
    ExamStatus.DRAFT,
    ExamStatus.PROCESSING,
    ExamStatus.TA_REVIEW,
    ExamStatus.APPROVED,
    ExamStatus.LOCKED,
)

MAX_TOTAL_SQL = cast(StudentSubmission.evaluation_result["max_total"].astext, Float)


def user_summary(user: User | None) -> UserSummary | None:
    return UserSummary.model_validate(user) if user else None


async def users_by_id(db: AsyncSession, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, User]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    rows = (await db.execute(select(User).where(User.id.in_(wanted)))).scalars().all()
    return {u.id: u for u in rows}


def rubric_stats(rubric: Rubric) -> tuple[int, float]:
    try:
        schema = RubricSchema.from_dict(rubric.structured_data)
    except Exception:
        return 0, 0.0
    return len(schema.items), rubric_total_marks(schema.items)


def rubric_summary(rubric: Rubric, used_by: list[ExamRef] | None = None) -> RubricSummary:
    count, total = rubric_stats(rubric)
    return RubricSummary(
        id=rubric.id,
        name=rubric.name,
        source_filename=rubric.source_filename,
        source_type=rubric.source_type,
        question_count=count,
        total_marks=total,
        created_at=rubric.created_at,
        used_by_exams=used_by or [],
    )


# --- Exams -----------------------------------------------------------------------------


async def exam_counts(db: AsyncSession, exam_ids: list[uuid.UUID]) -> dict[uuid.UUID, ExamCounts]:
    counts: dict[uuid.UUID, ExamCounts] = {eid: ExamCounts() for eid in exam_ids}
    if not exam_ids:
        return counts
    rows = (
        await db.execute(
            select(
                StudentSubmission.exam_id,
                StudentSubmission.status,
                StudentSubmission.review_status,
                StudentSubmission.needs_manual_grading,
                func.count(),
            )
            .where(StudentSubmission.exam_id.in_(exam_ids))
            .group_by(
                StudentSubmission.exam_id,
                StudentSubmission.status,
                StudentSubmission.review_status,
                StudentSubmission.needs_manual_grading,
            )
        )
    ).all()
    for exam_id, sub_status, review_status, manual, n in rows:
        c = counts[exam_id]
        c.submissions += n
        if sub_status == SubmissionStatus.UPLOADED:
            c.uploaded += n
        elif sub_status in (SubmissionStatus.PROCESSING, SubmissionStatus.OCR_COMPLETE):
            c.processing += n
        elif sub_status == SubmissionStatus.FAILED:
            c.failed += n
        elif sub_status == SubmissionStatus.EVALUATED:
            c.processed += n
            if review_status in TA_QUEUE_STATUSES:
                c.awaiting_ta += n
            elif review_status in TA_REVIEWED_STATUSES:
                c.ta_reviewed += n
            elif review_status == ReviewStatus.ESCALATED:
                c.escalated += n
            elif review_status == ReviewStatus.PROFESSOR_APPROVED:
                c.professor_approved += n
            elif review_status == ReviewStatus.PUBLISHED:
                c.published += n
            if manual and review_status in TA_QUEUE_STATUSES:
                c.needs_manual_grading += n
    flag_rows = (
        await db.execute(
            select(IntegrityFlag.exam_id, func.count())
            .where(IntegrityFlag.exam_id.in_(exam_ids), IntegrityFlag.status == IntegrityFlagStatus.OPEN)
            .group_by(IntegrityFlag.exam_id)
        )
    ).all()
    for exam_id, n in flag_rows:
        counts[exam_id].integrity_open = n
    return counts


def exam_stage(exam: Exam, counts: ExamCounts) -> str:
    if exam.status == ExamStatus.PUBLISHED:
        return "published"
    if exam.status == ExamStatus.LOCKED:
        return "locked"
    if exam.status == ExamStatus.APPROVED:
        return "approved"
    if exam.status == ExamStatus.PROCESSING:
        return "ai_processing"
    if exam.status == ExamStatus.TA_REVIEW:
        if counts.processed and not counts.awaiting_ta and not counts.escalated:
            return "professor_approval"
        return "ta_review"
    return "setup"


async def exam_averages(
    db: AsyncSession, exam_ids: list[uuid.UUID]
) -> dict[uuid.UUID, tuple[float | None, float | None]]:
    if not exam_ids:
        return {}
    rows = (
        await db.execute(
            select(
                StudentSubmission.exam_id,
                func.avg(StudentSubmission.total_marks),
                func.max(MAX_TOTAL_SQL),
            )
            .where(
                StudentSubmission.exam_id.in_(exam_ids),
                StudentSubmission.status == SubmissionStatus.EVALUATED,
            )
            .group_by(StudentSubmission.exam_id)
        )
    ).all()
    return {
        eid: (round(float(avg), 2) if avg is not None else None, float(mx) if mx is not None else None)
        for eid, avg, mx in rows
    }


async def exam_tas(db: AsyncSession, exam_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[User]]:
    result: dict[uuid.UUID, list[User]] = defaultdict(list)
    if not exam_ids:
        return result
    rows = (
        await db.execute(
            select(ExamTA.exam_id, User)
            .join(User, User.id == ExamTA.ta_id)
            .where(ExamTA.exam_id.in_(exam_ids), ExamTA.active.is_(True))
            .order_by(User.full_name)
        )
    ).all()
    for exam_id, user in rows:
        result[exam_id].append(user)
    return result


async def build_exam_responses(
    db: AsyncSession, exams: list[Exam], response_cls: type[ExamResponse] = ExamResponse
) -> list[ExamResponse]:
    if not exams:
        return []
    ids = [e.id for e in exams]
    courses = {
        c.id: c
        for c in (
            await db.execute(select(Course).where(Course.id.in_({e.course_id for e in exams})))
        ).scalars()
    }
    rubric_ids = {e.rubric_id for e in exams if e.rubric_id}
    rubrics = {
        r.id: r
        for r in (await db.execute(select(Rubric).where(Rubric.id.in_(rubric_ids)))).scalars()
    } if rubric_ids else {}
    counts = await exam_counts(db, ids)
    averages = await exam_averages(db, ids)
    tas = await exam_tas(db, ids)

    out = []
    for exam in exams:
        course = courses[exam.course_id]
        rubric = rubrics.get(exam.rubric_id) if exam.rubric_id else None
        avg, max_seen = averages.get(exam.id, (None, None))
        rubric_total = rubric_stats(rubric)[1] if rubric else None
        out.append(
            response_cls(
                id=exam.id,
                course_id=course.id,
                course_code=course.course_code,
                course_name=course.name,
                name=exam.name,
                description=exam.description,
                exam_type=exam.exam_type,
                total_marks=exam.total_marks,
                exam_date=exam.exam_date,
                status=exam.status,
                stage=exam_stage(exam, counts[exam.id]),
                rubric=rubric_summary(rubric) if rubric else None,
                tas=[user_summary(u) for u in tas.get(exam.id, [])],
                counts=counts[exam.id],
                average_score=avg,
                max_score=max_seen or rubric_total or exam.total_marks,
                created_at=exam.created_at,
                updated_at=exam.updated_at,
                approved_at=exam.approved_at,
                locked_at=exam.locked_at,
                published_at=exam.published_at,
            )
        )
    return out


# --- Courses ---------------------------------------------------------------------------


async def build_course_responses(db: AsyncSession, courses: list[Course]) -> list[CourseResponse]:
    if not courses:
        return []
    ids = [c.id for c in courses]
    professors = await users_by_id(db, (c.professor_id for c in courses))

    students = dict(
        (
            await db.execute(
                select(Enrollment.course_id, func.count())
                .where(Enrollment.course_id.in_(ids), Enrollment.status == EnrollmentStatus.ACTIVE)
                .group_by(Enrollment.course_id)
            )
        ).all()
    )
    tas = dict(
        (
            await db.execute(
                select(CourseMember.course_id, func.count())
                .where(
                    CourseMember.course_id.in_(ids),
                    CourseMember.active.is_(True),
                    CourseMember.role == UserRole.TA,
                )
                .group_by(CourseMember.course_id)
            )
        ).all()
    )
    exam_rows = (
        await db.execute(
            select(
                Exam.course_id,
                func.count(),
                func.count().filter(Exam.status.in_(ACTIVE_EXAM_STATUSES)),
            )
            .where(Exam.course_id.in_(ids))
            .group_by(Exam.course_id)
        )
    ).all()
    exams = {cid: (total, active) for cid, total, active in exam_rows}
    sub_rows = (
        await db.execute(
            select(
                Exam.course_id,
                func.count(StudentSubmission.id),
                func.count().filter(StudentSubmission.review_status.in_(TA_QUEUE_STATUSES)),
                func.count().filter(StudentSubmission.review_status == ReviewStatus.ESCALATED),
                func.avg(
                    case(
                        (
                            and_(
                                StudentSubmission.status == SubmissionStatus.EVALUATED,
                                MAX_TOTAL_SQL > 0,
                            ),
                            StudentSubmission.total_marks / MAX_TOTAL_SQL * 100.0,
                        )
                    )
                ),
            )
            .join(Exam, Exam.id == StudentSubmission.exam_id)
            .where(Exam.course_id.in_(ids))
            .group_by(Exam.course_id)
        )
    ).all()
    subs = {cid: (n, pending, esc, avg) for cid, n, pending, esc, avg in sub_rows}

    out = []
    for c in courses:
        n, pending, esc, avg = subs.get(c.id, (0, 0, 0, None))
        total_exams, active_exams = exams.get(c.id, (0, 0))
        out.append(
            CourseResponse(
                id=c.id,
                name=c.name,
                course_code=c.course_code,
                description=c.description,
                semester=c.semester,
                academic_year=c.academic_year,
                status=c.status,
                professor=user_summary(professors[c.professor_id]),
                created_at=c.created_at,
                updated_at=c.updated_at,
                stats=CourseStats(
                    student_count=students.get(c.id, 0),
                    ta_count=tas.get(c.id, 0),
                    exam_count=total_exams,
                    active_exam_count=active_exams,
                    submission_count=n,
                    pending_reviews=pending,
                    escalated=esc,
                    average_score_pct=round(float(avg), 1) if avg is not None else None,
                ),
            )
        )
    return out


# --- Submissions -----------------------------------------------------------------------


async def student_names(db: AsyncSession, record_ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {i for i in record_ids if i}
    if not wanted:
        return {}
    rows = (await db.execute(select(Student.id, Student.name).where(Student.id.in_(wanted)))).all()
    return {sid: name for sid, name in rows}


async def integrity_counts(db: AsyncSession, submission_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not submission_ids:
        return {}
    rows = (
        await db.execute(
            select(IntegrityFlag.submission_a_id, IntegrityFlag.submission_b_id).where(
                IntegrityFlag.status == IntegrityFlagStatus.OPEN,
                or_(
                    IntegrityFlag.submission_a_id.in_(submission_ids),
                    IntegrityFlag.submission_b_id.in_(submission_ids),
                ),
            )
        )
    ).all()
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for a, b in rows:
        counts[a] += 1
        counts[b] += 1
    return counts


def submission_max_total(sub: StudentSubmission) -> float | None:
    if sub.evaluation_result and sub.evaluation_result.get("max_total") is not None:
        return float(sub.evaluation_result["max_total"])
    return None


async def build_submission_rows(
    db: AsyncSession, submissions: list[StudentSubmission]
) -> list[SubmissionRow]:
    names = await student_names(db, (s.student_record_id for s in submissions))
    users = await users_by_id(
        db, [u for s in submissions for u in (s.assigned_ta_id, s.reviewed_by)]
    )
    flags = await integrity_counts(db, [s.id for s in submissions])
    return [
        SubmissionRow(
            id=s.id,
            exam_id=s.exam_id,
            student_id=s.student_id,
            student_name=names.get(s.student_record_id) if s.student_record_id else None,
            source_filename=s.source_filename,
            status=s.status,
            review_status=s.review_status,
            total_marks=s.total_marks,
            max_total=submission_max_total(s),
            ai_total_marks=s.ai_total_marks,
            ta_total_marks=s.ta_total_marks,
            professor_total_marks=s.professor_total_marks,
            min_confidence=s.min_confidence,
            needs_manual_grading=s.needs_manual_grading,
            integrity_open=flags.get(s.id, 0),
            assigned_ta=user_summary(users.get(s.assigned_ta_id)) if s.assigned_ta_id else None,
            reviewed_by=user_summary(users.get(s.reviewed_by)) if s.reviewed_by else None,
            escalation_reason=s.escalation_reason if s.review_status == ReviewStatus.ESCALATED else None,
            error_message=s.error_message,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in submissions
    ]
