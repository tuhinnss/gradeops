"""Cohort analytics for a rubric."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import ensure_professor, get_legacy_actor
from app.api.permissions import require_rubric_access, submission_scope
from app.db import crud
from app.db.models import User
from app.db.session import get_db

router = APIRouter()


@router.get("/rubric/{rubric_id}")
async def rubric_analytics(
    rubric_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> dict:
    ensure_professor(user)
    await require_rubric_access(db, rubric_id, user)
    return await crud.analytics_for_rubric(db, rubric_id, scope=submission_scope(user))


@router.get("/rubric/{rubric_id}/plagiarism")
async def rubric_plagiarism(
    rubric_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> dict:
    ensure_professor(user)
    await require_rubric_access(db, rubric_id, user)
    report = await crud.get_latest_plagiarism_report(db, rubric_id)
    if not report:
        return {"rubric_id": str(rubric_id), "flags": [], "matrix": {}}
    return {
        "rubric_id": str(rubric_id),
        "flags": report.flags,
        "matrix": report.matrix or {},
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@router.get("/submissions")
async def list_submissions_analytics(
    rubric_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_legacy_actor),
) -> dict:
    ensure_professor(user)
    limit = max(1, min(limit, 200))
    scope = submission_scope(user)
    subs = await crud.list_submissions(db, rubric_id=rubric_id, skip=skip, limit=limit, scope=scope)
    total = await crud.count_submissions(db, rubric_id=rubric_id, scope=scope)
    items = [
        {
            "id": str(s.id),
            "student_id": s.student_id,
            "status": s.status.value,
            "review_status": s.review_status.value,
            "total_marks": s.total_marks,
            "plagiarism_score": s.plagiarism_score,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in subs
    ]
    return {"items": items, "total": total, "skip": skip, "limit": limit}
