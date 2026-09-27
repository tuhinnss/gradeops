"""Human-in-the-loop review: state, detail, actions and answer-sheet images.

``POST /review/{id}/action`` is the single implementation of review decisions for
TAs and professors (see ``app.services.review_service``).
"""

import logging
import uuid
from pathlib import Path

import fitz
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import get_legacy_actor
from app.api.permissions import require_submission_access
from app.config import get_settings
from app.db import crud
from app.db.models import StudentSubmission, User
from app.db.session import get_db
from app.schemas.evaluation import QuestionResult
from app.schemas.review import ReviewActionRequest, ReviewDetailResponse, SubmissionReviewResponse
from app.services.review_queue import audit_items, review_detail
from app.services.review_service import apply_review_action

logger = logging.getLogger(__name__)
router = APIRouter()

CROP_MARGIN_PT = 6
IMAGE_CACHE = {"Cache-Control": "private, max-age=300"}


async def _review_state(db: AsyncSession, submission: StudentSubmission) -> SubmissionReviewResponse:
    data = submission.evaluation_result or {}
    return SubmissionReviewResponse(
        submission_id=submission.id,
        student_id=submission.student_id,
        review_status=submission.review_status,
        reviewer_notes=submission.reviewer_notes,
        results=[QuestionResult.model_validate(r) for r in data.get("results", [])],
        total=float(data.get("total", 0)),
        max_total=float(data.get("max_total", 0)),
        audit_history=await audit_items(db, submission.id),
        exam_id=submission.exam_id,
        ai_total=submission.ai_total_marks,
        ta_total=submission.ta_total_marks,
        professor_total=submission.professor_total_marks,
        escalation_reason=submission.escalation_reason,
        escalation_notes=submission.escalation_notes,
    )


@router.get("/{submission_id}", response_model=SubmissionReviewResponse)
async def get_review_state(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> SubmissionReviewResponse:
    submission = await require_submission_access(db, submission_id, user)
    if not submission.evaluation_result:
        raise HTTPException(status_code=404, detail="Submission not evaluated yet")
    return await _review_state(db, submission)


@router.get("/{submission_id}/detail", response_model=ReviewDetailResponse)
async def get_review_detail(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> ReviewDetailResponse:
    submission = await require_submission_access(db, submission_id, user)
    return await review_detail(db, submission, user)


@router.post("/{submission_id}/action", response_model=SubmissionReviewResponse)
async def review_action(
    submission_id: uuid.UUID,
    body: ReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> SubmissionReviewResponse:
    # Row lock serialises concurrent decisions on the same submission.
    submission = await require_submission_access(db, submission_id, user, lock=True)
    await apply_review_action(db, submission, user, body)
    return await _review_state(db, submission)


# --- Answer-sheet images ----------------------------------------------------------------


def _open_pdf(submission: StudentSubmission) -> fitz.Document:
    path = Path(submission.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Answer sheet file missing on disk")
    return fitz.open(path)


def _render(page: fitz.Page, zoom: float, clip: fitz.Rect | None = None) -> bytes:
    return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False).tobytes("png")


@router.get("/{submission_id}/pages/{page_index}")
async def get_page_image(
    submission_id: uuid.UUID,
    page_index: int,
    dpi: int = Query(110, ge=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> Response:
    submission = await require_submission_access(db, submission_id, user)
    with _open_pdf(submission) as doc:
        if page_index < 0 or page_index >= len(doc):
            raise HTTPException(status_code=404, detail="Page not found")
        png = _render(doc[page_index], dpi / 72.0)
    return Response(content=png, media_type="image/png", headers=IMAGE_CACHE)


@router.get("/{submission_id}/answer-image")
async def get_answer_image(
    submission_id: uuid.UUID,
    question: str = Query(..., min_length=1, max_length=32),
    dpi: int = Query(130, ge=50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> Response:
    """Crop of the answer region OCR used for ``question`` (full page if unknown)."""
    submission = await require_submission_access(db, submission_id, user)
    answer = next(
        (a for a in await crud.list_extracted_answers(db, submission_id) if a.question_number.upper() == question.upper()),
        None,
    )
    page_index = answer.page_index if answer else 0
    source_zoom = get_settings().pdf_dpi / 72.0  # OCR bboxes are in pixels at PDF_DPI
    with _open_pdf(submission) as doc:
        if page_index >= len(doc):
            raise HTTPException(status_code=404, detail="Page not found")
        page = doc[page_index]
        clip = None
        if answer and isinstance(answer.bbox, dict) and {"x0", "y0", "x1", "y1"} <= answer.bbox.keys():
            b = answer.bbox
            clip = fitz.Rect(
                b["x0"] / source_zoom - CROP_MARGIN_PT,
                b["y0"] / source_zoom - CROP_MARGIN_PT,
                b["x1"] / source_zoom + CROP_MARGIN_PT,
                b["y1"] / source_zoom + CROP_MARGIN_PT,
            ) & page.rect
            if clip.is_empty:
                clip = None
        png = _render(page, dpi / 72.0, clip)
    return Response(
        content=png,
        media_type="image/png",
        headers={**IMAGE_CACHE, "X-Page-Index": str(page_index), "X-Cropped": "1" if clip else "0"},
    )


@router.get("/{submission_id}/source-pdf")
async def get_source_pdf(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> FileResponse:
    submission = await require_submission_access(db, submission_id, user)
    path = Path(submission.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Answer sheet file missing on disk")
    return FileResponse(path, media_type="application/pdf", filename=submission.source_filename)
