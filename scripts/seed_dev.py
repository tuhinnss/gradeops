"""DEVELOPMENT SEED DATA — never run against production.

Creates a small, clearly-labelled demo: a professor, two TAs, one course with a
roster, a mid-semester exam with the sample rubric, and one typed "answer
sheet" PDF per student. Answer sheets are then graded by the REAL pipeline
(OCR → segmentation → evaluation → similarity check) through the same batch
job the dashboard uses — no scores are fabricated. With --with-reviews a few
TA review actions are recorded through the normal review service so the
dashboards have activity to show.

    python -m scripts.seed_dev                 # structure + PDFs + AI grading
    python -m scripts.seed_dev --with-reviews  # plus sample TA decisions
    python -m scripts.seed_dev --no-evaluate   # leave sheets for "Evaluate" in the UI

All seed accounts use the @gradeops.dev domain and the password printed at the
end. Refuses to run when ENVIRONMENT=production or when seed data exists.
"""

import argparse
import asyncio
import json
import random
import shutil
import sys
import uuid
from pathlib import Path

import fitz
from sqlalchemy import select

from app.config import get_settings
from app.core.security import hash_password
from app.db import crud
from app.db.models import (
    Course,
    CourseMember,
    CourseStatus,
    Enrollment,
    EnrollmentStatus,
    Exam,
    ExamStatus,
    ExamTA,
    ReviewStatus,
    Student,
    StudentSubmission,
    User,
    UserRole,
)
from app.db.session import async_session_factory, engine
from app.schemas.review import QuestionOverride, ReviewActionRequest
from app.services.batch_queue import run_batch_job
from app.services.exam_workflow import add_exam_audit, mark_exam_processing
from app.services.review_service import apply_review_action
from app.services.storage import StorageService

ROOT = Path(__file__).resolve().parents[1]
RUBRIC_PATH = ROOT / "samples" / "ds_midsem_rubric.json"
PASSWORD = "gradeops-dev-2026"
SEED_TAG = "[dev seed]"

STUDENTS = [
    ("240122061", "Aarav Mehta"), ("240122062", "Bhavna Iyer"), ("240122063", "Chirag Rao"),
    ("240122064", "Divya Nair"), ("240122065", "Eshan Gupta"), ("240122066", "Farah Khan"),
    ("240122067", "Gaurav Das"), ("240122068", "Harini Pillai"), ("240122069", "Ishaan Bose"),
    ("240122070", "Jaya Menon"),
]

PARTIAL_WORK = {
    "Q1": "A stack stores items. We push things on it and pop them later.",
    "Q2": "In a BST smaller keys go to the left side of each node.",
    "Q3": "Two keys can land in the same bucket which is a collision.",
    "Q4": "BFS goes level by level using a queue.",
}
OFF_TOPIC = {
    "Q1": "Arrays are stored contiguously in memory and indexed from zero.",
    "Q2": "Sorting can be done with merge sort in n log n time = 2 x 3 + 7.",
    "Q3": "A linked list node has data and a pointer to the next node.",
    "Q4": "Graphs have vertices and edges; trees are graphs without cycles.",
}


def answer_text(question: str, key_points: list[str], quality: str, rng: random.Random) -> str:
    # Each student gets their own worked example so independent answers differ.
    example = f" For example with n = {rng.randint(3, 97)} items."
    if quality == "strong":
        return " ".join(f"{kp}." for kp in key_points) + example
    if quality == "partial":
        return PARTIAL_WORK[question] + example
    if quality == "blank":
        return ""
    return OFF_TOPIC[question] + example


def render_sheet(student_id: str, name: str, answers: dict[str, str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 40), f"{SEED_TAG} CS3001 Midsem — {student_id} {name}", fontsize=9, color=(0.5, 0.5, 0.5))
    height = (page.rect.height - 60) / len(answers)
    for i, (q, text) in enumerate(answers.items()):
        y = 60 + i * height
        page.insert_textbox(fitz.Rect(50, y, 550, y + height - 10), f"{q}. {text}", fontsize=13)
    data = doc.tobytes()
    doc.close()
    return data


