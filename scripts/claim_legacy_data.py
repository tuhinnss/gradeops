"""Attach pre-course (legacy) rubrics and submissions to a professor's course.

Submissions uploaded before courses existed have no course/exam/owner, so they
are only reachable in AUTH_ENABLED=false demo mode. This script gives them an
owner without altering grades:

    python -m scripts.claim_legacy_data --professor prof@uni.edu            # dry run
    python -m scripts.claim_legacy_data --professor prof@uni.edu --apply

For each legacy rubric with unowned submissions it creates (in a course
"LEGACY" owned by the professor) one exam named after the rubric, links the
submissions to it, enrols their students and records the change in the exam
audit log. Exams start in TA_REVIEW (or DRAFT if nothing was evaluated), so every
grade still needs human review before it can be published.
"""

import argparse
import asyncio
import sys
from collections import defaultdict

from sqlalchemy import select

from app.db import crud
from app.db.models import (
    Course,
    CourseStatus,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamStatus,
    Rubric,
    Student,
    StudentSubmission,
    SubmissionStatus,
    UserRole,
)
from app.db.session import async_session_factory, engine
from app.services.exam_workflow import add_exam_audit


async def main(args: argparse.Namespace) -> None:
    async with async_session_factory() as db:
        prof = await crud.get_user_by_email(db, args.professor)
        if not prof or prof.role != UserRole.PROFESSOR:
            sys.exit(f"{args.professor} is not a professor account")
        orphans = list(
            (
                await db.execute(
                    select(StudentSubmission).where(
                        StudentSubmission.exam_id.is_(None), StudentSubmission.uploaded_by.is_(None)
                    )
                )
            ).scalars()
        )
        by_rubric: dict = defaultdict(list)
        for sub in orphans:
            by_rubric[sub.rubric_id].append(sub)
        print(f"{len(orphans)} legacy submission(s) across {len(by_rubric)} rubric group(s)")
        for rid, subs in by_rubric.items():
            rubric = await db.get(Rubric, rid) if rid else None
            print(f"  - {rubric.name if rubric else '(no rubric)'}: {len(subs)} submission(s)")
        if not args.apply:
            print("Dry run — re-run with --apply to claim them.")
            return

        course = await db.scalar(
            select(Course).where(Course.professor_id == prof.id, Course.course_code == "LEGACY")
        )
        if not course:
            course = Course(name="Legacy imports", course_code="LEGACY", professor_id=prof.id, status=CourseStatus.ACTIVE)
            db.add(course)
            await db.flush()
        for rid, subs in by_rubric.items():
            rubric = await db.get(Rubric, rid) if rid else None
            if rubric and rubric.owner_id is None:
                rubric.owner_id = prof.id
            evaluated = any(s.status == SubmissionStatus.EVALUATED for s in subs)
            exam = Exam(
                course_id=course.id,
                name=f"Legacy: {rubric.name if rubric else 'no rubric'}",
                rubric_id=rid,
                created_by=prof.id,
                status=ExamStatus.TA_REVIEW if evaluated else ExamStatus.DRAFT,
            )
            db.add(exam)
            await db.flush()
            for sub in subs:
                student = await db.scalar(select(Student).where(Student.student_id == sub.student_id))
                if not student:
                    student = Student(student_id=sub.student_id, name="")
                    db.add(student)
                    await db.flush()
                if not await db.scalar(
                    select(Enrollment).where(Enrollment.course_id == course.id, Enrollment.student_id == student.id)
                ):
                    db.add(Enrollment(course_id=course.id, student_id=student.id, status=EnrollmentStatus.ACTIVE))
                sub.exam_id, sub.course_id, sub.student_record_id = exam.id, course.id, student.id
                sub.uploaded_by = prof.id
            await add_exam_audit(
                db, exam, action="legacy_claimed", actor_id=prof.id,
                details={"submissions": len(subs)}, notes="Claimed via scripts.claim_legacy_data",
            )
        await db.commit()
        print(f"Claimed into course LEGACY ({course.id}).")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--professor", required=True, help="Email of the professor who will own the data")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args()))
