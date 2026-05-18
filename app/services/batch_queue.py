"""Async batch evaluation queue with DB-backed progress."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import crud
from app.db.models import BatchJobStatus, ReviewStatus
from app.schemas.rubric import RubricSchema
from app.services.pipeline import GradeOpsPipeline

logger = logging.getLogger(__name__)

_pipeline: GradeOpsPipeline | None = None
_running: set[uuid.UUID] = set()
_lock = asyncio.Lock()


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
                        await pipeline.evaluate_submission(session, sid, rubric_schema)
                        sub = await crud.get_submission(session, sid)
                        if sub:
                            await crud.update_submission(
                                session,
                                sub,
                                review_status=ReviewStatus.PENDING,
                            )
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
                    flags = await pipeline.run_plagiarism_check(session, submission_ids)
                    await crud.save_plagiarism_report(
                        session,
                        rubric_id=job.rubric_id,
                        flags=[f.model_dump() for f in flags],
                        batch_job_id=job_id,
                    )
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
                status = BatchJobStatus.COMPLETED if failed == 0 else BatchJobStatus.COMPLETED
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
                await session.commit()
    finally:
        _running.discard(job_id)


def enqueue_batch_job(job_id: uuid.UUID, session_factory: async_sessionmaker) -> None:
    asyncio.create_task(run_batch_job(job_id, session_factory))
