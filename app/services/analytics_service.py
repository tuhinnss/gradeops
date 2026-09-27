"""Exam- and course-level analytics computed from persisted grading data."""

import statistics
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    TA_QUEUE_STATUSES,
    TA_REVIEWED_STATUSES,
    Exam,
    IntegrityFlag,
    IntegrityFlagStatus,
    ReviewAudit,
    ReviewStatus,
    Rubric,
    StudentSubmission,
    SubmissionStatus,
)
from app.schemas.dashboard import (
    CourseAnalyticsResponse,
    CourseExamSummary,
    CriterionStats,
    DistributionBucket,
    ExamAnalyticsResponse,
    IntegrityStats,
    QuestionStats,
    ReviewStats,
    ScoreSummary,
    StudentScore,
)
from app.services.academic import rubric_stats, student_names, submission_max_total

EPS = 1e-6


def score_summary(values: list[float], max_total: float | None) -> ScoreSummary:
    if not values:
        return ScoreSummary(
            count=0, average=None, median=None, highest=None, lowest=None,
            std_dev=None, max_total=max_total, average_pct=None,
        )
    avg = statistics.fmean(values)
    return ScoreSummary(
        count=len(values),
        average=round(avg, 2),
        median=round(statistics.median(values), 2),
        highest=round(max(values), 2),
        lowest=round(min(values), 2),
        std_dev=round(statistics.pstdev(values), 2) if len(values) > 1 else 0.0,
        max_total=max_total,
        average_pct=round(avg / max_total * 100, 1) if max_total else None,
    )


