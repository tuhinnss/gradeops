"""Gradebook assembly and professor finalisation (approve → lock → publish, reopen).

Invariants:
* An exam can only be approved when every submission has been evaluated and
  reviewed by a human (no AI-only grades, no open escalations).
* Publishing requires professor approval of every submission; open integrity
  flags must be explicitly acknowledged.
* Once locked/published nothing changes until an explicit, audited reopen.
"""

import csv
import io
import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.models import (
    FROZEN_EXAM_STATUSES,
    TA_REVIEWED_STATUSES,
    Course,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamStatus,
    ReviewAudit,
    ReviewStatus,
    Rubric,
    Student,
    StudentSubmission,
    SubmissionStatus,
    User,
)
from app.config import get_settings
from app.schemas.academic import FinalizationSummary
from app.schemas.dashboard import GradebookResponse, GradebookRow
from app.schemas.evaluation import QuestionResult
from app.schemas.rubric import RubricSchema
from app.services.pdf_annotator import PDFAnnotator
from app.services.academic import exam_counts, integrity_counts, submission_max_total, users_by_id
from app.services.exam_workflow import add_exam_audit

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    ReviewStatus.NOT_EVALUATED: "Not evaluated",
    ReviewStatus.AI_EVALUATED: "AI graded — awaiting TA",
    ReviewStatus.TA_PENDING: "Returned to TA",
    ReviewStatus.TA_APPROVED: "TA approved",
    ReviewStatus.TA_OVERRIDDEN: "TA overridden",
    ReviewStatus.ESCALATED: "Escalated",
    ReviewStatus.PROFESSOR_APPROVED: "Professor approved",
    ReviewStatus.PUBLISHED: "Published",
}


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=409, detail=detail)


def refresh_annotated_pdf(sub: StudentSubmission) -> None:
    """Re-draw the annotated sheet with the final (human-reviewed) marks. Best effort."""
    try:
        results = [QuestionResult.model_validate(r) for r in (sub.evaluation_result or {}).get("results", [])]
        answers = (sub.extracted_text or {}).get("answers", [])
        out = get_settings().output_dir / str(sub.id) / f"{sub.student_id}_final.pdf"
        PDFAnnotator().annotate(Path(sub.file_path), results, answers, out, sub.student_id)
        sub.annotated_pdf_path = str(out)
    except Exception as exc:  # the grade itself is already recorded
        logger.warning("Could not regenerate annotated PDF for %s: %s", sub.id, exc)


# --- Gradebook -------------------------------------------------------------------------


