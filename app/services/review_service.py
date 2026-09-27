"""The one implementation of human review decisions (TA and professor).

Every state change is validated against the review lifecycle, the actor's role
and the exam state, and is written to ``review_audits`` (old/new marks, reviewer,
timestamp, reason, notes, status transition).
"""

import copy
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.models import (
    FROZEN_EXAM_STATUSES,
    Exam,
    ExamStatus,
    ReviewAudit,
    ReviewStatus,
    StudentSubmission,
    SubmissionStatus,
    User,
    UserRole,
)
from app.schemas.review import ESCALATION_REASON_LABELS, QuestionOverride, ReviewActionRequest

ESCALATION_REASONS = set(ESCALATION_REASON_LABELS) - {"legacy_rejected"}

# States in which a TA may still record (or change) their decision.
TA_ACTIONABLE = {
    ReviewStatus.AI_EVALUATED,
    ReviewStatus.TA_PENDING,
    ReviewStatus.TA_APPROVED,
    ReviewStatus.TA_OVERRIDDEN,
}
# States a professor may act on (PUBLISHED is always frozen by the exam status).
PROFESSOR_ACTIONABLE = TA_ACTIONABLE | {ReviewStatus.ESCALATED, ReviewStatus.PROFESSOR_APPROVED}

MARKS_EPSILON = 1e-6


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _bad_request(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def review_block_reason(submission: StudentSubmission, exam: Exam | None) -> str | None:
    """Why no review action is possible right now (None = actions possible)."""
    if submission.status != SubmissionStatus.EVALUATED or not submission.evaluation_result:
        return "Submission has not been evaluated yet"
    if exam and exam.status in FROZEN_EXAM_STATUSES:
        return f"Grades are {exam.status.value}; the professor must reopen the exam to make changes"
    if exam and exam.status == ExamStatus.PROCESSING:
        return "AI evaluation is running for this exam"
    return None


def allowed_actions(
    submission: StudentSubmission, exam: Exam | None, actor: User | None
) -> dict[str, bool]:
    """Which actions the UI should offer (the backend re-validates on submit)."""
    none = dict.fromkeys(("approve", "override", "escalate", "resolve", "return_to_ta"), False)
    if review_block_reason(submission, exam):
        return none
    current = submission.review_status
    if actor is not None and actor.role == UserRole.PROFESSOR:
        return {
            "approve": current in PROFESSOR_ACTIONABLE and current != ReviewStatus.PROFESSOR_APPROVED,
            "override": current in PROFESSOR_ACTIONABLE,
            "escalate": False,
            "resolve": current == ReviewStatus.ESCALATED,
            "return_to_ta": current in PROFESSOR_ACTIONABLE and current != ReviewStatus.TA_PENDING,
        }
    ta_ok = current in TA_ACTIONABLE and not (exam and exam.status == ExamStatus.APPROVED)
    return {
        "approve": ta_ok,
        "override": ta_ok,
        "escalate": ta_ok,
        "resolve": False,
        "return_to_ta": False,
    }


async def _original_ai_marks(db: AsyncSession, submission_id: uuid.UUID, question: str) -> float | None:
    """For results stored before ``ai_marks_awarded`` existed: earliest overridden value."""
    return await db.scalar(
        select(ReviewAudit.old_marks)
        .where(
            ReviewAudit.submission_id == submission_id,
            ReviewAudit.question == question,
            ReviewAudit.action == "override",
        )
        .order_by(ReviewAudit.created_at.asc())
        .limit(1)
    )


async def _apply_overrides(
    db: AsyncSession,
    submission: StudentSubmission,
    overrides: list[QuestionOverride],
) -> tuple[dict, list[tuple[str, float, float, str | None, str | None]]]:
    """Validate and apply mark overrides to a deep copy of the stored results.

    Returns (new evaluation_result, [(question, old, new, old_comment, new_comment)]).
    """
    eval_data = copy.deepcopy(submission.evaluation_result)
    results: list[dict] = eval_data.get("results", [])
    by_question = {str(r.get("question", "")).upper(): r for r in results}
    seen: set[str] = set()
    changes: list[tuple[str, float, float, str | None, str | None]] = []

    for ov in overrides:
        key = ov.question.strip().upper()
        if key in seen:
            raise _bad_request(f"Question {ov.question} listed more than once")
        seen.add(key)
        row = by_question.get(key)
        if row is None:
            raise _bad_request(f"Unknown question {ov.question}")
        max_marks = float(row.get("max_marks", 0))
        new_marks = round(float(ov.marks_awarded), 2)
        if new_marks < 0 or new_marks > max_marks + MARKS_EPSILON:
            raise _bad_request(
                f"Marks for {row['question']} must be between 0 and {max_marks:g}",
                422,
            )
        old_marks = float(row.get("marks_awarded", 0))
        if abs(new_marks - old_marks) < MARKS_EPSILON and not ov.justification:
            continue
        if row.get("ai_marks_awarded") is None:
            original = await _original_ai_marks(db, submission.id, row["question"])
            row["ai_marks_awarded"] = original if original is not None else old_marks
        old_comment = row.get("reviewer_comment")
        row["marks_awarded"] = new_marks
        if ov.justification:
            row["reviewer_comment"] = ov.justification
        changes.append((row["question"], old_marks, new_marks, old_comment, ov.justification))

    eval_data["results"] = results
    eval_data["total"] = round(sum(float(r.get("marks_awarded", 0)) for r in results), 2)
    return eval_data, changes


async def apply_review_action(
    db: AsyncSession,
    submission: StudentSubmission,
    actor: User | None,
    body: ReviewActionRequest,
) -> StudentSubmission:
    """Validate and persist one review decision. ``actor=None`` = legacy open mode."""
    exam = await db.get(Exam, submission.exam_id) if submission.exam_id else None
    blocked = review_block_reason(submission, exam)
    if blocked:
        raise _conflict(blocked)
    if body.expected_review_status and body.expected_review_status != submission.review_status:
        raise _conflict(
            f"Submission is now {submission.review_status.value}; reload before acting"
        )

    is_professor = actor is not None and actor.role == UserRole.PROFESSOR
    role_label = actor.role.value if actor else "anonymous"
    action = body.action.strip().lower()
    reason = (body.reason or "").strip() or None
    notes = (body.notes or "").strip() or None
    if action == "reject":  # legacy alias
        action, reason = "escalate", reason or "ai_grading_incorrect"

    current = submission.review_status
    now = datetime.now(UTC)
    if not is_professor and exam and exam.status == ExamStatus.APPROVED:
        raise _conflict("The professor has approved this exam; only the professor can change grades")

    def check_state() -> None:
        allowed = PROFESSOR_ACTIONABLE if is_professor else TA_ACTIONABLE
        if current in allowed:
            return
        if current == ReviewStatus.ESCALATED:
            raise _conflict("Escalated submissions can only be resolved by the professor")
        if current == ReviewStatus.PROFESSOR_APPROVED:
            raise _conflict("Already approved by the professor")
        raise _conflict(f"Cannot {action} a submission in state {current.value}")

    async def audit(action_name: str, to: ReviewStatus, **extra) -> None:
        await crud.add_review_audit(
            db,
            submission_id=submission.id,
            reviewer_id=actor.id if actor else None,
            action=action_name,
            notes=notes,
            actor_role=role_label,
            from_status=current.value,
            to_status=to.value,
            **extra,
        )

    def mark_professor_approved(total: float) -> None:
        submission.review_status = ReviewStatus.PROFESSOR_APPROVED
        submission.professor_total_marks = total
        submission.approved_by = actor.id if actor else None
        submission.approved_at = now

    def mark_ta_reviewed(new_status: ReviewStatus, total: float) -> None:
        submission.review_status = new_status
        submission.ta_total_marks = total
        submission.reviewed_by = actor.id if actor else None
        submission.reviewed_at = now

    async def record_overrides(target: ReviewStatus) -> float:
        if not body.overrides:
            raise _bad_request("No question overrides supplied")
        if not reason or len(reason) < 3:
            raise _bad_request("A reason is required when overriding marks")
        eval_data, changes = await _apply_overrides(db, submission, body.overrides)
        if not changes:
            raise _bad_request("No marks were changed")
        for question, old, new, old_comment, new_comment in changes:
            await audit(
                "override",
                target,
                question=question,
                old_marks=old,
                new_marks=new,
                old_remarks=old_comment,
                new_remarks=new_comment,
                reason=reason,
            )
        submission.evaluation_result = eval_data
        submission.total_marks = eval_data["total"]
        return eval_data["total"]

    total = float(submission.total_marks or 0)

    if action == "approve":
        check_state()
        if is_professor:
            if current == ReviewStatus.PROFESSOR_APPROVED:
                raise _conflict("Already approved by the professor")
            await audit("approve", ReviewStatus.PROFESSOR_APPROVED)
            mark_professor_approved(total)
        else:
            await audit("approve", ReviewStatus.TA_APPROVED)
            mark_ta_reviewed(ReviewStatus.TA_APPROVED, total)

    elif action == "override":
        check_state()
        target = ReviewStatus.PROFESSOR_APPROVED if is_professor else ReviewStatus.TA_OVERRIDDEN
        total = await record_overrides(target)
        if is_professor:
            mark_professor_approved(total)
        else:
            mark_ta_reviewed(ReviewStatus.TA_OVERRIDDEN, total)

    elif action == "escalate":
        if is_professor:
            raise _bad_request("Professors resolve escalations; use approve, override or return_to_ta")
        check_state()
        if reason not in ESCALATION_REASONS:
            raise _bad_request(
                f"Escalation reason must be one of: {', '.join(sorted(ESCALATION_REASONS))}",
                422,
            )
        if reason == "other" and not notes:
            raise _bad_request("Describe the issue in notes when the reason is 'other'")
        await audit("escalate", ReviewStatus.ESCALATED, reason=reason)
        submission.review_status = ReviewStatus.ESCALATED
        submission.escalation_reason = reason
        submission.escalation_notes = notes
        submission.escalated_by = actor.id if actor else None
        submission.escalated_at = now

    elif action == "resolve":
        if not is_professor:
            raise HTTPException(status_code=403, detail="Only the professor can resolve escalations")
        if current != ReviewStatus.ESCALATED:
            raise _conflict("Only escalated submissions can be resolved; use approve instead")
        if body.overrides:
            total = await record_overrides(ReviewStatus.PROFESSOR_APPROVED)
        await audit("resolve", ReviewStatus.PROFESSOR_APPROVED, reason=reason)
        mark_professor_approved(total)

    elif action == "return_to_ta":
        if not is_professor:
            raise HTTPException(status_code=403, detail="Only the professor can return work to TAs")
        check_state()
        if current == ReviewStatus.TA_PENDING:
            raise _conflict("Already waiting for TA review")
        if not notes:
            raise _bad_request("Add a note telling the TA what to re-check")
        await audit("return_to_ta", ReviewStatus.TA_PENDING, reason=reason)
        submission.review_status = ReviewStatus.TA_PENDING
        submission.approved_by = None
        submission.approved_at = None
        submission.professor_total_marks = None

    else:
        raise _bad_request(f"Unknown review action '{body.action}'")

    if notes:
        submission.reviewer_notes = notes
    await db.flush()
    return submission