async def seed(args: argparse.Namespace) -> None:
    settings = get_settings()
    if settings.environment == "production":
        sys.exit("Refusing to seed: ENVIRONMENT=production")
    rng = random.Random(42)
    rubric_data = json.loads(RUBRIC_PATH.read_text())
    items = {i["question_number"]: i["key_points"] for i in rubric_data["items"]}

    async with async_session_factory() as db:
        if await crud.get_user_by_email(db, "professor@gradeops.dev"):
            sys.exit("Seed data already present (professor@gradeops.dev exists). Use a fresh database to re-seed.")

        async def user(email: str, name: str, role: UserRole) -> User:
            return await crud.create_user(db, email=email, hashed_password=hash_password(PASSWORD), full_name=name, role=role)

        prof = await user("professor@gradeops.dev", "Dr. Meera Sharma", UserRole.PROFESSOR)
        ta1 = await user("rahul.ta@gradeops.dev", "Rahul Verma", UserRole.TA)
        ta2 = await user("ananya.ta@gradeops.dev", "Ananya Das", UserRole.TA)

        course = Course(
            name="Data Structures", course_code="CS3001", semester="Autumn", academic_year="2026-27",
            description=f"{SEED_TAG} Demo course created by scripts/seed_dev.py.",
            professor_id=prof.id, status=CourseStatus.ACTIVE,
        )
        db.add(course)
        await db.flush()
        for ta in (ta1, ta2):
            db.add(CourseMember(course_id=course.id, user_id=ta.id, role=UserRole.TA, active=True))

        students = {}
        for sid, name in STUDENTS:
            st = Student(student_id=sid, name=name, email=f"{sid}@students.gradeops.dev", metadata_={"seed": True})
            db.add(st)
            await db.flush()
            db.add(Enrollment(course_id=course.id, student_id=st.id, status=EnrollmentStatus.ACTIVE))
            students[sid] = st

        rubric = await crud.create_rubric(
            db, name="CS3001 Midsem rubric", source_filename=RUBRIC_PATH.name, source_type="json",
            structured_data=rubric_data, file_path=str(RUBRIC_PATH), owner_id=prof.id,
        )
        exam = Exam(
            course_id=course.id, name="Mid Semester Examination", exam_type="midterm", total_marks=20,
            description=SEED_TAG, rubric_id=rubric.id, created_by=prof.id, status=ExamStatus.DRAFT,
        )
        db.add(exam)
        await db.flush()
        await add_exam_audit(db, exam, action="created", actor_id=prof.id, notes=SEED_TAG)
        for ta in (ta1, ta2):
            db.add(ExamTA(exam_id=exam.id, ta_id=ta.id, active=True))

        storage = StorageService()
        profiles = ["strong", "strong", "partial", "partial", "off", "strong", "partial", "off", "strong", "partial"]
        sub_ids: list[uuid.UUID] = []
        sheets: dict[str, dict[str, str]] = {}
        for (sid, name), profile in zip(STUDENTS, profiles, strict=True):
            answers = {}
            for q, kps in items.items():
                quality = profile if profile != "partial" else rng.choice(["strong", "partial", "partial", "off"])
                answers[q] = answer_text(q, kps, quality, rng)
            sheets[sid] = answers
        # One copied sheet (of a non-model answer) so the similarity check has a
        # genuine potential match to surface for the professor.
        sheets["240122068"] = dict(sheets["240122064"])
        for sid, name in STUDENTS:
            path = storage.save_upload_file(render_sheet(sid, name, sheets[sid]), "submissions", f"{uuid.uuid4()}_{sid}_midsem.pdf")
            sub = await crud.create_submission(
                db, student_id=sid, source_filename=f"{sid}_midsem.pdf", file_path=str(path), rubric_id=rubric.id,
                uploaded_by=prof.id, course_id=course.id, exam_id=exam.id, student_record_id=students[sid].id,
            )
            sub_ids.append(sub.id)
        await db.commit()
        ids = {"prof": prof.id, "ta1": ta1.id, "exam": exam.id, "rubric": rubric.id}

    if args.no_evaluate:
        print("Answer sheets uploaded; run evaluation from the exam page.")
    else:
        if not shutil.which("tesseract") and settings.ocr_engine == "tesseract":
            print("WARNING: tesseract not found; OCR may fail. Install it or use --no-evaluate.")
        async with async_session_factory() as db:
            job = await crud.create_batch_job(
                db, rubric_id=ids["rubric"], submission_ids=[str(s) for s in sub_ids],
                run_plagiarism=True, created_by=ids["prof"], exam_id=ids["exam"],
            )
            exam = await db.get(Exam, ids["exam"])
            await mark_exam_processing(db, exam, ids["prof"], len(sub_ids))
            await db.commit()
            job_id = job.id
        print("Grading answer sheets with the real pipeline (OCR + evaluation)…")
        await run_batch_job(job_id, async_session_factory)
        async with async_session_factory() as db:
            job = await crud.get_batch_job(db, job_id)
            print(f"Batch job {job.status.value}: {job.completed_count} graded, {job.failed_count} failed")

        if args.with_reviews:
            async with async_session_factory() as db:
                ta = await db.get(User, ids["ta1"])
                subs = list(
                    (
                        await db.execute(
                            select(StudentSubmission)
                            .where(StudentSubmission.exam_id == ids["exam"], StudentSubmission.review_status == ReviewStatus.AI_EVALUATED)
                            .order_by(StudentSubmission.student_id)
                        )
                    ).scalars()
                )
                plan = [
                    ReviewActionRequest(action="approve", notes=f"{SEED_TAG} sample approval"),
                    ReviewActionRequest(action="approve", notes=f"{SEED_TAG} sample approval"),
                    ReviewActionRequest(
                        action="override", reason="Partial credit per rubric", notes=SEED_TAG,
                        overrides=[QuestionOverride(question="Q1", marks_awarded=3.0, justification="Order of operations explained")],
                    ),
                    ReviewActionRequest(action="escalate", reason="ocr_unreliable", notes=f"{SEED_TAG} handwriting on Q3 unclear"),
                ]
                for sub, body in zip(subs, plan, strict=False):
                    try:
                        await apply_review_action(db, sub, ta, body)
                    except Exception as exc:  # e.g. override equal to current mark
                        print(f"  skipped sample {body.action} for {sub.student_id}: {getattr(exc, 'detail', exc)}")
                await db.commit()
            print("Recorded sample TA decisions (see the review audit log).")

    await engine.dispose()
    print(
        "\nDEV SEED READY\n"
        f"  Professor : professor@gradeops.dev / {PASSWORD}\n"
        f"  TA        : rahul.ta@gradeops.dev  / {PASSWORD}\n"
        f"  TA        : ananya.ta@gradeops.dev / {PASSWORD}\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-evaluate", action="store_true", help="Upload sheets only; grade from the UI")
    parser.add_argument("--with-reviews", action="store_true", help="Record sample TA review actions")
    asyncio.run(seed(parser.parse_args()))
