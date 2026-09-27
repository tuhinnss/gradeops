"""Review queue, review detail and queue navigation (scoped to the caller)."""

import uuid

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.permissions import submission_scope
from app.db import crud
from app.db.models import (
    HUMAN_REVIEWED_STATUSES,
    TA_QUEUE_STATUSES,
    TA_REVIEWED_STATUSES,
    Course,
    Exam,
    IntegrityFlag,
    IntegrityFlagStatus,
    ReviewStatus,
    Rubric,
    Student,
    StudentSubmission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.schemas.evaluation import CriterionScore
from app.schemas.review import (
    AnswerRegion,
    FocusQuestion,
    IntegrityFlagBrief,
    ReviewAuditItem,
    ReviewDetailResponse,
    ReviewExamInfo,
    ReviewNavigation,
    ReviewPermissions,
    ReviewQuestion,
    ReviewQueueItem,
    ReviewQueueResponse,
    ReviewSubmissionInfo,
    RubricCriteria,
)
from app.schemas.rubric import RubricSchema
from app.services.academic import integrity_counts, student_names, submission_max_total, user_summary, users_by_id
from app.services.review_service import allowed_actions, review_block_reason
from app.services.text_utils import normalize_question_label

STATUS_GROUPS: dict[str, tuple[ReviewStatus, ...]] = {
    "pending": TA_QUEUE_STATUSES,
    "reviewed": TA_REVIEWED_STATUSES,
    "escalated": (ReviewStatus.ESCALATED,),
    "approved": (ReviewStatus.PROFESSOR_APPROVED, ReviewStatus.PUBLISHED),
}


def _open_flag_exists() -> ColumnElement[bool]:
    return exists().where(
        IntegrityFlag.status == IntegrityFlagStatus.OPEN,
        or_(
            IntegrityFlag.submission_a_id == StudentSubmission.id,
            IntegrityFlag.submission_b_id == StudentSubmission.id,
        ),
    )


def _question_filter(question: str) -> ColumnElement[bool]:
    return StudentSubmission.evaluation_result["results"].contains([{"question": question}])


def normalise_question(question: str | None) -> str | None:
    if not question:
        return None
    label = normalize_question_label(question.strip().lstrip("Qq")) or question.strip().upper()
    return label if label.startswith("Q") else f"Q{label}"


def _focus(sub: StudentSubmission, question: str | None) -> FocusQuestion | None:
    results = (sub.evaluation_result or {}).get("results", [])
    if not results:
        return None
    if question:
        chosen = next((r for r in results if str(r.get("question")).upper() == question.upper()), None)
    else:
        chosen = min(results, key=lambda r: float(r.get("confidence", 1.0)))
    if not chosen:
        return None
    return FocusQuestion(
        question=str(chosen.get("question")),
        marks_awarded=float(chosen.get("marks_awarded", 0)),
        max_marks=float(chosen.get("max_marks", 0)),
        confidence=float(chosen.get("confidence", 0)),
        requires_manual_grading=bool(chosen.get("requires_manual_grading", False)),
    )


async def review_queue(
    db: AsyncSession,
    user: User,
    *,
    exam_id: uuid.UUID | None = None,
    course_id: uuid.UUID | None = None,
    status: str = "pending",
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    integrity_only: bool = False,
    manual_only: bool = False,
    student: str | None = None,
    question: str | None = None,
    sort: str = "confidence_asc",
    limit: int = 50,
    offset: int = 0,
) -> ReviewQueueResponse:
    question = normalise_question(question)
    conditions: list[ColumnElement[bool]] = [
        submission_scope(user),
        StudentSubmission.status == SubmissionStatus.EVALUATED,
        StudentSubmission.exam_id.isnot(None),
    ]
    if status in STATUS_GROUPS:
        conditions.append(StudentSubmission.review_status.in_(STATUS_GROUPS[status]))
    elif status != "all":
        conditions.append(StudentSubmission.review_status == ReviewStatus(status))
    if exam_id:
        conditions.append(StudentSubmission.exam_id == exam_id)
    if course_id:
        conditions.append(StudentSubmission.exam_id.in_(select(Exam.id).where(Exam.course_id == course_id)))
    if min_confidence is not None:
        conditions.append(StudentSubmission.min_confidence >= min_confidence)
    if max_confidence is not None:
        conditions.append(StudentSubmission.min_confidence <= max_confidence)
    if integrity_only:
        conditions.append(_open_flag_exists())
    if manual_only:
        conditions.append(StudentSubmission.needs_manual_grading.is_(True))
    if question:
        conditions.append(_question_filter(question))
    if student:
        like = f"%{student.strip()}%"
        conditions.append(
            or_(
                StudentSubmission.student_id.ilike(like),
                StudentSubmission.student_record_id.in_(select(Student.id).where(Student.name.ilike(like))),
            )
        )

    total = await db.scalar(select(func.count()).select_from(StudentSubmission).where(*conditions)) or 0
    order = {
        "confidence_asc": (StudentSubmission.min_confidence.asc().nulls_last(), StudentSubmission.id),
        "confidence_desc": (StudentSubmission.min_confidence.desc().nulls_last(), StudentSubmission.id),
        "newest": (StudentSubmission.created_at.desc(), StudentSubmission.id),
        "oldest": (StudentSubmission.created_at.asc(), StudentSubmission.id),
    }.get(sort, (StudentSubmission.min_confidence.asc().nulls_last(), StudentSubmission.id))
    subs = list(
        (
            await db.execute(
                select(StudentSubmission).where(*conditions).order_by(*order).offset(offset).limit(limit)
            )
        ).scalars()
    )

    exams = {
        e.id: (e, c)
        for e, c in (
            await db.execute(
                select(Exam, Course)
                .join(Course, Course.id == Exam.course_id)
                .where(Exam.id.in_({s.exam_id for s in subs if s.exam_id}))
            )
        ).all()
    }
    names = await student_names(db, (s.student_record_id for s in subs))
    flags = await integrity_counts(db, [s.id for s in subs])
    items = []
    for s in subs:
        exam, course = exams.get(s.exam_id, (None, None))
        items.append(
            ReviewQueueItem(
                submission_id=s.id,
                student_id=s.student_id,
                student_name=names.get(s.student_record_id) if s.student_record_id else None,
                exam_id=s.exam_id,
                exam_name=exam.name if exam else None,
                course_code=course.course_code if course else None,
                total=s.total_marks,
                ai_total=s.ai_total_marks,
                max_total=submission_max_total(s),
                min_confidence=s.min_confidence,
                focus=_focus(s, question),
                review_status=s.review_status,
                needs_manual_grading=s.needs_manual_grading,
                integrity_flags=flags.get(s.id, 0),
                escalation_reason=s.escalation_reason if s.review_status == ReviewStatus.ESCALATED else None,
                assigned_to_me=s.assigned_ta_id == user.id,
                updated_at=s.updated_at,
            )
        )
    return ReviewQueueResponse(items=items, total=total)


async def navigation(db: AsyncSession, user: User | None, sub: StudentSubmission) -> ReviewNavigation:
    """Neighbours in the caller's queue for this exam, lowest confidence first."""
    if sub.exam_id is None:
        return ReviewNavigation(prev_id=None, next_id=None, next_pending_id=None, position=None, queue_size=0)
    rows = (
        await db.execute(
            select(StudentSubmission.id, StudentSubmission.review_status)
            .where(
                submission_scope(user),
                StudentSubmission.exam_id == sub.exam_id,
                StudentSubmission.status == SubmissionStatus.EVALUATED,
            )
            .order_by(StudentSubmission.min_confidence.asc().nulls_last(), StudentSubmission.id)
            .limit(5000)
        )
    ).all()
    ids = [r[0] for r in rows]
    if sub.id not in ids:
        return ReviewNavigation(prev_id=None, next_id=None, next_pending_id=None, position=None, queue_size=len(ids))
    pos = ids.index(sub.id)
    pending_statuses = set(TA_QUEUE_STATUSES)
    if user is not None and user.role == UserRole.PROFESSOR:
        pending_statuses |= {ReviewStatus.ESCALATED, *TA_REVIEWED_STATUSES}
    rotated = rows[pos + 1 :] + rows[:pos]
    next_pending = next((rid for rid, st in rotated if st in pending_statuses), None)
    return ReviewNavigation(
        prev_id=ids[pos - 1] if pos > 0 else None,
        next_id=ids[pos + 1] if pos + 1 < len(ids) else None,
        next_pending_id=next_pending,
        position=pos + 1,
        queue_size=len(ids),
    )


async def audit_items(db: AsyncSession, submission_id: uuid.UUID) -> list[ReviewAuditItem]:
    audits = await crud.list_review_audits(db, submission_id)
    users = await users_by_id(db, (a.reviewer_id for a in audits))
    return [
        ReviewAuditItem(
            id=a.id,
            action=a.action,
            question=a.question,
            old_marks=a.old_marks,
            new_marks=a.new_marks,
            notes=a.notes,
            created_at=a.created_at.isoformat() if a.created_at else None,
            reason=a.reason,
            from_status=a.from_status,
            to_status=a.to_status,
            actor_role=a.actor_role,
            reviewer=user_summary(users.get(a.reviewer_id)) if a.reviewer_id else None,
        )
        for a in audits
    ]


async def review_detail(
    db: AsyncSession, sub: StudentSubmission, user: User | None
) -> ReviewDetailResponse:
    exam = await db.get(Exam, sub.exam_id) if sub.exam_id else None
    course = await db.get(Course, exam.course_id) if exam else None
    rubric_id = (exam.rubric_id if exam else None) or sub.rubric_id
    rubric = await db.get(Rubric, rubric_id) if rubric_id else None
    rubric_items = {}
    if rubric:
        try:
            rubric_items = {
                i.question_number.upper(): i for i in RubricSchema.from_dict(rubric.structured_data).items
            }
        except Exception:
            rubric_items = {}

    answers = {a.question_number.upper(): a for a in await crud.list_extracted_answers(db, sub.id)}
    stored_answers = {
        str(a.get("question_number", "")).upper(): a
        for a in (sub.extracted_text or {}).get("answers", [])
    }

    questions: list[ReviewQuestion] = []
    for r in (sub.evaluation_result or {}).get("results", []):
        q = str(r.get("question", ""))
        item = rubric_items.get(q.upper())
        ans = answers.get(q.upper())
        region = None
        if ans is not None:
            region = AnswerRegion(
                text=ans.extracted_text or "", ocr_confidence=ans.ocr_confidence,
                page_index=ans.page_index, bbox=ans.bbox, is_blank=ans.is_blank,
            )
        elif q.upper() in stored_answers:
            a = stored_answers[q.upper()]
            region = AnswerRegion(
                text=a.get("extracted_text", ""), ocr_confidence=a.get("ocr_confidence"),
                page_index=a.get("page_index"), bbox=a.get("bbox"), is_blank=bool(a.get("is_blank")),
            )
        questions.append(
            ReviewQuestion(
                question=q,
                max_marks=float(r.get("max_marks", 0)),
                marks_awarded=float(r.get("marks_awarded", 0)),
                ai_marks_awarded=r.get("ai_marks_awarded"),
                confidence=float(r.get("confidence", 0)),
                justification=r.get("justification", ""),
                reviewer_comment=r.get("reviewer_comment"),
                is_blank=bool(r.get("is_blank", False)),
                requires_manual_grading=bool(r.get("requires_manual_grading", False)),
                scoring_method=r.get("scoring_method"),
                criteria=[CriterionScore.model_validate(c) for c in r.get("criteria", []) or []],
                key_points_matched=r.get("key_points_matched", []) or [],
                key_points_partial=r.get("key_points_partial", []) or [],
                key_points_missed=r.get("key_points_missed", []) or [],
                negative_triggers=r.get("negative_triggers", []) or [],
                rubric=RubricCriteria(
                    key_points=item.key_points if item else [],
                    partial_credit_rules=item.partial_credit_rules if item else [],
                    negative_conditions=item.negative_conditions if item else [],
                ),
                answer=region,
            )
        )

    flag_rows = (
        await db.execute(
            select(IntegrityFlag).where(
                or_(IntegrityFlag.submission_a_id == sub.id, IntegrityFlag.submission_b_id == sub.id)
            )
        )
    ).scalars().all()
    flags = [
        IntegrityFlagBrief(
            id=f.id,
            question=f.question,
            similarity=f.similarity,
            other_student_id=f.student_b if f.submission_a_id == sub.id else f.student_a,
            other_submission_id=f.submission_b_id if f.submission_a_id == sub.id else f.submission_a_id,
            status=f.status,
        )
        for f in flag_rows
    ]

    users = await users_by_id(db, (sub.escalated_by, sub.reviewed_by, sub.approved_by, sub.assigned_ta_id))
    name = None
    if sub.student_record_id:
        name = (await student_names(db, [sub.student_record_id])).get(sub.student_record_id)
    data = sub.evaluation_result or {}
    actions = allowed_actions(sub, exam, user)
    return ReviewDetailResponse(
        submission=ReviewSubmissionInfo(
            id=sub.id,
            student_id=sub.student_id,
            student_name=name,
            source_filename=sub.source_filename,
            status=sub.status,
            review_status=sub.review_status,
            page_count=sub.page_count,
            total=float(data.get("total", sub.total_marks or 0)),
            max_total=float(data.get("max_total", 0)),
            ai_total=sub.ai_total_marks,
            ta_total=sub.ta_total_marks,
            professor_total=sub.professor_total_marks,
            min_confidence=sub.min_confidence,
            needs_manual_grading=sub.needs_manual_grading,
            reviewer_notes=sub.reviewer_notes,
            escalation_reason=sub.escalation_reason,
            escalation_notes=sub.escalation_notes,
            escalated_by=user_summary(users.get(sub.escalated_by)) if sub.escalated_by else None,
            escalated_at=sub.escalated_at,
            reviewed_by=user_summary(users.get(sub.reviewed_by)) if sub.reviewed_by else None,
            reviewed_at=sub.reviewed_at,
            approved_by=user_summary(users.get(sub.approved_by)) if sub.approved_by else None,
            approved_at=sub.approved_at,
            assigned_ta=user_summary(users.get(sub.assigned_ta_id)) if sub.assigned_ta_id else None,
            has_annotated_pdf=bool(sub.annotated_pdf_path),
        ),
        exam=(
            ReviewExamInfo(
                id=exam.id, name=exam.name, status=exam.status,
                course_code=course.course_code, course_name=course.name,
            )
            if exam and course
            else None
        ),
        questions=questions,
        integrity_flags=flags,
        audit_history=await audit_items(db, sub.id),
        permissions=ReviewPermissions(
            can_approve=actions["approve"],
            can_override=actions["override"],
            can_escalate=actions["escalate"],
            can_resolve=actions["resolve"],
            can_return=actions["return_to_ta"],
            read_only_reason=review_block_reason(sub, exam)
            or (None if any(actions.values()) else _read_only_reason(sub, user)),
        ),
        navigation=await navigation(db, user, sub),
    )


def _read_only_reason(sub: StudentSubmission, user: User | None) -> str:
    if sub.review_status == ReviewStatus.ESCALATED:
        return "Escalated to the professor — awaiting resolution"
    if sub.review_status in HUMAN_REVIEWED_STATUSES and (user is None or user.role == UserRole.TA):
        return "Approved by the professor"
    return "No review actions available"