async def build_gradebook(db: AsyncSession, exam: Exam) -> GradebookResponse:
    course = await db.get(Course, exam.course_id)
    rubric = await db.get(Rubric, exam.rubric_id) if exam.rubric_id else None
    questions: list[str] = []
    rubric_max: float | None = None
    if rubric:
        schema = RubricSchema.from_dict(rubric.structured_data)
        questions = [i.question_number for i in schema.items]
        rubric_max = round(sum(i.max_marks for i in schema.items), 2)

    subs = list(
        (
            await db.execute(
                select(StudentSubmission)
                .where(StudentSubmission.exam_id == exam.id)
                .order_by(StudentSubmission.student_id, StudentSubmission.created_at)
            )
        ).scalars()
    )
    users = await users_by_id(db, [u for s in subs for u in (s.reviewed_by, s.approved_by)])
    flags = await integrity_counts(db, [s.id for s in subs])
    record_ids = {s.student_record_id for s in subs if s.student_record_id}

    roster = (
        await db.execute(
            select(Student)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.course_id == exam.course_id, Enrollment.status == EnrollmentStatus.ACTIVE)
        )
    ).scalars().all()
    names = {st.id: st.name for st in roster}
    if record_ids - names.keys():
        extra = (await db.execute(select(Student).where(Student.id.in_(record_ids - names.keys())))).scalars()
        names.update({st.id: st.name for st in extra})

    rows: list[GradebookRow] = []
    for s in subs:
        results = (s.evaluation_result or {}).get("results", [])
        if not questions and results:
            questions = [str(r.get("question")) for r in results]
        max_score = submission_max_total(s) or rubric_max or exam.total_marks
        evaluated = s.status == SubmissionStatus.EVALUATED
        final = s.total_marks if evaluated else None
        label = STATUS_LABELS[s.review_status] if evaluated else s.status.value.replace("_", " ").capitalize()
        rows.append(
            GradebookRow(
                submission_id=s.id,
                student_id=s.student_id,
                student_name=names.get(s.student_record_id) if s.student_record_id else None,
                ai_score=s.ai_total_marks,
                ta_score=s.ta_total_marks,
                professor_score=s.professor_total_marks,
                final_score=final,
                max_score=max_score,
                percentage=round(final / max_score * 100, 1) if final is not None and max_score else None,
                review_status=s.review_status,
                status_label=label,
                integrity_flags=flags.get(s.id, 0),
                reviewed_by=users[s.reviewed_by].full_name if s.reviewed_by in users else None,
                approved_by=users[s.approved_by].full_name if s.approved_by in users else None,
                overridden=(
                    s.ai_total_marks is not None
                    and final is not None
                    and abs(float(s.ai_total_marks) - float(final)) > 1e-6
                ),
                question_scores={
                    str(r.get("question")): float(r.get("marks_awarded", 0)) for r in results
                },
            )
        )

    submitted = {s.student_record_id for s in subs if s.student_record_id} | {
        st.id for st in roster if st.student_id in {s.student_id for s in subs}
    }
    for st in roster:
        if st.id not in submitted:
            rows.append(
                GradebookRow(
                    submission_id=None, student_id=st.student_id, student_name=st.name,
                    ai_score=None, ta_score=None, professor_score=None, final_score=None,
                    max_score=rubric_max or exam.total_marks, percentage=None,
                    review_status=None, status_label="No submission",
                )
            )
    rows.sort(key=lambda r: r.student_id)
    return GradebookResponse(
        exam_id=exam.id,
        exam_name=exam.name,
        course_code=course.course_code if course else "",
        status=exam.status,
        max_score=rubric_max or exam.total_marks,
        questions=questions,
        rows=rows,
        is_final=exam.status in (ExamStatus.APPROVED, ExamStatus.LOCKED, ExamStatus.PUBLISHED),
    )


def gradebook_csv(gb: GradebookResponse, final_only: bool = False) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    header = [
        "student_id", "student_name", "ai_score", "ta_score", "professor_score",
        "final_score", "max_score", "percentage", "status", "integrity_flags",
        "reviewed_by", "approved_by", *gb.questions,
    ]
    if not final_only:
        header.insert(0, "grade_status")
    writer.writerow(header)
    for r in gb.rows:
        row = [
            r.student_id, r.student_name or "", _fmt(r.ai_score), _fmt(r.ta_score),
            _fmt(r.professor_score), _fmt(r.final_score), _fmt(r.max_score), _fmt(r.percentage),
            r.status_label, r.integrity_flags, r.reviewed_by or "", r.approved_by or "",
            *(_fmt(r.question_scores.get(q)) for q in gb.questions),
        ]
        if not final_only:
            row.insert(0, "FINAL" if gb.is_final else "PROVISIONAL")
        writer.writerow([_csv_safe(v) for v in row])
    return out.getvalue()


def _fmt(v: float | None) -> str:
    return "" if v is None else f"{v:g}"


