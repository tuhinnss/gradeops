"""Human-in-the-loop review workflow."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import get_current_user_optional
from app.db import crud
from app.db.models import ReviewStatus, User
from app.db.session import get_db
from app.schemas.evaluation import QuestionResult
from app.schemas.review import ReviewActionRequest, ReviewAuditItem, SubmissionReviewResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{submission_id}", response_model=SubmissionReviewResponse)
async def get_review_state(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> SubmissionReviewResponse:
    submission = await crud.get_submission(db, submission_id)
    if not submission or not submission.evaluation_result:
        raise HTTPException(status_code=404, detail="Submission not evaluated yet")

    data = submission.evaluation_result
    audits = await crud.list_review_audits(db, submission_id)

    return SubmissionReviewResponse(
        submission_id=submission_id,
        student_id=submission.student_id,
        review_status=submission.review_status,
        reviewer_notes=submission.reviewer_notes,
        results=[QuestionResult.model_validate(r) for r in data.get("results", [])],
        total=float(data.get("total", 0)),
        max_total=float(data.get("max_total", 0)),
        audit_history=[
            ReviewAuditItem(
                id=a.id,
                action=a.action,
                question=a.question,
                old_marks=a.old_marks,
                new_marks=a.new_marks,
                notes=a.notes,
                created_at=a.created_at.isoformat() if a.created_at else None,
            )
            for a in audits
        ],
    )


@router.post("/{submission_id}/action", response_model=SubmissionReviewResponse)
async def review_action(
    submission_id: uuid.UUID,
    body: ReviewActionRequest,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_current_user_optional),
) -> SubmissionReviewResponse:
    submission = await crud.get_submission(db, submission_id)
    if not submission or not submission.evaluation_result:
        raise HTTPException(status_code=404, detail="Submission not evaluated yet")

    eval_data = dict(submission.evaluation_result)
    results = list(eval_data.get("results", []))
    action = body.action.lower()

    if action == "override" and body.overrides:
        for ov in body.overrides:
            for r in results:
                if r.get("question") == ov.question:
                    old_marks = float(r.get("marks_awarded", 0))
                    r["marks_awarded"] = ov.marks_awarded
                    if ov.justification:
                        r["justification"] = ov.justification
                    await crud.add_review_audit(
                        db,
                        submission_id=submission_id,
                        reviewer_id=user.id if user else None,
                        action="override",
                        question=ov.question,
                        old_marks=old_marks,
                        new_marks=ov.marks_awarded,
                        notes=body.notes,
                    )
        eval_data["results"] = results
        eval_data["total"] = sum(float(r.get("marks_awarded", 0)) for r in results)
        review_status = ReviewStatus.OVERRIDDEN
    elif action == "approve":
        review_status = ReviewStatus.APPROVED
        await crud.add_review_audit(
            db,
            submission_id=submission_id,
            reviewer_id=user.id if user else None,
            action="approve",
            notes=body.notes,
        )
    elif action == "reject":
        review_status = ReviewStatus.REJECTED
        await crud.add_review_audit(
            db,
            submission_id=submission_id,
            reviewer_id=user.id if user else None,
            action="reject",
            notes=body.notes,
        )
    else:
        review_status = ReviewStatus.REVIEWED
        await crud.add_review_audit(
            db,
            submission_id=submission_id,
            reviewer_id=user.id if user else None,
            action=action,
            notes=body.notes,
        )

    await crud.update_submission(
        db,
        submission,
        evaluation_result=eval_data,
        total_marks=eval_data.get("total"),
        review_status=review_status,
        reviewer_notes=body.notes,
        reviewed_by=user.id if user else None,
        reviewed_at=datetime.now(UTC),
    )

    return await get_review_state(submission_id, db)
