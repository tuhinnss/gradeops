"""Bulk upload and batch evaluation queue."""

import io
import logging
import re
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import get_current_user_optional
from app.config import get_settings
from app.db import crud
from app.db.models import User
from app.db.session import async_session_factory, get_db
from app.schemas.batch import BatchJobCreate, BatchJobResponse, BulkUploadResponse, BulkUploadItem
from app.services.batch_queue import enqueue_batch_job
from app.services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()
storage = StorageService()


def _student_id_from_filename(filename: str, index: int) -> str:
    stem = Path(filename).stem
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", stem)[:64]
    if cleaned and len(cleaned) >= 2:
        return cleaned
    return f"student_{index:04d}"


async def _save_pdf_bytes(content: bytes, filename: str, subdir: str) -> Path:
    if len(content) > settings.max_upload_bytes:
        raise ValueError(f"File {filename} exceeds size limit")
    safe = f"{uuid.uuid4()}_{Path(filename).name}"
    return storage.save_upload_file(content, subdir, safe)


@router.post("/answer-sheets", response_model=BulkUploadResponse)
async def bulk_upload_answer_sheets(
    files: list[UploadFile] = File(..., description="Multiple PDF answer sheets"),
    rubric_id: uuid.UUID | None = Form(None),
    batch_job_id: uuid.UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> BulkUploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    uploaded: list[BulkUploadItem] = []
    failed: list[dict] = []

    for idx, file in enumerate(files):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            failed.append({"filename": file.filename, "error": "Not a PDF"})
            continue
        try:
            content = await file.read()
            dest = await _save_pdf_bytes(content, file.filename, "submissions")
            student_id = _student_id_from_filename(file.filename, idx + 1)
            sub = await crud.create_submission(
                db,
                student_id=student_id,
                source_filename=file.filename,
                file_path=str(dest),
                rubric_id=rubric_id,
                batch_job_id=batch_job_id,
            )
            uploaded.append(BulkUploadItem(id=sub.id, student_id=student_id, filename=file.filename))
        except Exception as exc:
            failed.append({"filename": file.filename, "error": str(exc)})

    return BulkUploadResponse(
        uploaded=uploaded,
        failed=failed,
        message=f"Uploaded {len(uploaded)} of {len(files)} files",
    )


@router.post("/answer-sheets/zip", response_model=BulkUploadResponse)
async def bulk_upload_zip(
    file: UploadFile = File(..., description="ZIP containing PDF answer sheets"),
    rubric_id: uuid.UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> BulkUploadResponse:
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP files accepted")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="ZIP exceeds size limit")

    uploaded: list[BulkUploadItem] = []
    failed: list[dict] = []
    idx = 0

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                if name.endswith("/") or not name.lower().endswith(".pdf"):
                    continue
                idx += 1
                try:
                    pdf_bytes = zf.read(name)
                    basename = Path(name).name
                    dest = await _save_pdf_bytes(pdf_bytes, basename, "submissions")
                    student_id = _student_id_from_filename(basename, idx)
                    sub = await crud.create_submission(
                        db,
                        student_id=student_id,
                        source_filename=basename,
                        file_path=str(dest),
                        rubric_id=rubric_id,
                    )
                    uploaded.append(
                        BulkUploadItem(id=sub.id, student_id=student_id, filename=basename)
                    )
                except Exception as exc:
                    failed.append({"filename": name, "error": str(exc)})
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Invalid ZIP file") from exc

    return BulkUploadResponse(
        uploaded=uploaded,
        failed=failed,
        message=f"Extracted {len(uploaded)} PDFs from ZIP",
    )


@router.post("/jobs", response_model=BatchJobResponse)
async def create_batch_job(
    body: BatchJobCreate,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> BatchJobResponse:
    rubric = await crud.get_rubric(db, body.rubric_id)
    if not rubric:
        raise HTTPException(status_code=404, detail="Rubric not found")

    job = await crud.create_batch_job(
        db,
        rubric_id=body.rubric_id,
        submission_ids=[str(s) for s in body.submission_ids],
        run_plagiarism=body.run_plagiarism_check,
        created_by=user.id if user else None,
    )

    for sid in body.submission_ids:
        sub = await crud.get_submission(db, sid)
        if sub:
            await crud.update_submission(db, sub, batch_job_id=job.id, rubric_id=body.rubric_id)

    await db.flush()
    enqueue_batch_job(job.id, async_session_factory)

    return _job_response(job)


@router.get("/jobs/{job_id}", response_model=BatchJobResponse)
async def get_batch_job(job_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> BatchJobResponse:
    job = await crud.get_batch_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return _job_response(job)


def _job_response(job) -> BatchJobResponse:
    total = job.total_count or 1
    pct = round(100.0 * (job.completed_count + job.failed_count) / total, 1)
    return BatchJobResponse(
        id=job.id,
        rubric_id=job.rubric_id,
        status=job.status,
        total_count=job.total_count,
        completed_count=job.completed_count,
        failed_count=job.failed_count,
        progress_percent=min(pct, 100.0),
        submission_ids=job.submission_ids or [],
        errors=job.errors or [],
    )
