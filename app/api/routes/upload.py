"""Upload endpoints for answer sheets and rubrics."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import ensure_professor, get_legacy_actor
from app.api.permissions import require_rubric_access
from app.config import get_settings
from app.core.exceptions import RubricParseError, http_error
from app.db import crud
from app.db.models import User
from app.db.session import get_db
from app.schemas.upload import RubricUploadResponse, UploadResponse
from app.services.rubric_parser import RubricParser

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


def _validate_pdf(file: UploadFile) -> None:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted for answer sheets",
        )


def _validate_rubric_file(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")
    lower = file.filename.lower()
    if lower.endswith(".json"):
        return "json"
    if lower.endswith(".pdf"):
        return "pdf"
    raise HTTPException(
        status_code=400,
        detail="Rubric must be .json or .pdf",
    )


async def _save_upload(file: UploadFile, subdir: str) -> tuple[Path, str]:
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_mb}MB limit",
        )

    dest_dir = settings.upload_dir / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4()}_{Path(file.filename).name}"
    dest_path = dest_dir / safe_name
    dest_path.write_bytes(content)
    return dest_path, file.filename or safe_name


@router.post("/answer-sheet", response_model=UploadResponse)
async def upload_answer_sheet(
    file: UploadFile = File(..., description="Handwritten answer sheet PDF"),
    student_id: str = Form(..., description="Student identifier"),
    rubric_id: uuid.UUID | None = Form(None),
    db: AsyncSession = Depends(get_db),
    actor: User | None = Depends(get_legacy_actor),
) -> UploadResponse:
    ensure_professor(actor)
    _validate_pdf(file)
    if rubric_id:
        await require_rubric_access(db, rubric_id, actor)
    dest_path, filename = await _save_upload(file, "submissions")

    submission = await crud.create_submission(
        db,
        student_id=student_id,
        source_filename=filename,
        file_path=str(dest_path),
        rubric_id=rubric_id,
        uploaded_by=actor.id if actor else None,
    )
    logger.info("Uploaded answer sheet for student %s: %s", student_id, submission.id)

    return UploadResponse(
        id=submission.id,
        message="Answer sheet uploaded successfully",
        filename=filename,
    )


@router.post("/rubric", response_model=RubricUploadResponse)
async def upload_rubric(
    file: UploadFile = File(..., description="Marking scheme JSON or PDF"),
    name: str = Form("Exam Rubric"),
    db: AsyncSession = Depends(get_db),
    actor: User | None = Depends(get_legacy_actor),
) -> RubricUploadResponse:
    ensure_professor(actor)
    source_type = _validate_rubric_file(file)
    dest_path, filename = await _save_upload(file, "rubrics")

    parser = RubricParser()
    try:
        schema = parser.parse_file(dest_path, source_type)
    except RubricParseError as exc:
        raise http_error(exc) from exc

    rubric = await crud.create_rubric(
        db,
        name=name,
        source_filename=filename,
        source_type=source_type,
        structured_data=schema.to_dict(),
        file_path=str(dest_path),
        owner_id=actor.id if actor else None,
    )

    return RubricUploadResponse(
        id=rubric.id,
        message="Rubric parsed and stored successfully",
        filename=filename,
        question_count=len(schema.items),
    )
