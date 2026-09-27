"""Rubric library (professor-owned). TAs read rubrics only through assigned exams."""

import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps_auth import ProfessorUser, StaffUser
from app.api.permissions import require_rubric_access
from app.db.models import Exam, ExamStatus, Rubric
from app.db.session import get_db
from app.schemas.academic import ExamRef, RubricDetail, RubricSummary, RubricUpdate
from app.schemas.rubric import RubricSchema
from app.services.academic import rubric_summary
from app.services.exam_workflow import add_exam_audit
from app.services.text_utils import validate_rubric_items

router = APIRouter()

EDITABLE_EXAM_STATUSES = (ExamStatus.DRAFT, ExamStatus.TA_REVIEW)


async def _usage(db: AsyncSession, rubric_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Exam]]:
    usage: dict[uuid.UUID, list[Exam]] = defaultdict(list)
    if rubric_ids:
        for exam in (await db.execute(select(Exam).where(Exam.rubric_id.in_(rubric_ids)))).scalars():
            usage[exam.rubric_id].append(exam)
    return usage


def _refs(exams: list[Exam]) -> list[ExamRef]:
    return [ExamRef(id=e.id, name=e.name) for e in exams]


@router.get("", response_model=list[RubricSummary])
async def list_rubrics(user: ProfessorUser, db: AsyncSession = Depends(get_db)) -> list[RubricSummary]:
    rubrics = list(
        (await db.execute(select(Rubric).where(Rubric.owner_id == user.id).order_by(Rubric.created_at.desc()))).scalars()
    )
    usage = await _usage(db, [r.id for r in rubrics])
    return [rubric_summary(r, _refs(usage.get(r.id, []))) for r in rubrics]


@router.get("/{rubric_id}", response_model=RubricDetail)
async def get_rubric(rubric_id: uuid.UUID, user: StaffUser, db: AsyncSession = Depends(get_db)) -> RubricDetail:
    rubric = await require_rubric_access(db, rubric_id, user)
    usage = await _usage(db, [rubric.id])
    summary = rubric_summary(rubric, _refs(usage.get(rubric.id, [])))
    return RubricDetail(**summary.model_dump(), structured_data=RubricSchema.from_dict(rubric.structured_data))


@router.put("/{rubric_id}", response_model=RubricDetail)
async def update_rubric(
    rubric_id: uuid.UUID, body: RubricUpdate, user: ProfessorUser, db: AsyncSession = Depends(get_db)
) -> RubricDetail:
    """Edit a rubric. Blocked once any exam using it has been approved or published."""
    rubric = await require_rubric_access(db, rubric_id, user, manage=True)
    exams = (await _usage(db, [rubric.id])).get(rubric.id, [])
    frozen = [e.name for e in exams if e.status not in EDITABLE_EXAM_STATUSES]
    if frozen:
        raise HTTPException(
            status_code=409,
            detail=f"Rubric is used by exams that are processing or finalised: {', '.join(frozen)}",
        )
    if body.name is not None:
        rubric.name = body.name
    if body.structured_data is not None:
        items = validate_rubric_items(body.structured_data.items)
        if not items:
            raise HTTPException(status_code=400, detail="Rubric needs at least one valid question")
        rubric.structured_data = RubricSchema(title=body.structured_data.title, items=items).to_dict()
        for exam in exams:
            await add_exam_audit(
                db, exam, action="rubric_edited", actor_id=user.id,
                notes="Rubric changed; re-run evaluation for grades to reflect it.",
                details={"rubric_id": str(rubric.id)},
            )
    await db.flush()
    summary = rubric_summary(rubric, _refs(exams))
    return RubricDetail(**summary.model_dump(), structured_data=RubricSchema.from_dict(rubric.structured_data))
