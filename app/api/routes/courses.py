"""Courses, rosters and course staff (TAs)."""

import csv
import io
import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import ProfessorUser, StaffUser
from app.api.permissions import course_scope, require_course_access
from app.core.security import hash_password
from app.db import crud
from app.db.models import (
    Course,
    CourseMember,
    CourseStatus,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamTA,
    Student,
    StudentSubmission,
    UserRole,
)
from app.db.session import get_db
from app.schemas.academic import (
    CourseCreate,
    CourseResponse,
    CourseUpdate,
    StudentImportRequest,
    StudentImportResponse,
    StudentIn,
    StudentResponse,
    TAAddRequest,
    TAWorkload,
)
from app.schemas.dashboard import ActivityItem, CourseAnalyticsResponse
from app.services.academic import build_course_responses
from app.services.activity import recent_activity
from app.services.analytics_service import course_analytics
from app.services.staff import ta_workloads

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CSV_BYTES = 2 * 1024 * 1024


async def _course_response(db: AsyncSession, course: Course) -> CourseResponse:
    return (await build_course_responses(db, [course]))[0]


def _ensure_active(course: Course) -> None:
    if course.status == CourseStatus.ARCHIVED:
        raise HTTPException(status_code=409, detail="Course is archived; unarchive it first")


@router.get("", response_model=list[CourseResponse])
async def list_courses(
    user: StaffUser,
    status_filter: Literal["active", "archived", "all"] = Query("active", alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[CourseResponse]:
    q = select(Course).where(course_scope(user)).order_by(Course.created_at.desc())
    if status_filter != "all":
        q = q.where(Course.status == CourseStatus(status_filter))
    courses = list((await db.execute(q)).scalars())
    return await build_course_responses(db, courses)


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    body: CourseCreate, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> CourseResponse:
    course = Course(**body.model_dump(), professor_id=user.id, status=CourseStatus.ACTIVE)
    db.add(course)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="You already have this course code for that semester and year"
        ) from exc
    return await _course_response(db, course)


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: uuid.UUID, user: StaffUser, db: AsyncSession = Depends(get_db)
) -> CourseResponse:
    course = await require_course_access(db, course_id, user)
    return await _course_response(db, course)


@router.patch("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: uuid.UUID, body: CourseUpdate, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> CourseResponse:
    course = await require_course_access(db, course_id, user, manage=True)
    data = body.model_dump(exclude_unset=True)
    if "course_code" in data and data["course_code"]:
        data["course_code"] = data["course_code"].strip().upper()
    for key, value in data.items():
        setattr(course, key, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Duplicate course offering") from exc
    await db.refresh(course)
    return await _course_response(db, course)


@router.delete("/{course_id}", response_model=CourseResponse)
async def archive_course(
    course_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> CourseResponse:
    """Archive (soft-delete). Grades and audit history are never hard-deleted."""
    course = await require_course_access(db, course_id, user, manage=True)
    course.status = CourseStatus.ARCHIVED
    await db.flush()
    await db.refresh(course)
    return await _course_response(db, course)


# --- Students ---------------------------------------------------------------------------


@router.get("/{course_id}/students", response_model=list[StudentResponse])
async def list_students(
    course_id: uuid.UUID,
    user: ProfessorUser,
    include_dropped: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[StudentResponse]:
    await require_course_access(db, course_id, user, manage=True)
    q = (
        select(Student, Enrollment)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course_id)
        .order_by(Student.student_id)
    )
    if not include_dropped:
        q = q.where(Enrollment.status == EnrollmentStatus.ACTIVE)
    return [
        StudentResponse(
            id=s.id,
            student_id=s.student_id,
            name=s.name,
            email=s.email,
            enrollment_status=e.status,
            enrolled_at=e.created_at,
        )
        for s, e in (await db.execute(q)).all()
    ]


async def import_students(
    db: AsyncSession, course_id: uuid.UUID, students: list[StudentIn]
) -> StudentImportResponse:
    result = StudentImportResponse(created=0, enrolled=0, already_enrolled=0)
    seen: set[str] = set()
    for item in students:
        sid = item.student_id.strip()
        if sid in seen:
            result.errors.append(f"{sid}: listed more than once")
            continue
        seen.add(sid)
        student = await db.scalar(select(Student).where(Student.student_id == sid))
        if student is None:
            student = Student(student_id=sid, name=item.name.strip(), email=item.email)
            db.add(student)
            await db.flush()
            result.created += 1
        else:
            # Student records are shared across courses: only fill blanks, never
            # overwrite details another course may rely on.
            if not student.name and item.name:
                student.name = item.name.strip()
            if not student.email and item.email:
                student.email = item.email
        enrollment = await db.scalar(
            select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.student_id == student.id)
        )
        if enrollment is None:
            db.add(Enrollment(course_id=course_id, student_id=student.id, status=EnrollmentStatus.ACTIVE))
            result.enrolled += 1
        elif enrollment.status == EnrollmentStatus.DROPPED:
            enrollment.status = EnrollmentStatus.ACTIVE
            result.reactivated += 1
        else:
            result.already_enrolled += 1
    await db.flush()
    return result


@router.post("/{course_id}/students", response_model=StudentImportResponse)
async def add_students(
    course_id: uuid.UUID,
    body: StudentImportRequest,
    user: ProfessorUser,
    db: AsyncSession = Depends(get_db),
) -> StudentImportResponse:
    course = await require_course_access(db, course_id, user, manage=True)
    _ensure_active(course)
    return await import_students(db, course_id, body.students)


@router.post("/{course_id}/students/import-csv", response_model=StudentImportResponse)
async def import_students_csv(
    course_id: uuid.UUID,
    user: ProfessorUser,
    file: UploadFile = File(..., description="CSV with columns student_id,name,email"),
    db: AsyncSession = Depends(get_db),
) -> StudentImportResponse:
    course = await require_course_access(db, course_id, user, manage=True)
    _ensure_active(course)
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(status_code=413, detail="CSV too large (2 MB max)")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text))
    fields = {f.strip().lower() for f in (reader.fieldnames or [])}
    if "student_id" not in fields:
        raise HTTPException(status_code=400, detail="CSV needs a 'student_id' header column")
    students: list[StudentIn] = []
    errors: list[str] = []
    for line_no, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        try:
            students.append(
                StudentIn(student_id=row.get("student_id", ""), name=row.get("name", ""), email=row.get("email") or None)
            )
        except ValidationError as exc:
            errors.append(f"line {line_no}: {exc.errors()[0]['msg']}")
    if not students:
        raise HTTPException(status_code=400, detail="No valid student rows found")
    result = await import_students(db, course_id, students)
    result.errors = errors + result.errors
    return result


