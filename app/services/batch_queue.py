"""Async batch evaluation queue with DB-backed progress."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import crud
from app.db.models import BatchJob, BatchJobStatus, StudentSubmission, SubmissionStatus
from app.schemas.rubric import RubricSchema
from app.services.exam_workflow import finish_exam_processing, persist_integrity_flags
from app.services.pipeline import GradeOpsPipeline

logger = logging.getLogger(__name__)

_pipeline: GradeOpsPipeline | None = None
_running: set[uuid.UUID] = set()
_lock = asyncio.Lock()

ACTIVE_JOB_STATUSES = (BatchJobStatus.QUEUED, BatchJobStatus.RUNNING)
# Jobs run inside the API process. A queued/running job that is not running in
# this process and has recorded no progress for this long died with an earlier
# process (e.g. the API restarted mid-job); it would otherwise keep its exam in
# PROCESSING forever.
STALE_JOB_AFTER = timedelta(minutes=20)
INTERRUPTED_MESSAGE = "Interrupted before finishing (the API restarted); run the evaluation again"


def get_shared_pipeline() -> GradeOpsPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GradeOpsPipeline()
    return _pipeline


async def run_batch_job(
    job_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _lock:
        if job_id in _running:
            return
        _running.add(job_id)

    pipeline = get_shared_pipeline()
    try:
        async with session_factory() as session:
            job = await crud.get_batch_job(session, job_id)
            if not job:
                return
            await crud.update_batch_job(session, job, status=BatchJobStatus.RUNNING)
            await session.commit()

        rubric_schema: RubricSchema | None = None
        submission_ids: list[uuid.UUID] = []

        async with session_factory() as session:
            job = await crud.get_batch_job(session, job_id)
            if not job:
                return
            rubric = await crud.get_rubric(session, job.rubric_id)
            if not rubric:
                await crud.update_batch_job(
                    session, job, status=BatchJobStatus.FAILED, errors=[{"message": "Rubric not found"}]
                )
                if job.exam_id:
                    await finish_exam_processing(session, job.exam_id)
                await session.commit()
                return
            rubric_schema = RubricSchema.from_dict(rubric.structured_data)
            submission_ids = [uuid.UUID(str(s)) for s in (job.submission_ids or [])]

        completed = 0
        failed = 0
        errors: list[dict] = []

        sem = asyncio.Semaphore(2)

        async def process_one(sid: uuid.UUID) -> None:
            nonlocal completed, failed
            async with sem:
                async with session_factory() as session:
                    try:
                        await pipeline.process_submission_ocr(session, sid, rubric_schema)
                        # Sets review_status=AI_EVALUATED (awaiting human review).
                        await pipeline.evaluate_submission(session, sid, rubric_schema)
                        await session.commit()
                        completed += 1
                    except Exception as exc:
                        logger.exception("Batch item %s failed: %s", sid, exc)
                        failed += 1
                        errors.append({"submission_id": str(sid), "error": str(exc)})
                        await session.rollback()

                async with session_factory() as session:
                    job = await crud.get_batch_job(session, job_id)
                    if job:
                        await crud.update_batch_job(
                            session,
                            job,
                            completed_count=completed,
                            failed_count=failed,
                            errors=errors,
                        )
                        await session.commit()

        await asyncio.gather(*[process_one(sid) for sid in submission_ids])

        if rubric_schema and len(submission_ids) > 1:
            async with session_factory() as session:
                job = await crud.get_batch_job(session, job_id)
                if job and job.run_plagiarism:
                    flags = await pipeline.run_plagiarism_check(session, submission_ids, rubric_schema)
                    await crud.save_plagiarism_report(
                        session,
                        rubric_id=job.rubric_id,
                        flags=[f.model_dump() for f in flags],
                        batch_job_id=job_id,
                        exam_id=job.exam_id,
                    )
                    if job.exam_id:
                        await persist_integrity_flags(session, job.exam_id, flags)
                    for sid in submission_ids:
                        sub = await crud.get_submission(session, sid)
                        if not sub:
                            continue
                        related = [
                            f.similarity
                            for f in flags
                            if f.student_id_a == sub.student_id or f.student_id_b == sub.student_id
                        ]
                        if related:
                            await crud.update_submission(
                                session, sub, plagiarism_score=max(related)
                            )
                    await session.commit()

        async with session_factory() as session:
            job = await crud.get_batch_job(session, job_id)
            if job:
                status = BatchJobStatus.COMPLETED
                if completed == 0 and failed > 0:
                    status = BatchJobStatus.FAILED
                await crud.update_batch_job(
                    session,
                    job,
                    status=status,
                    completed_count=completed,
                    failed_count=failed,
                    errors=errors,
                )
                if job.exam_id:
                    await finish_exam_processing(session, job.exam_id)
                await session.commit()
    except Exception as exc:
        logger.exception("Batch job %s crashed: %s", job_id, exc)
        async with session_factory() as session:
            job = await crud.get_batch_job(session, job_id)
            if job:
                await crud.update_batch_job(
                    session,
                    job,
                    status=BatchJobStatus.FAILED,
                    errors=[*(job.errors or []), {"error": str(exc)}],
                )
                if job.exam_id:
                    await finish_exam_processing(session, job.exam_id)
                await session.commit()
    finally:
        _running.discard(job_id)


_tasks: set[asyncio.Task] = set()


def enqueue_batch_job(job_id: uuid.UUID, session_factory: async_sessionmaker) -> asyncio.Task:
    task = asyncio.create_task(run_batch_job(job_id, session_factory))
    # Keep a reference so the task is not garbage-collected mid-run.
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


def _is_interrupted(job: BatchJob, now: datetime) -> bool:
    if job.status not in ACTIVE_JOB_STATUSES or job.id in _running:
        return False
    last = job.updated_at or job.created_at
    return last is None or now - last >= STALE_JOB_AFTER


async def _fail_interrupted(session: AsyncSession, job: BatchJob) -> None:
    logger.warning("Batch job %s was interrupted; marking it failed", job.id)
    job.status = BatchJobStatus.FAILED
    job.errors = [*(job.errors or []), {"error": INTERRUPTED_MESSAGE}]
    ids = [uuid.UUID(str(s)) for s in (job.submission_ids or [])]
    if ids:
        await session.execute(
            update(StudentSubmission)
            .where(
                StudentSubmission.id.in_(ids),
                StudentSubmission.status == SubmissionStatus.PROCESSING,
            )
            .values(status=SubmissionStatus.FAILED, error_message=INTERRUPTED_MESSAGE)
        )


async def recover_interrupted_exam(session: AsyncSession, exam_id: uuid.UUID) -> bool:
    """Release an exam left in PROCESSING by jobs that died with their process.

    Returns False (and changes nothing) while any of the exam's jobs may still
    be running.
    """
    now = datetime.now(UTC)
    jobs = list(
        (
            await session.execute(
                select(BatchJob).where(
                    BatchJob.exam_id == exam_id, BatchJob.status.in_(ACTIVE_JOB_STATUSES)
                )
            )
        ).scalars()
    )
    if any(not _is_interrupted(job, now) for job in jobs):
        return False
    for job in jobs:
        await _fail_interrupted(session, job)
    await finish_exam_processing(session, exam_id)
    await session.flush()
    return True


async def recover_interrupted_job(session: AsyncSession, job: BatchJob) -> None:
    """Called when a job is polled: fail it if it was interrupted."""
    if job.exam_id:
        await recover_interrupted_exam(session, job.exam_id)
    elif _is_interrupted(job, datetime.now(UTC)):
        await _fail_interrupted(session, job)
        await session.flush()
