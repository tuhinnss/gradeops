"""Exams: setup, rubric, submissions, AI processing, TA assignment, finalisation."""

import json
import logging
import re
import uuid
from itertools import cycle
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import ProfessorUser, StaffUser
from app.api.permissions import exam_scope, require_course_access, require_exam_access, submission_scope
from app.config import get_settings
from app.core.exceptions import RubricParseError
from app.db import crud
from app.db.models import (
    TA_QUEUE_STATUSES,
    BatchJob,
    CourseMember,
    CourseStatus,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamAudit,
    ExamStatus,
    ExamTA,
    ReviewStatus,
    Rubric,
    Student,
    StudentSubmission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.db.session import async_session_factory, get_db
from app.schemas.academic import (
    DistributeRequest,
    DistributeResponse,
    EvaluateExamRequest,
    ExamAuditItem,
    ExamCreate,
    ExamDetailResponse,
    ExamResponse,
    ExamRubricLink,
    ExamTAAssign,
    ExamUpdate,
    FinalizationSummary,
    MappingItemResult,
    MappingValidateRequest,
    MappingValidateResponse,
    PublishRequest,
    ReopenRequest,
    RubricDetail,
    SubmissionListResponse,
    SubmissionUploadItem,
    SubmissionUploadResponse,
    UserSummary,
    ExamTransitionRequest,
)
from app.schemas.batch import BatchJobResponse
from app.schemas.dashboard import ExamAnalyticsResponse, GradebookResponse, IntegrityFlagResponse
from app.schemas.rubric import RubricSchema
from app.services import finalization
from app.services.academic import (
    build_exam_responses,
    build_submission_rows,
    rubric_summary,
    user_summary,
    users_by_id,
)
from app.services.analytics_service import exam_analytics
from app.services.batch_queue import enqueue_batch_job, recover_interrupted_exam
from app.services.exam_workflow import add_exam_audit, mark_exam_processing
from app.services.integrity import list_integrity_flags
from app.services.rubric_parser import RubricParser
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()
storage = StorageService()

SETUP_STATUSES = (ExamStatus.DRAFT, ExamStatus.TA_REVIEW)


async def _detail(db: AsyncSession, exam: Exam, user: User) -> ExamDetailResponse:
    base = (await build_exam_responses(db, [exam], ExamDetailResponse))[0]
    if user.role != UserRole.PROFESSOR:
        return base
    job = await db.scalar(
        select(BatchJob).where(BatchJob.exam_id == exam.id).order_by(BatchJob.created_at.desc()).limit(1)
    )
    from app.api.routes.bulk import job_response

    audits = list(
        (
            await db.execute(
                select(ExamAudit).where(ExamAudit.exam_id == exam.id).order_by(ExamAudit.created_at.desc()).limit(50)
            )
        ).scalars()
    )
    actors = await users_by_id(db, (a.actor_id for a in audits))
    base.latest_job = job_response(job) if job else None
    base.audit = [
        ExamAuditItem(
            id=a.id,
            action=a.action,
            actor=user_summary(actors.get(a.actor_id)) if a.actor_id else None,
            from_status=a.from_status,
            to_status=a.to_status,
            notes=a.notes,
            details=a.details,
            created_at=a.created_at,
        )
        for a in audits
    ]
    return base


# --- Exams CRUD -------------------------------------------------------------------------


@router.get("", response_model=list[ExamResponse])
async def list_exams(
    user: StaffUser,
    course_id: uuid.UUID | None = None,
    exam_status: ExamStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[ExamResponse]:
    q = select(Exam).where(exam_scope(user)).order_by(Exam.created_at.desc())
    if course_id:
        q = q.where(Exam.course_id == course_id)
    if exam_status:
        q = q.where(Exam.status == exam_status)
    return await build_exam_responses(db, list((await db.execute(q)).scalars()))


@router.post("", response_model=ExamDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_exam(body: ExamCreate, user: ProfessorUser, db: AsyncSession = Depends(get_db)) -> ExamDetailResponse:
    course = await require_course_access(db, body.course_id, user, manage=True)
    if course.status != CourseStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Cannot add exams to an archived course")
    if body.rubric_id:
        rubric = await db.get(Rubric, body.rubric_id)
        if not rubric or rubric.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Rubric not found")
    exam = Exam(**body.model_dump(), created_by=user.id, status=ExamStatus.DRAFT)
    db.add(exam)
    await db.flush()
    await add_exam_audit(db, exam, action="created", actor_id=user.id)
    await db.refresh(exam)
    return await _detail(db, exam, user)


@router.get("/{exam_id}", response_model=ExamDetailResponse)
async def get_exam(exam_id: uuid.UUID, user: StaffUser, db: AsyncSession = Depends(get_db)) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user)
    if exam.status == ExamStatus.PROCESSING:
        await recover_interrupted_exam(db, exam.id)
    return await _detail(db, exam, user)


@router.patch("/{exam_id}", response_model=ExamDetailResponse)
async def update_exam(
    exam_id: uuid.UUID, body: ExamUpdate, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    finalization.ensure_exam_editable(exam)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(exam, key, value)
    await db.flush()
    await db.refresh(exam)
    return await _detail(db, exam, user)


# --- Rubric -----------------------------------------------------------------------------


def _ensure_rubric_changeable(exam: Exam) -> None:
    if exam.status not in SETUP_STATUSES:
        raise HTTPException(status_code=409, detail=f"Cannot change the rubric while the exam is {exam.status.value}")


@router.get("/{exam_id}/rubric", response_model=RubricDetail)
async def get_exam_rubric(exam_id: uuid.UUID, user: StaffUser, db: AsyncSession = Depends(get_db)) -> RubricDetail:
    exam = await require_exam_access(db, exam_id, user)
    rubric = await db.get(Rubric, exam.rubric_id) if exam.rubric_id else None
    if not rubric:
        raise HTTPException(status_code=404, detail="Exam has no rubric yet")
    summary = rubric_summary(rubric)
    return RubricDetail(**summary.model_dump(), structured_data=RubricSchema.from_dict(rubric.structured_data))


@router.post("/{exam_id}/rubric", response_model=ExamDetailResponse)
async def upload_exam_rubric(
    exam_id: uuid.UUID,
    user: ProfessorUser,
    file: UploadFile = File(..., description="Marking scheme JSON or PDF"),
    name: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    _ensure_rubric_changeable(exam)
    filename = Path(file.filename or "").name
    lower = filename.lower()
    if not (lower.endswith(".json") or lower.endswith(".pdf")):
        raise HTTPException(status_code=400, detail="Rubric must be .json or .pdf")
    content = await file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.max_upload_mb}MB limit")
    source_type = "json" if lower.endswith(".json") else "pdf"
    dest = storage.save_upload_file(content, "rubrics", f"{uuid.uuid4()}_{filename}")
    try:
        schema = RubricParser().parse_file(dest, source_type)
    except RubricParseError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc
    if not schema.items:
        raise HTTPException(status_code=400, detail="No questions found in the rubric")
    rubric = await crud.create_rubric(
        db,
        name=name or f"{exam.name} rubric",
        source_filename=filename,
        source_type=source_type,
        structured_data=schema.to_dict(),
        file_path=str(dest),
        owner_id=user.id,
    )
    previous = exam.rubric_id
    exam.rubric_id = rubric.id
    await add_exam_audit(
        db, exam, action="rubric_uploaded", actor_id=user.id,
        details={"rubric_id": str(rubric.id), "previous_rubric_id": str(previous) if previous else None,
                 "questions": len(schema.items)},
    )
    await db.flush()
    return await _detail(db, exam, user)


@router.put("/{exam_id}/rubric", response_model=ExamDetailResponse)
async def link_exam_rubric(
    exam_id: uuid.UUID, body: ExamRubricLink, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    _ensure_rubric_changeable(exam)
    rubric = await db.get(Rubric, body.rubric_id)
    if not rubric or rubric.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Rubric not found")
    exam.rubric_id = rubric.id
    await add_exam_audit(db, exam, action="rubric_linked", actor_id=user.id, details={"rubric_id": str(rubric.id)})
    await db.flush()
    return await _detail(db, exam, user)


# --- TA assignment ---------------------------------------------------------------------


async def _exam_ta_list(db: AsyncSession, exam_id: uuid.UUID) -> list[UserSummary]:
    rows = (
        await db.execute(
            select(User)
            .join(ExamTA, ExamTA.ta_id == User.id)
            .where(ExamTA.exam_id == exam_id, ExamTA.active.is_(True))
            .order_by(User.full_name)
        )
    ).scalars()
    return [user_summary(u) for u in rows]


@router.post("/{exam_id}/tas", response_model=list[UserSummary])
async def assign_exam_ta(
    exam_id: uuid.UUID, body: ExamTAAssign, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> list[UserSummary]:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    member = await db.scalar(
        select(CourseMember).where(
            CourseMember.course_id == exam.course_id,
            CourseMember.user_id == body.ta_id,
            CourseMember.active.is_(True),
            CourseMember.role == UserRole.TA,
        )
    )
    if not member:
        raise HTTPException(status_code=400, detail="Add this TA to the course before assigning exams")
    row = await db.scalar(select(ExamTA).where(ExamTA.exam_id == exam_id, ExamTA.ta_id == body.ta_id))
    if row is None:
        db.add(ExamTA(exam_id=exam_id, ta_id=body.ta_id, active=True))
    else:
        row.active = True
    await add_exam_audit(db, exam, action="ta_assigned", actor_id=user.id, details={"ta_id": str(body.ta_id)})
    await db.flush()
    return await _exam_ta_list(db, exam_id)


@router.delete("/{exam_id}/tas/{ta_id}", response_model=list[UserSummary])
async def unassign_exam_ta(
    exam_id: uuid.UUID, ta_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> list[UserSummary]:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    row = await db.scalar(select(ExamTA).where(ExamTA.exam_id == exam_id, ExamTA.ta_id == ta_id))
    if not row or not row.active:
        raise HTTPException(status_code=404, detail="TA is not assigned to this exam")
    row.active = False
    subs = (
        await db.execute(
            select(StudentSubmission).where(
                StudentSubmission.exam_id == exam_id, StudentSubmission.assigned_ta_id == ta_id
            )
        )
    ).scalars()
    for sub in subs:
        sub.assigned_ta_id = None
    await add_exam_audit(db, exam, action="ta_unassigned", actor_id=user.id, details={"ta_id": str(ta_id)})
    await db.flush()
    return await _exam_ta_list(db, exam_id)


@router.post("/{exam_id}/distribute", response_model=DistributeResponse)
async def distribute_submissions(
    exam_id: uuid.UUID, body: DistributeRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> DistributeResponse:
    """Round-robin submissions awaiting review across the exam's TAs."""
    exam = await require_exam_access(db, exam_id, user, manage=True)
    finalization.ensure_exam_editable(exam)
    tas = [u.id for u in await _exam_ta_list(db, exam_id)]
    if body.ta_ids:
        unknown = set(body.ta_ids) - set(tas)
        if unknown:
            raise HTTPException(status_code=400, detail="Some TAs are not assigned to this exam")
        tas = list(body.ta_ids)
    if not tas:
        raise HTTPException(status_code=400, detail="Assign at least one TA to the exam first")
    q = select(StudentSubmission).where(
        StudentSubmission.exam_id == exam_id,
        StudentSubmission.review_status.in_((ReviewStatus.NOT_EVALUATED, *TA_QUEUE_STATUSES)),
    ).order_by(StudentSubmission.student_id)
    if not body.rebalance:
        q = q.where(StudentSubmission.assigned_ta_id.is_(None))
    subs = list((await db.execute(q)).scalars())
    assigned: dict[str, int] = {str(t): 0 for t in tas}
    for sub, ta_id in zip(subs, cycle(tas)):
        sub.assigned_ta_id = ta_id
        assigned[str(ta_id)] += 1
    await add_exam_audit(db, exam, action="distributed", actor_id=user.id, details={"assigned": assigned})
    return DistributeResponse(assigned=assigned, total=len(subs))


# --- Submissions -----------------------------------------------------------------------


@router.get("/{exam_id}/submissions", response_model=SubmissionListResponse)
async def list_exam_submissions(
    exam_id: uuid.UUID,
    user: StaffUser,
    review_status: ReviewStatus | None = None,
    processing_status: SubmissionStatus | None = Query(None, alias="status"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> SubmissionListResponse:
    await require_exam_access(db, exam_id, user)
    conditions = [StudentSubmission.exam_id == exam_id, submission_scope(user)]
    if review_status:
        conditions.append(StudentSubmission.review_status == review_status)
    if processing_status:
        conditions.append(StudentSubmission.status == processing_status)
    total = await db.scalar(select(func.count()).select_from(StudentSubmission).where(*conditions)) or 0
    subs = list(
        (
            await db.execute(
                select(StudentSubmission)
                .where(*conditions)
                .order_by(StudentSubmission.student_id, StudentSubmission.created_at)
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
    )
    return SubmissionListResponse(items=await build_submission_rows(db, subs), total=total)


def infer_student_id(filename: str, roster: set[str]) -> str | None:
    """Student ID from a filename: an enrolled ID appearing in it, else its first token."""
    stem = Path(filename).stem
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", stem) if t]
    for token in tokens:
        if token in roster:
            return token
    for sid in sorted(roster, key=len, reverse=True):
        if len(sid) >= 4 and sid in stem:
            return sid
    return tokens[0] if tokens else None


async def _roster(db: AsyncSession, course_id: uuid.UUID) -> dict[str, Student]:
    rows = (
        await db.execute(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.course_id == course_id, Enrollment.status == EnrollmentStatus.ACTIVE)
        )
    ).scalars()
    return {s.student_id: s for s in rows}


async def _existing_student_ids(db: AsyncSession, exam_id: uuid.UUID) -> set[str]:
    return set(
        (await db.execute(select(StudentSubmission.student_id).where(StudentSubmission.exam_id == exam_id))).scalars()
    )


def _validate_mapping(
    items: list[tuple[str, str | None]], roster: dict[str, Student], existing: set[str], auto_enroll: bool
) -> list[MappingItemResult]:
    results: list[MappingItemResult] = []
    seen: set[str] = set()
    for filename, given in items:
        sid = (given or "").strip() or infer_student_id(filename, set(roster))
        if not filename.lower().endswith(".pdf"):
            results.append(MappingItemResult(filename=filename, student_id=sid, status="invalid", message="Not a PDF"))
            continue
        if not sid or not re.fullmatch(r"[A-Za-z0-9_.\-]{1,128}", sid):
            results.append(
                MappingItemResult(filename=filename, student_id=sid, status="invalid", message="Could not determine a valid student ID")
            )
            continue
        if sid in seen:
            results.append(MappingItemResult(filename=filename, student_id=sid, status="duplicate_in_upload", message="Same student twice in this upload"))
            continue
        seen.add(sid)
        if sid in existing:
            results.append(MappingItemResult(filename=filename, student_id=sid, status="already_submitted", message="Student already has a submission for this exam"))
            continue
        student = roster.get(sid)
        if student is None and not auto_enroll:
            results.append(MappingItemResult(filename=filename, student_id=sid, status="not_enrolled", message="Not on the course roster"))
            continue
        results.append(
            MappingItemResult(filename=filename, student_id=sid, student_name=student.name if student else None, status="ok")
        )
    return results


@router.post("/{exam_id}/submissions/validate", response_model=MappingValidateResponse)
async def validate_submission_mapping(
    exam_id: uuid.UUID,
    body: MappingValidateRequest,
    user: ProfessorUser,
    auto_enroll: bool = False,
    db: AsyncSession = Depends(get_db),
) -> MappingValidateResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    results = _validate_mapping(
        [(i.filename, i.student_id) for i in body.items],
        await _roster(db, exam.course_id),
        await _existing_student_ids(db, exam_id),
        auto_enroll,
    )
    ok = sum(1 for r in results if r.status == "ok")
    return MappingValidateResponse(items=results, ok=ok, problems=len(results) - ok)


@router.post("/{exam_id}/submissions", response_model=SubmissionUploadResponse)
async def upload_exam_submissions(
    exam_id: uuid.UUID,
    user: ProfessorUser,
    files: list[UploadFile] = File(..., description="Answer-sheet PDFs"),
    student_ids: str | None = Form(None, description="JSON list of student IDs aligned with files"),
    auto_enroll: bool = Form(False),
    db: AsyncSession = Depends(get_db),
) -> SubmissionUploadResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    if exam.status not in SETUP_STATUSES:
        raise HTTPException(status_code=409, detail=f"Cannot upload while the exam is {exam.status.value}")
    given: list[str | None] = [None] * len(files)
    if student_ids:
        try:
            parsed = json.loads(student_ids)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="student_ids must be a JSON list") from exc
        if not isinstance(parsed, list) or len(parsed) != len(files):
            raise HTTPException(status_code=400, detail="student_ids must list one ID per file")
        given = [str(x).strip() if x else None for x in parsed]

    roster = await _roster(db, exam.course_id)
    mapping = _validate_mapping(
        [(Path(f.filename or "").name, g) for f, g in zip(files, given, strict=True)],
        roster,
        await _existing_student_ids(db, exam_id),
        auto_enroll,
    )
    response = SubmissionUploadResponse(uploaded=[])
    for upload, result in zip(files, mapping, strict=True):
        if result.status != "ok":
            response.failed.append({"filename": result.filename, "student_id": result.student_id, "error": result.message})
            continue
        content = await upload.read(settings.max_upload_bytes + 1)
        if len(content) > settings.max_upload_bytes:
            response.failed.append({"filename": result.filename, "error": "File exceeds size limit"})
            continue
        if not content.startswith(b"%PDF"):
            response.failed.append({"filename": result.filename, "error": "File is not a valid PDF"})
            continue
        student = roster.get(result.student_id)
        if student is None:  # auto_enroll
            student = await db.scalar(select(Student).where(Student.student_id == result.student_id))
            if student is None:
                student = Student(student_id=result.student_id, name="")
                db.add(student)
                await db.flush()
            db.add(Enrollment(course_id=exam.course_id, student_id=student.id, status=EnrollmentStatus.ACTIVE))
            roster[student.student_id] = student
            response.warnings.append(f"{result.student_id} was added to the course roster")
        dest = storage.save_upload_file(content, "submissions", f"{uuid.uuid4()}_{result.filename}")
        sub = await crud.create_submission(
            db,
            student_id=result.student_id,
            source_filename=result.filename,
            file_path=str(dest),
            rubric_id=exam.rubric_id,
            uploaded_by=user.id,
            course_id=exam.course_id,
            exam_id=exam.id,
            student_record_id=student.id,
        )
        response.uploaded.append(
            SubmissionUploadItem(id=sub.id, student_id=sub.student_id, student_name=student.name or None, filename=result.filename)
        )
    if response.uploaded:
        await add_exam_audit(db, exam, action="submissions_uploaded", actor_id=user.id, details={"count": len(response.uploaded)})
    return response


@router.delete("/{exam_id}/submissions/{submission_id}", status_code=204)
async def delete_exam_submission(
    exam_id: uuid.UUID, submission_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> Response:
    """Remove a mis-uploaded sheet. Human-reviewed work is never deleted (audit trail)."""
    exam = await require_exam_access(db, exam_id, user, manage=True)
    finalization.ensure_exam_editable(exam)
    sub = await db.get(StudentSubmission, submission_id)
    if not sub or sub.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="Submission not found")
    if sub.review_status not in (ReviewStatus.NOT_EVALUATED, ReviewStatus.AI_EVALUATED):
        raise HTTPException(status_code=409, detail="Submissions with human review history cannot be deleted")
    if sub.status == SubmissionStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Submission is being processed")
    await db.delete(sub)
    await add_exam_audit(
        db, exam, action="submission_deleted", actor_id=user.id,
        details={"submission_id": str(submission_id), "student_id": sub.student_id},
    )
    return Response(status_code=204)


# --- Processing -------------------------------------------------------------------------


@router.post("/{exam_id}/evaluate", response_model=BatchJobResponse)
async def evaluate_exam(
    exam_id: uuid.UUID, body: EvaluateExamRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> BatchJobResponse:
    """Run OCR → segmentation → evaluation → similarity check as a batch job."""
    from app.api.routes.bulk import job_response

    exam = await require_exam_access(db, exam_id, user, manage=True)
    if exam.status == ExamStatus.PROCESSING and not await recover_interrupted_exam(db, exam.id):
        raise HTTPException(status_code=409, detail="Evaluation is already running for this exam")
    if exam.status not in SETUP_STATUSES:
        raise HTTPException(status_code=409, detail=f"Exam is {exam.status.value}; reopen it before re-evaluating")
    if not exam.rubric_id:
        raise HTTPException(status_code=400, detail="Upload or link a rubric first")
    q = select(StudentSubmission).where(StudentSubmission.exam_id == exam_id)
    if not body.reevaluate:
        q = q.where(StudentSubmission.status != SubmissionStatus.EVALUATED)
    subs = list((await db.execute(q)).scalars())
    if not subs:
        raise HTTPException(status_code=400, detail="No submissions to evaluate")
    job = await crud.create_batch_job(
        db,
        rubric_id=exam.rubric_id,
        submission_ids=[str(s.id) for s in subs],
        run_plagiarism=body.run_plagiarism_check,
        created_by=user.id,
        exam_id=exam.id,
    )
    for sub in subs:
        sub.batch_job_id = job.id
        sub.rubric_id = exam.rubric_id
    await mark_exam_processing(db, exam, user.id, len(subs))
    # Commit before the background worker opens its own session.
    await db.commit()
    enqueue_batch_job(job.id, async_session_factory)
    return job_response(job)


# --- Finalisation ----------------------------------------------------------------------


@router.get("/{exam_id}/publish-summary", response_model=FinalizationSummary)
async def publish_summary(exam_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)) -> FinalizationSummary:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    return await finalization.finalization_summary(db, exam)


@router.post("/{exam_id}/approve", response_model=ExamDetailResponse)
async def approve_exam(
    exam_id: uuid.UUID, body: ExamTransitionRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    await finalization.approve_exam(db, exam, user, body.notes)
    await db.flush()
    return await _detail(db, exam, user)


@router.post("/{exam_id}/lock", response_model=ExamDetailResponse)
async def lock_exam(
    exam_id: uuid.UUID, body: ExamTransitionRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    await finalization.lock_exam(db, exam, user, body.notes)
    await db.flush()
    return await _detail(db, exam, user)


@router.post("/{exam_id}/publish", response_model=ExamDetailResponse)
async def publish_exam(
    exam_id: uuid.UUID, body: PublishRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    await finalization.publish_exam(db, exam, user, body.notes, body.acknowledge_integrity_flags)
    await db.flush()
    return await _detail(db, exam, user)


@router.post("/{exam_id}/reopen", response_model=ExamDetailResponse)
async def reopen_exam(
    exam_id: uuid.UUID, body: ReopenRequest, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> ExamDetailResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    await finalization.reopen_exam(db, exam, user, body.reason)
    await db.flush()
    return await _detail(db, exam, user)


# --- Gradebook / analytics / integrity -------------------------------------------------


@router.get("/{exam_id}/gradebook", response_model=GradebookResponse)
async def get_gradebook(exam_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)) -> GradebookResponse:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    return await finalization.build_gradebook(db, exam)


@router.get("/{exam_id}/gradebook.csv")
async def export_gradebook(
    exam_id: uuid.UUID, user: ProfessorUser, final: bool = False, db: AsyncSession = Depends(get_db)
) -> Response:
    exam = await require_exam_access(db, exam_id, user, manage=True)
    gb = await finalization.build_gradebook(db, exam)
    if final and not gb.is_final:
        raise HTTPException(status_code=409, detail="Final gradebook is available once the exam is approved")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{gb.course_code}_{exam.name}").strip("_") or "gradebook"
    suffix = "final" if final else "provisional" if not gb.is_final else "gradebook"
    await add_exam_audit(db, exam, action="gradebook_exported", actor_id=user.id, details={"final": final})
    return Response(
        content=finalization.gradebook_csv(gb, final_only=final),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}_{suffix}.csv"'},
    )


@router.get("/{exam_id}/analytics", response_model=ExamAnalyticsResponse)
async def get_exam_analytics(exam_id: uuid.UUID, user: StaffUser, db: AsyncSession = Depends(get_db)) -> ExamAnalyticsResponse:
    """Professors get full analytics; TAs get cohort-level figures without per-student data."""
    exam = await require_exam_access(db, exam_id, user)
    return await exam_analytics(db, exam, include_students=user.role == UserRole.PROFESSOR)


@router.get("/{exam_id}/integrity", response_model=list[IntegrityFlagResponse])
async def get_exam_integrity(
    exam_id: uuid.UUID, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> list[IntegrityFlagResponse]:
    await require_exam_access(db, exam_id, user, manage=True)
    return await list_integrity_flags(db, user, exam_id=exam_id)
