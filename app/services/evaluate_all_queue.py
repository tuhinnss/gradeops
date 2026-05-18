"""Background queue for evaluate-all jobs with progress tracking."""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import crud
from app.schemas.rubric import RubricSchema
from app.services.pipeline import GradeOpsPipeline

logger = logging.getLogger(__name__)

_pipeline: GradeOpsPipeline | None = None
_jobs: dict[uuid.UUID, "EvaluateAllJob"] = {}
_lock = asyncio.Lock()


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class EvaluateAllJob:
    job_id: uuid.UUID
    rubric_id: uuid.UUID
    submission_ids: list[uuid.UUID]
    run_plagiarism: bool
    status: JobStatus = JobStatus.QUEUED
    total_processed: int = 0
    current: int = 0
    success_count: int = 0
    failed_count: int = 0
    errors: list[dict] = field(default_factory=list)


def get_pipeline() -> GradeOpsPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GradeOpsPipeline()
    return _pipeline


def get_job(job_id: uuid.UUID) -> EvaluateAllJob | None:
    return _jobs.get(job_id)


async def run_evaluate_all_job(
    job_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    job = _jobs.get(job_id)
    if not job:
        return

    pipeline = get_pipeline()
    job.status = JobStatus.RUNNING
    total = len(job.submission_ids)
    job.total_processed = total
    succeeded_ids: list[uuid.UUID] = []

    sem = asyncio.Semaphore(2)
    counter_lock = asyncio.Lock()

    async def process_one(sid: uuid.UUID) -> None:
        async with sem:
            async with session_factory() as session:
                try:
                    rubric = await crud.get_rubric(session, job.rubric_id)
                    if not rubric:
                        raise ValueError("Rubric not found")
                    rubric_schema = RubricSchema.from_dict(rubric.structured_data)
                    await pipeline.process_submission_ocr(session, sid, rubric_schema)
                    await pipeline.evaluate_submission(session, sid, rubric_schema)
                    await session.commit()
                    async with counter_lock:
                        job.success_count += 1
                        job.current = job.success_count + job.failed_count
                        logger.info(
                            "Evaluating submission %s/%s...",
                            job.current,
                            total,
                        )
                        succeeded_ids.append(sid)
                except Exception as exc:
                    logger.exception("Evaluate-all failed for %s: %s", sid, exc)
                    async with counter_lock:
                        job.failed_count += 1
                        job.current = job.success_count + job.failed_count
                        job.errors.append({"submission_id": str(sid), "error": str(exc)})
                        logger.info(
                            "Evaluating submission %s/%s... (failed)",
                            job.current,
                            total,
                        )
                    await session.rollback()

    await asyncio.gather(*[process_one(sid) for sid in job.submission_ids])

    if job.run_plagiarism and len(succeeded_ids) > 1:
        async with session_factory() as session:
            try:
                await pipeline.run_plagiarism_check(session, succeeded_ids)
                await session.commit()
            except Exception as exc:
                logger.warning("Plagiarism check after evaluate-all failed: %s", exc)

    job.current = total
    job.status = JobStatus.COMPLETED if job.failed_count == 0 else JobStatus.COMPLETED
    logger.info(
        "Evaluate-all job %s done: %s succeeded, %s failed of %s",
        job_id,
        job.success_count,
        job.failed_count,
        total,
    )


def enqueue_evaluate_all(
    *,
    rubric_id: uuid.UUID,
    submission_ids: list[uuid.UUID],
    run_plagiarism: bool,
    session_factory: async_sessionmaker[AsyncSession],
) -> EvaluateAllJob:
    job_id = uuid.uuid4()
    job = EvaluateAllJob(
        job_id=job_id,
        rubric_id=rubric_id,
        submission_ids=submission_ids,
        run_plagiarism=run_plagiarism,
        total_processed=len(submission_ids),
    )
    _jobs[job_id] = job
    asyncio.create_task(run_evaluate_all_job(job_id, session_factory))
    return job