@router.delete("/{course_id}/students/{student_record_id}", status_code=204)
async def drop_student(
    course_id: uuid.UUID,
    student_record_id: uuid.UUID,
    user: ProfessorUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    await require_course_access(db, course_id, user, manage=True)
    enrollment = await db.scalar(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.student_id == student_record_id
        )
    )
    if not enrollment:
        raise HTTPException(status_code=404, detail="Student not enrolled")
    enrollment.status = EnrollmentStatus.DROPPED
    return Response(status_code=204)


# --- TAs ------------------------------------------------------------------------------


@router.get("/{course_id}/tas", response_model=list[TAWorkload])
async def list_course_tas(
    course_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> list[TAWorkload]:
    await require_course_access(db, course_id, user, manage=True)
    return await ta_workloads(db, course_id)


@router.post("/{course_id}/tas", response_model=TAWorkload, status_code=201)
async def add_course_ta(
    course_id: uuid.UUID, body: TAAddRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> TAWorkload:
    course = await require_course_access(db, course_id, user, manage=True)
    _ensure_active(course)
    ta = await crud.get_user_by_email(db, body.email)
    if ta is None:
        if not body.password:
            raise HTTPException(
                status_code=404,
                detail="No account with that email. Ask the TA to register, or provide a password to create one.",
            )
        ta = await crud.create_user(
            db,
            email=body.email,
            hashed_password=hash_password(body.password),
            full_name=body.full_name or body.email.split("@")[0],
            role=UserRole.TA,
        )
    elif ta.role != UserRole.TA:
        raise HTTPException(status_code=400, detail="That account is not a TA account")
    elif not ta.is_active:
        raise HTTPException(status_code=400, detail="That TA account is disabled")

    member = await db.scalar(
        select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == ta.id)
    )
    if member is None:
        db.add(CourseMember(course_id=course_id, user_id=ta.id, role=UserRole.TA, active=True))
    elif member.active:
        raise HTTPException(status_code=409, detail="TA is already on this course")
    else:
        member.active = True
    await db.flush()
    workloads = await ta_workloads(db, course_id)
    return next(w for w in workloads if w.user.id == ta.id)


@router.delete("/{course_id}/tas/{user_id}", status_code=204)
async def remove_course_ta(
    course_id: uuid.UUID, user_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> Response:
    """Deactivate a TA on the course and all its exams. Their audit history is kept."""
    await require_course_access(db, course_id, user, manage=True)
    member = await db.scalar(
        select(CourseMember).where(CourseMember.course_id == course_id, CourseMember.user_id == user_id)
    )
    if not member or not member.active:
        raise HTTPException(status_code=404, detail="TA not on this course")
    member.active = False
    course_exam_ids = select(Exam.id).where(Exam.course_id == course_id)
    await db.execute(
        update(ExamTA)
        .where(ExamTA.ta_id == user_id, ExamTA.exam_id.in_(course_exam_ids))
        .values(active=False)
    )
    # Release per-submission assignments so the work returns to the shared queue.
    await db.execute(
        update(StudentSubmission)
        .where(StudentSubmission.assigned_ta_id == user_id, StudentSubmission.exam_id.in_(course_exam_ids))
        .values(assigned_ta_id=None)
    )
    return Response(status_code=204)


@router.get("/{course_id}/analytics", response_model=CourseAnalyticsResponse)
async def get_course_analytics(
    course_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> CourseAnalyticsResponse:
    await require_course_access(db, course_id, user, manage=True)
    return await course_analytics(db, course_id)


@router.get("/{course_id}/activity", response_model=list[ActivityItem])
async def get_course_activity(
    course_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> list[ActivityItem]:
    """Recent review and exam events for this course, from the audit tables."""
    await require_course_access(db, course_id, user, manage=True)
    return await recent_activity(db, exam_filter=Exam.course_id == course_id, limit=20)