def distribution(percentages: list[float]) -> list[DistributionBucket]:
    buckets = [
        DistributionBucket(label=f"{lo}–{lo + 10}%", lower_pct=lo, upper_pct=lo + 10, count=0)
        for lo in range(0, 100, 10)
    ]
    for pct in percentages:
        idx = min(int(max(pct, 0) // 10), 9)
        buckets[idx].count += 1
    return buckets


async def _evaluated(db: AsyncSession, exam_id: uuid.UUID) -> list[StudentSubmission]:
    return list(
        (
            await db.execute(
                select(StudentSubmission)
                .where(
                    StudentSubmission.exam_id == exam_id,
                    StudentSubmission.status == SubmissionStatus.EVALUATED,
                )
                .order_by(StudentSubmission.student_id)
            )
        ).scalars()
    )


async def _exam_max_total(db: AsyncSession, exam: Exam, subs: list[StudentSubmission]) -> float | None:
    if exam.rubric_id:
        rubric = await db.get(Rubric, exam.rubric_id)
        if rubric:
            total = rubric_stats(rubric)[1]
            if total:
                return total
    seen = [m for m in (submission_max_total(s) for s in subs) if m]
    return max(seen) if seen else exam.total_marks


async def exam_analytics(
    db: AsyncSession, exam: Exam, include_students: bool = True
) -> ExamAnalyticsResponse:
    subs = await _evaluated(db, exam.id)
    max_total = await _exam_max_total(db, exam, subs)
    finals = [float(s.total_marks or 0) for s in subs]
    pcts = [
        f / (submission_max_total(s) or max_total) * 100
        for f, s in zip(finals, subs, strict=True)
        if (submission_max_total(s) or max_total)
    ]

    # Per-question and per-criterion statistics from stored results.
    q_marks: dict[str, list[float]] = defaultdict(list)
    q_ai: dict[str, list[float]] = defaultdict(list)
    q_conf: dict[str, list[float]] = defaultdict(list)
    q_max: dict[str, float] = {}
    q_overridden: dict[str, int] = defaultdict(int)
    q_order: list[str] = []
    crit: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0])  # evaluated, missed, partial
    for s in subs:
        for r in (s.evaluation_result or {}).get("results", []):
            q = str(r.get("question", "?"))
            if q not in q_max:
                q_order.append(q)
            marks = float(r.get("marks_awarded", 0))
            q_marks[q].append(marks)
            q_max[q] = float(r.get("max_marks", 0))
            ai = r.get("ai_marks_awarded")
            if ai is not None:
                q_ai[q].append(float(ai))
                if abs(float(ai) - marks) > EPS:
                    q_overridden[q] += 1
            if r.get("confidence") is not None:
                q_conf[q].append(float(r["confidence"]))
            for c in r.get("criteria", []) or []:
                if c.get("kind", "key_point") != "key_point":
                    continue
                entry = crit[(q, str(c.get("criterion", "")))]
                entry[0] += 1
                if c.get("status") == "missed":
                    entry[1] += 1
                elif c.get("status") == "partial":
                    entry[2] += 1

    questions = []
    for q in q_order:
        marks, mx = q_marks[q], q_max[q]
        n = len(marks)
        full = sum(1 for m in marks if mx and m >= mx - EPS)
        zero = sum(1 for m in marks if m <= EPS)
        avg = statistics.fmean(marks) if marks else 0.0
        questions.append(
            QuestionStats(
                question=q,
                max_marks=mx,
                attempts=n,
                average=round(avg, 2),
                average_pct=round(avg / mx * 100, 1) if mx else 0.0,
                ai_average=round(statistics.fmean(q_ai[q]), 2) if q_ai[q] else None,
                full_credit_pct=round(full / n * 100, 1) if n else 0.0,
                partial_pct=round((n - full - zero) / n * 100, 1) if n else 0.0,
                zero_pct=round(zero / n * 100, 1) if n else 0.0,
                average_confidence=round(statistics.fmean(q_conf[q]), 3) if q_conf[q] else None,
                overridden=q_overridden[q],
            )
        )
    criteria = sorted(
        (
            CriterionStats(
                question=q,
                criterion=c,
                evaluated=v[0],
                missed_rate=round(v[1] / v[0] * 100, 1) if v[0] else 0.0,
                partial_rate=round(v[2] / v[0] * 100, 1) if v[0] else 0.0,
            )
            for (q, c), v in crit.items()
        ),
        key=lambda x: -x.missed_rate,
    )

    # Review lifecycle and override rates (from audits, not inferred).
    by_status: dict[ReviewStatus, int] = defaultdict(int)
    for s in subs:
        by_status[s.review_status] += 1
    sub_ids = [s.id for s in subs]
    ta_touched = ta_overrode = prof_overrode = 0
    if sub_ids:
        audit_rows = (
            await db.execute(
                select(ReviewAudit.submission_id, ReviewAudit.action, ReviewAudit.actor_role).where(
                    ReviewAudit.submission_id.in_(sub_ids),
                    ReviewAudit.action.in_(("approve", "override", "escalate")),
                )
            )
        ).all()
        ta_subs = {sid for sid, _, role in audit_rows if role == "ta"}
        ta_touched = len(ta_subs)
        ta_overrode = len({sid for sid, action, role in audit_rows if role == "ta" and action == "override"})
        prof_overrode = len(
            {sid for sid, action, role in audit_rows if role == "professor" and action == "override"}
        )
    prof_decided = by_status[ReviewStatus.PROFESSOR_APPROVED] + by_status[ReviewStatus.PUBLISHED]
    pairs = [
        (float(s.ai_total_marks), float(s.ta_total_marks))
        for s in subs
        if s.ai_total_marks is not None and s.ta_total_marks is not None
    ]
    review = ReviewStats(
        ai_evaluated=len(subs),
        awaiting_ta=sum(by_status[st] for st in TA_QUEUE_STATUSES),
        ta_reviewed=sum(by_status[st] for st in TA_REVIEWED_STATUSES),
        escalated=by_status[ReviewStatus.ESCALATED],
        professor_approved=by_status[ReviewStatus.PROFESSOR_APPROVED],
        published=by_status[ReviewStatus.PUBLISHED],
        ta_override_rate=round(ta_overrode / ta_touched * 100, 1) if ta_touched else None,
        professor_override_rate=round(prof_overrode / prof_decided * 100, 1) if prof_decided else None,
        ai_ta_disagreement_rate=(
            round(sum(1 for a, t in pairs if abs(a - t) > EPS) / len(pairs) * 100, 1) if pairs else None
        ),
        ai_ta_mean_abs_diff=(
            round(statistics.fmean(abs(a - t) for a, t in pairs), 2) if pairs else None
        ),
    )

    flag_counts = dict(
        (
            await db.execute(
                select(IntegrityFlag.status, func.count())
                .where(IntegrityFlag.exam_id == exam.id)
                .group_by(IntegrityFlag.status)
            )
        ).all()
    )
    integrity = IntegrityStats(
        open=flag_counts.get(IntegrityFlagStatus.OPEN, 0),
        dismissed=flag_counts.get(IntegrityFlagStatus.DISMISSED, 0),
        confirmed=flag_counts.get(IntegrityFlagStatus.CONFIRMED, 0),
    )

    students = None
    if include_students:
        names = await student_names(db, (s.student_record_id for s in subs))
        students = sorted(
            (
                StudentScore(
                    submission_id=s.id,
                    student_id=s.student_id,
                    student_name=names.get(s.student_record_id) if s.student_record_id else None,
                    final_score=s.total_marks,
                    percentage=(
                        round(float(s.total_marks or 0) / (submission_max_total(s) or max_total) * 100, 1)
                        if (submission_max_total(s) or max_total)
                        else None
                    ),
                )
                for s in subs
            ),
            key=lambda x: -(x.final_score or 0),
        )

    return ExamAnalyticsResponse(
        exam_id=exam.id,
        exam_name=exam.name,
        summary=score_summary(finals, max_total),
        distribution=distribution(pcts),
        questions=questions,
        criteria=criteria[:50],
        review=review,
        integrity=integrity,
        students=students,
    )


async def course_analytics(db: AsyncSession, course_id: uuid.UUID) -> CourseAnalyticsResponse:
    exams = list(
        (await db.execute(select(Exam).where(Exam.course_id == course_id).order_by(Exam.created_at))).scalars()
    )
    summaries: list[CourseExamSummary] = []
    all_pcts: list[float] = []
    for exam in exams:
        subs = await _evaluated(db, exam.id)
        max_total = await _exam_max_total(db, exam, subs)
        finals = [float(s.total_marks or 0) for s in subs]
        if max_total:
            all_pcts.extend(f / max_total * 100 for f in finals)
        summaries.append(
            CourseExamSummary(
                exam_id=exam.id, exam_name=exam.name, status=exam.status,
                summary=score_summary(finals, max_total),
            )
        )
    return CourseAnalyticsResponse(
        course_id=course_id, exams=summaries, overall=score_summary(all_pcts, 100.0)
    )
