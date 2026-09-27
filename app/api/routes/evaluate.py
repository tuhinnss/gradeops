"""Evaluation endpoints (professor only; TAs review, they do not run the pipeline)."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_pipeline
from app.api.deps_auth import ensure_professor, get_legacy_actor
from app.api.permissions import require_rubric_access, require_submission_access, submission_scope
from app.core.exceptions import GradeOpsError, http_error
from app.db import crud
from app.db.models import FROZEN_EXAM_STATUSES, Exam, StudentSubmission, User
from app.db.session import async_session_factory, get_db
from app.schemas.evaluation import (
    EvaluateAllRequest,
    EvaluateAllResponse,
    EvaluationResponse,
)
from app.schemas.rubric import RubricSchema
from app.schemas.upload import BatchEvaluateRequest, EvaluateRequest
from app.services.evaluate_all_queue import enqueue_evaluate_all, get_job
from app.services.pipeline import GradeOpsPipeline

logger = logging.getLogger(__name__)
router = APIRouter()


async def _resolve_rubric(
    db: AsyncSession, submission: StudentSubmission, rubric_id: uuid.UUID | None, user: User | None
) -> RubricSchema:
    """Rubric for a submission; exam submissions always use their exam's rubric."""
    exam = await db.get(Exam, submission.exam_id) if submission.exam_id else None
    if exam and exam.rubric_id:
        if rubric_id and rubric_id != exam.rubric_id:
            raise HTTPException(status_code=400, detail="Submission belongs to an exam with a different rubric")
        rid = exam.rubric_id
    else:
        rid = rubric_id or submission.rubric_id
    if not rid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="rubric_id required (not linked on submission)",
        )
    rubric = await require_rubric_access(db, rid, user)
    return RubricSchema.from_dict(rubric.structured_data)


async def _load_for_evaluation(
    db: AsyncSession, submission_id: uuid.UUID, user: User | None
) -> StudentSubmission:
    submission = await require_submission_access(db, submission_id, user, manage=True)
    if submission.exam_id:
        exam = await db.get(Exam, submission.exam_id)
        if exam and exam.status in FROZEN_EXAM_STATUSES:
            raise HTTPException(status_code=409, detail="Exam grades are locked; reopen the exam first")
    return submission


@router.post("/run", response_model=EvaluationResponse)
async def evaluate_submission(
    body: EvaluateRequest,
    db: AsyncSession = Depends(get_db),
    pipeline: GradeOpsPipeline = Depends(get_pipeline),
    user: User | None = Depends(get_legacy_actor),
) -> EvaluationResponse:
    ensure_professor(user)
    submission = await _load_for_evaluation(db, body.submission_id, user)
    rubric_schema = await _resolve_rubric(db, submission, body.rubric_id, user)

    try:
        await pipeline.process_submission_ocr(db, body.submission_id, rubric_schema)
        response = await pipeline.evaluate_submission(db, body.submission_id, rubric_schema)
    except GradeOpsError as exc:
        raise http_error(exc, 422) from exc

    if body.run_plagiarism_check:
        flags = await pipeline.run_plagiarism_check(db, [body.submission_id])
        response.plagiarism_flags = flags

    return response


@router.post("/batch", response_model=list[EvaluationResponse])
async def evaluate_batch(
    body: BatchEvaluateRequest,
    db: AsyncSession = Depends(get_db),
    pipeline: GradeOpsPipeline = Depends(get_pipeline),
    user: User | None = Depends(get_legacy_actor),
) -> list[EvaluationResponse]:
    ensure_professor(user)
    rubric = await require_rubric_access(db, body.rubric_id, user)
    rubric_schema = RubricSchema.from_dict(rubric.structured_data)
    for sid in body.submission_ids:
        submission = await _load_for_evaluation(db, sid, user)
        await _resolve_rubric(db, submission, body.rubric_id, user)

    responses: list[EvaluationResponse] = []
    for sid in body.submission_ids:
        try:
            await pipeline.process_submission_ocr(db, sid, rubric_schema)
            resp = await pipeline.evaluate_submission(db, sid, rubric_schema)
            responses.append(resp)
        except GradeOpsError as exc:
            logger.error("Batch evaluate failed for %s: %s", sid, exc)
            raise http_error(exc, 422) from exc

    if body.run_plagiarism_check and len(body.submission_ids) > 1:
        flags = await pipeline.run_plagiarism_check(db, body.submission_ids)
        for resp in responses:
            resp.plagiarism_flags = [
                f for f in flags
                if f.student_id_a == resp.student_id or f.student_id_b == resp.student_id
            ]

    return responses


@router.post("/all", response_model=EvaluateAllResponse)
async def evaluate_all(
    body: EvaluateAllRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> EvaluateAllResponse:
    """
    Evaluate all given submissions (or all linked to rubric) in the background.
    Poll GET /evaluate/all/{job_id} for progress.
    """
    ensure_professor(user)
    await require_rubric_access(db, body.rubric_id, user)

    if body.submission_ids:
        for sid in body.submission_ids:
            submission = await _load_for_evaluation(db, sid, user)
            await _resolve_rubric(db, submission, body.rubric_id, user)
        submission_ids = body.submission_ids
    else:
        subs = await crud.list_submissions(
            db, rubric_id=body.rubric_id, limit=500, scope=submission_scope(user)
        )
        submission_ids = [s.id for s in subs]

    if not submission_ids:
        return EvaluateAllResponse(
            status="completed",
            total_processed=0,
            success_count=0,
            failed_count=0,
        )

    job = enqueue_evaluate_all(
        rubric_id=body.rubric_id,
        submission_ids=submission_ids,
        run_plagiarism=body.run_plagiarism_check,
        session_factory=async_session_factory,
        created_by=user.id if user else None,
    )

    return EvaluateAllResponse(
        job_id=job.job_id,
        status=job.status.value,
        total_processed=job.total_processed,
        success_count=0,
        failed_count=0,
        current=0,
    )


@router.get("/all/{job_id}", response_model=EvaluateAllResponse)
async def get_evaluate_all_status(
    job_id: uuid.UUID, user: User | None = Depends(get_legacy_actor)
) -> EvaluateAllResponse:
    job = get_job(job_id)
    if not job or (user is not None and job.created_by != user.id):
        raise HTTPException(status_code=404, detail="Evaluate-all job not found")

    return EvaluateAllResponse(
        job_id=job.job_id,
        status=job.status.value,
        total_processed=job.total_processed,
        success_count=job.success_count,
        failed_count=job.failed_count,
        current=job.current,
        errors=job.errors,
    )


@router.post("/ocr/{submission_id}")
async def run_ocr_only(
    submission_id: uuid.UUID,
    rubric_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    pipeline: GradeOpsPipeline = Depends(get_pipeline),
    user: User | None = Depends(get_legacy_actor),
) -> dict:
    ensure_professor(user)
    submission = await _load_for_evaluation(db, submission_id, user)

    rubric_schema = None
    if rubric_id or submission.rubric_id or submission.exam_id:
        rubric_schema = await _resolve_rubric(db, submission, rubric_id, user)

    try:
        return await pipeline.process_submission_ocr(db, submission_id, rubric_schema)
    except GradeOpsError as exc:
        raise http_error(exc, 422) from exc
