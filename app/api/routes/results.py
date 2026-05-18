"""Results and report generation endpoints."""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import crud
from app.db.session import get_db
from app.schemas.evaluation import EvaluationResponse, QuestionResult

router = APIRouter()
settings = get_settings()


@router.get("/{submission_id}")
async def get_results(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    submission = await crud.get_submission(db, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if not submission.evaluation_result:
        return {
            "submission_id": str(submission_id),
            "student_id": submission.student_id,
            "status": submission.status.value,
            "message": "Not yet evaluated. Call POST /api/v1/evaluate/run first.",
            "extracted_text": submission.extracted_text,
        }

    return {
        "submission_id": str(submission_id),
        "student_id": submission.student_id,
        "status": submission.status.value,
        "review_status": submission.review_status.value,
        "reviewer_notes": submission.reviewer_notes,
        "plagiarism_score": submission.plagiarism_score,
        **submission.evaluation_result,
    }


@router.get("/{submission_id}/json", response_model=EvaluationResponse)
async def get_results_json(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> EvaluationResponse:
    submission = await crud.get_submission(db, submission_id)
    if not submission or not submission.evaluation_result:
        raise HTTPException(status_code=404, detail="Evaluation results not found")

    data = submission.evaluation_result
    return EvaluationResponse(
        submission_id=submission_id,
        student_id=submission.student_id,
        results=[QuestionResult.model_validate(r) for r in data["results"]],
        total=data["total"],
        max_total=data.get("max_total", data["total"]),
        annotated_pdf_url=f"/api/v1/results/{submission_id}/annotated-pdf",
    )


@router.get("/{submission_id}/annotated-pdf")
async def download_annotated_pdf(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    submission = await crud.get_submission(db, submission_id)
    if not submission or not submission.annotated_pdf_path:
        raise HTTPException(status_code=404, detail="Annotated PDF not found")

    path = Path(submission.annotated_pdf_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Annotated PDF file missing on disk")

    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
    )


@router.get("/{submission_id}/generate-report")
async def generate_report(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return full evaluation report including OCR extraction and logs."""
    submission = await crud.get_submission(db, submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    logs = [
        {
            "stage": log.stage,
            "message": log.message,
            "metadata": log.metadata_,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in submission.evaluation_logs
    ]

    report = {
        "submission_id": str(submission_id),
        "student_id": submission.student_id,
        "status": submission.status.value,
        "source_filename": submission.source_filename,
        "page_count": submission.page_count,
        "extracted_text": submission.extracted_text,
        "evaluation": submission.evaluation_result,
        "total_marks": submission.total_marks,
        "annotated_pdf": submission.annotated_pdf_path,
        "logs": logs,
    }
    return JSONResponse(content=report)