def _csv_safe(value: object) -> object:
    """Neutralise spreadsheet formula injection in user-supplied text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@") and not _is_number(value):
        return "'" + value
    return value


def _is_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


# --- Finalisation ----------------------------------------------------------------------


async def finalization_summary(db: AsyncSession, exam: Exam) -> FinalizationSummary:
    c = (await exam_counts(db, [exam.id]))[exam.id]
    override_rows = (
        await db.execute(
            select(ReviewAudit.submission_id, ReviewAudit.actor_role)
            .join(StudentSubmission, StudentSubmission.id == ReviewAudit.submission_id)
            .where(StudentSubmission.exam_id == exam.id, ReviewAudit.action == "override")
        )
    ).all()
    ta_overrides = len({sid for sid, role in override_rows if role == "ta"})
    prof_overrides = len({sid for sid, role in override_rows if role == "professor"})
    not_evaluated = c.uploaded + c.processing

    blockers: list[str] = []
    if c.submissions == 0:
        blockers.append("No submissions uploaded")
    if not_evaluated:
        blockers.append(f"{not_evaluated} submission(s) not yet evaluated")
    if c.failed:
        blockers.append(f"{c.failed} submission(s) failed processing — re-run or remove them")
    if c.awaiting_ta:
        blockers.append(f"{c.awaiting_ta} submission(s) still awaiting human review")
    if c.escalated:
        blockers.append(f"{c.escalated} escalation(s) unresolved")
    warnings: list[str] = []
    if c.integrity_open:
        warnings.append(f"{c.integrity_open} similarity flag(s) not yet reviewed")

    reviewable = exam.status == ExamStatus.TA_REVIEW
    can_approve = reviewable and not blockers
    can_lock = exam.status == ExamStatus.APPROVED
    can_publish = exam.status in (ExamStatus.APPROVED, ExamStatus.LOCKED) and not blockers
    if exam.status in (ExamStatus.DRAFT, ExamStatus.PROCESSING):
        blockers.insert(0, f"Exam is in {exam.status.value} state")
    return FinalizationSummary(
        exam_id=exam.id,
        status=exam.status,
        total=c.submissions,
        evaluated=c.processed,
        not_evaluated=not_evaluated,
        failed=c.failed,
        awaiting_ta=c.awaiting_ta,
        ta_reviewed=c.ta_reviewed,
        escalated=c.escalated,
        professor_approved=c.professor_approved,
        published=c.published,
        ta_overrides=ta_overrides,
        professor_overrides=prof_overrides,
        integrity_open=c.integrity_open,
        needs_manual_grading=c.needs_manual_grading,
        can_approve=can_approve,
        can_lock=can_lock,
        can_publish=can_publish,
        can_reopen=exam.status in (ExamStatus.APPROVED, ExamStatus.LOCKED, ExamStatus.PUBLISHED),
        blockers=blockers,
        warnings=warnings,
    )


async def approve_exam(db: AsyncSession, exam: Exam, actor: User, notes: str | None) -> None:
    summary = await finalization_summary(db, exam)
    if exam.status != ExamStatus.TA_REVIEW:
        raise _conflict(f"Only exams in TA review can be approved (current: {exam.status.value})")
    if not summary.can_approve:
        raise _conflict("Cannot approve: " + "; ".join(summary.blockers))
    now = datetime.now(UTC)
    to_approve = list(
        (
            await db.execute(
                select(StudentSubmission).where(
                    StudentSubmission.exam_id == exam.id,
                    StudentSubmission.review_status.in_(TA_REVIEWED_STATUSES),
                )
            )
        ).scalars()
    )
    for sub in to_approve:
        await crud.add_review_audit(
            db,
            submission_id=sub.id,
            reviewer_id=actor.id,
            action="professor_approve_exam",
            actor_role=actor.role.value,
            from_status=sub.review_status.value,
            to_status=ReviewStatus.PROFESSOR_APPROVED.value,
            notes=notes,
        )
        sub.review_status = ReviewStatus.PROFESSOR_APPROVED
        sub.professor_total_marks = sub.total_marks
        sub.approved_by = actor.id
        sub.approved_at = now
    previous = exam.status
    exam.status = ExamStatus.APPROVED
    exam.approved_at = now
    await add_exam_audit(
        db, exam, action="approve", actor_id=actor.id, from_status=previous, notes=notes,
        details={**summary.model_dump(mode="json", include={"total", "ta_overrides", "professor_overrides", "integrity_open"}), "bulk_approved": len(to_approve)},
    )


async def lock_exam(db: AsyncSession, exam: Exam, actor: User, notes: str | None) -> None:
    if exam.status != ExamStatus.APPROVED:
        raise _conflict("Only approved exams can be locked")
    previous = exam.status
    exam.status = ExamStatus.LOCKED
    exam.locked_at = datetime.now(UTC)
    await add_exam_audit(db, exam, action="lock", actor_id=actor.id, from_status=previous, notes=notes)


async def publish_exam(
    db: AsyncSession, exam: Exam, actor: User, notes: str | None, acknowledge_integrity: bool
) -> None:
    summary = await finalization_summary(db, exam)
    if exam.status not in (ExamStatus.APPROVED, ExamStatus.LOCKED):
        raise _conflict("Approve the exam before publishing grades")
    if summary.blockers:
        raise _conflict("Cannot publish: " + "; ".join(summary.blockers))
    if summary.professor_approved != summary.total:
        raise _conflict("Every submission must be approved by the professor before publishing")
    if summary.integrity_open and not acknowledge_integrity:
        raise _conflict(
            f"{summary.integrity_open} similarity flag(s) are unresolved; review them or "
            "acknowledge to publish anyway"
        )
    now = datetime.now(UTC)
    subs = list(
        (
            await db.execute(
                select(StudentSubmission).where(
                    StudentSubmission.exam_id == exam.id,
                    StudentSubmission.review_status == ReviewStatus.PROFESSOR_APPROVED,
                )
            )
        ).scalars()
    )
    for sub in subs:
        await crud.add_review_audit(
            db,
            submission_id=sub.id,
            reviewer_id=actor.id,
            action="publish",
            actor_role=actor.role.value,
            from_status=ReviewStatus.PROFESSOR_APPROVED.value,
            to_status=ReviewStatus.PUBLISHED.value,
            new_marks=sub.total_marks,
        )
        sub.review_status = ReviewStatus.PUBLISHED
        refresh_annotated_pdf(sub)
    previous = exam.status
    exam.status = ExamStatus.PUBLISHED
    exam.published_at = now
    exam.locked_at = exam.locked_at or now
    await add_exam_audit(
        db, exam, action="publish", actor_id=actor.id, from_status=previous, notes=notes,
        details=summary.model_dump(
            mode="json",
            include={"total", "ta_overrides", "professor_overrides", "integrity_open", "needs_manual_grading"},
        ) | {"integrity_acknowledged": bool(summary.integrity_open and acknowledge_integrity)},
    )


async def reopen_exam(db: AsyncSession, exam: Exam, actor: User, reason: str) -> None:
    if exam.status not in (ExamStatus.APPROVED, ExamStatus.LOCKED, ExamStatus.PUBLISHED):
        raise _conflict("Only approved, locked or published exams can be reopened")
    previous = exam.status
    published = list(
        (
            await db.execute(
                select(StudentSubmission).where(
                    StudentSubmission.exam_id == exam.id,
                    StudentSubmission.review_status == ReviewStatus.PUBLISHED,
                )
            )
        ).scalars()
    )
    for sub in published:
        await crud.add_review_audit(
            db,
            submission_id=sub.id,
            reviewer_id=actor.id,
            action="reopen",
            actor_role=actor.role.value,
            from_status=ReviewStatus.PUBLISHED.value,
            to_status=ReviewStatus.PROFESSOR_APPROVED.value,
            notes=reason,
        )
    await db.execute(
        update(StudentSubmission)
        .where(
            StudentSubmission.exam_id == exam.id,
            StudentSubmission.review_status == ReviewStatus.PUBLISHED,
        )
        .values(review_status=ReviewStatus.PROFESSOR_APPROVED)
    )
    exam.status = ExamStatus.TA_REVIEW
    exam.approved_at = None
    exam.locked_at = None
    exam.published_at = None
    await add_exam_audit(
        db, exam, action="reopen", actor_id=actor.id, from_status=previous, notes=reason,
        details={"unpublished_submissions": len(published)},
    )


def ensure_exam_editable(exam: Exam) -> None:
    if exam.status in FROZEN_EXAM_STATUSES or exam.status == ExamStatus.APPROVED:
        raise _conflict(f"Exam is {exam.status.value}; reopen it before making changes")
