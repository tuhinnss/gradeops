"""Resource-level authorization: ownership (professor) and assignment (TA).

Knowing a UUID never grants access. Every check resolves the resource, then
verifies the caller owns it (professor) or is actively assigned to it (TA).
Inaccessible resources are reported as 404 so IDs cannot be probed; a role that
can see a resource but not perform an action gets 403.

``user=None`` only occurs on legacy endpoints in open demo mode
(AUTH_ENABLED=false) and is always allowed there.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BatchJob,
    Course,
    CourseMember,
    CourseStatus,
    Exam,
    ExamTA,
    Rubric,
    StudentSubmission,
    User,
    UserRole,
)


def _not_found(kind: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{kind} not found")


def _forbidden(detail: str = "Insufficient permissions") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


# --- SQL scopes (for list endpoints) ----------------------------------------------


def owned_course_ids(user: User):
    return select(Course.id).where(Course.professor_id == user.id)


def ta_exam_ids(user: User):
    """Exams the TA is actively assigned to, in active courses they are still staff on."""
    return (
        select(ExamTA.exam_id)
        .join(Exam, Exam.id == ExamTA.exam_id)
        .join(Course, Course.id == Exam.course_id)
        .join(
            CourseMember,
            and_(
                CourseMember.course_id == Course.id,
                CourseMember.user_id == user.id,
                CourseMember.active.is_(True),
            ),
        )
        .where(
            ExamTA.ta_id == user.id,
            ExamTA.active.is_(True),
            Course.status == CourseStatus.ACTIVE,
        )
    )


def ta_course_ids(user: User):
    return (
        select(CourseMember.course_id)
        .join(Course, Course.id == CourseMember.course_id)
        .where(
            CourseMember.user_id == user.id,
            CourseMember.active.is_(True),
            Course.status == CourseStatus.ACTIVE,
        )
    )


def course_scope(user: User) -> ColumnElement[bool]:
    if user.role == UserRole.PROFESSOR:
        return Course.professor_id == user.id
    return Course.id.in_(ta_course_ids(user))


def exam_scope(user: User) -> ColumnElement[bool]:
    if user.role == UserRole.PROFESSOR:
        return Exam.course_id.in_(owned_course_ids(user))
    return Exam.id.in_(ta_exam_ids(user))


def submission_scope(user: User | None) -> ColumnElement[bool]:
    """WHERE clause restricting StudentSubmission rows to what ``user`` may read."""
    if user is None:
        return StudentSubmission.id.isnot(None)
    if user.role == UserRole.PROFESSOR:
        owned_exams = select(Exam.id).where(Exam.course_id.in_(owned_course_ids(user)))
        return or_(
            StudentSubmission.exam_id.in_(owned_exams),
            StudentSubmission.course_id.in_(owned_course_ids(user)),
            and_(StudentSubmission.exam_id.is_(None), StudentSubmission.uploaded_by == user.id),
        )
    if user.role == UserRole.TA:
        return and_(
            StudentSubmission.exam_id.in_(ta_exam_ids(user)),
            or_(
                StudentSubmission.assigned_ta_id.is_(None),
                StudentSubmission.assigned_ta_id == user.id,
            ),
        )
    return false()


# --- Single-resource checks -----------------------------------------------------


async def require_course_access(
    db: AsyncSession, course_id: uuid.UUID, user: User, *, manage: bool = False
) -> Course:
    """Professor: must own the course. TA: read-only, must be active course staff."""
    course = await db.get(Course, course_id)
    if not course:
        raise _not_found("Course")
    if user.role == UserRole.PROFESSOR:
        if course.professor_id != user.id:
            raise _not_found("Course")
        return course
    visible = await db.scalar(
        select(CourseMember.id).where(
            CourseMember.course_id == course_id,
            CourseMember.user_id == user.id,
            CourseMember.active.is_(True),
        )
    )
    if not visible or course.status != CourseStatus.ACTIVE:
        raise _not_found("Course")
    if manage:
        raise _forbidden("Only the course professor can do this")
    return course


async def require_exam_access(
    db: AsyncSession, exam_id: uuid.UUID, user: User, *, manage: bool = False
) -> Exam:
    """Professor: must own the exam's course. TA: read/review only, must be assigned."""
    exam = await db.get(Exam, exam_id)
    if not exam:
        raise _not_found("Exam")
    if user.role == UserRole.PROFESSOR:
        course = await db.get(Course, exam.course_id)
        if not course or course.professor_id != user.id:
            raise _not_found("Exam")
        return exam
    assigned = await db.scalar(
        select(Exam.id).where(Exam.id == exam_id, Exam.id.in_(ta_exam_ids(user)))
    )
    if not assigned:
        raise _not_found("Exam")
    if manage:
        raise _forbidden("Only the course professor can do this")
    return exam


async def require_submission_access(
    db: AsyncSession,
    submission_id: uuid.UUID,
    user: User | None,
    *,
    manage: bool = False,
    lock: bool = False,
) -> StudentSubmission:
    """Load a submission the caller may read (``manage``: professor-only write).

    ``lock=True`` takes a row lock (SELECT … FOR UPDATE) to serialise concurrent
    review actions on the same submission.
    """
    query = select(StudentSubmission).where(StudentSubmission.id == submission_id)
    if lock:
        query = query.with_for_update()
    submission = (await db.execute(query)).scalar_one_or_none()
    if not submission:
        raise _not_found("Submission")
    if user is None:
        return submission
    visible = await db.scalar(
        select(StudentSubmission.id).where(
            StudentSubmission.id == submission_id, submission_scope(user)
        )
    )
    if not visible:
        raise _not_found("Submission")
    if manage and user.role != UserRole.PROFESSOR:
        raise _forbidden("Only the course professor can do this")
    return submission


async def require_rubric_access(
    db: AsyncSession, rubric_id: uuid.UUID, user: User | None, *, manage: bool = False
) -> Rubric:
    """Professor: rubric owner (or rubric of an exam they own). TA: read-only via assignment."""
    rubric = await db.get(Rubric, rubric_id)
    if not rubric:
        raise _not_found("Rubric")
    if user is None:
        return rubric
    if user.role == UserRole.PROFESSOR:
        if rubric.owner_id == user.id:
            return rubric
        used_in_own_exam = await db.scalar(
            select(Exam.id).where(Exam.rubric_id == rubric_id, exam_scope(user)).limit(1)
        )
        if used_in_own_exam and not manage:
            return rubric
        if used_in_own_exam and manage:
            raise _forbidden("Only the rubric owner can modify it")
        raise _not_found("Rubric")
    used_in_assigned_exam = await db.scalar(
        select(Exam.id).where(Exam.rubric_id == rubric_id, exam_scope(user)).limit(1)
    )
    if not used_in_assigned_exam:
        raise _not_found("Rubric")
    if manage:
        raise _forbidden("TAs cannot modify rubrics")
    return rubric


async def require_batch_job_access(
    db: AsyncSession, job_id: uuid.UUID, user: User | None
) -> BatchJob:
    job = await db.get(BatchJob, job_id)
    if not job:
        raise _not_found("Batch job")
    if user is None:
        return job
    if user.role != UserRole.PROFESSOR:
        raise _not_found("Batch job")
    if job.created_by == user.id:
        return job
    if job.exam_id:
        exam = await db.get(Exam, job.exam_id)
        course = await db.get(Course, exam.course_id) if exam else None
        if course and course.professor_id == user.id:
            return job
    raise _not_found("Batch job")
