"""Builders shared by the API tests."""

import io
import json
import uuid
from dataclasses import dataclass, field

import fitz
from httpx import AsyncClient

from app.core.security import create_access_token, hash_password
from app.db.models import (
    Enrollment,
    EnrollmentStatus,
    ReviewStatus,
    Student,
    StudentSubmission,
    SubmissionStatus,
    User,
    UserRole,
)

API = "/api/v1"
PASSWORD = "correct-horse-9"

RUBRIC = {
    "title": "Mechanics Midterm",
    "items": [
        {
            "question_number": "Q1",
            "max_marks": 4,
            "key_points": [
                "Newton's second law states force equals mass times acceleration",
                "Acceleration is proportional to net force",
            ],
        },
        {
            "question_number": "Q2",
            "max_marks": 6,
            "key_points": [
                "Kinetic energy equals half mass velocity squared",
                "Work done equals change in kinetic energy",
                "Final answer expressed in joules",
            ],
        },
    ],
}


def auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def make_user(session, email: str, role: UserRole, *, active: bool = True, name: str | None = None) -> User:
    user = User(
        email=email.lower(),
        hashed_password=hash_password(PASSWORD),
        full_name=name or email.split("@")[0].title(),
        role=role,
        is_active=active,
    )
    session.add(user)
    await session.commit()
    return user


def results_for(q1: float, q2: float, conf1: float = 0.8, conf2: float = 0.6) -> dict:
    def row(q, marks, mx, conf):
        return {
            "question": q, "marks_awarded": marks, "max_marks": mx, "justification": f"{q} AI remark",
            "confidence": conf, "is_blank": False, "ai_marks_awarded": marks,
            "criteria": [{"criterion": "crit", "kind": "key_point", "max_marks": mx, "awarded": marks,
                          "status": "met" if marks >= mx else "partial" if marks else "missed", "keyword_overlap": 0.5}],
        }
    return {"results": [row("Q1", q1, 4.0, conf1), row("Q2", q2, 6.0, conf2)], "total": q1 + q2, "max_total": 10.0}


async def seed_evaluated_submission(
    session, *, exam_id, course_id, rubric_id, student_id: str, q1: float = 3.0, q2: float = 4.0,
    conf1: float = 0.8, conf2: float = 0.6, name: str = "", file_path: str = "/nonexistent.pdf",
) -> uuid.UUID:
    """Insert an AI-evaluated submission directly (no OCR), enrolling the student."""
    student = Student(student_id=student_id, name=name or f"Student {student_id}")
    session.add(student)
    await session.flush()
    session.add(Enrollment(course_id=course_id, student_id=student.id, status=EnrollmentStatus.ACTIVE))
    data = results_for(q1, q2, conf1, conf2)
    sub = StudentSubmission(
        student_id=student_id, source_filename=f"{student_id}.pdf", file_path=file_path,
        rubric_id=rubric_id, course_id=course_id, exam_id=exam_id, student_record_id=student.id,
        status=SubmissionStatus.EVALUATED, review_status=ReviewStatus.AI_EVALUATED,
        evaluation_result=data, total_marks=data["total"], ai_total_marks=data["total"],
        min_confidence=min(conf1, conf2),
    )
    session.add(sub)
    await session.commit()
    return sub.id


def answer_pdf(lines: dict[str, str]) -> bytes:
    """A typed 'answer sheet': one block of text per question, top to bottom."""
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for q, text in lines.items():
        page.insert_textbox(fitz.Rect(50, y, 550, y + 330), f"{q}. {text}", fontsize=14)
        y += 360
    buf = io.BytesIO(doc.tobytes())
    doc.close()
    return buf.getvalue()


@dataclass
class World:
    """Two professors, two TAs and seeded exams — the standard security scenario."""

    prof_a: User
    prof_b: User
    ta_1: User  # on course A, assigned to exam A
    ta_2: User  # on course A, NOT assigned to exam A
    ta_b: User  # on course B, assigned to exam B
    course_a: dict
    course_b: dict
    exam_a: dict
    exam_b: dict
    subs_a: list[uuid.UUID] = field(default_factory=list)
    subs_b: list[uuid.UUID] = field(default_factory=list)

    @property
    def rubric_a(self) -> uuid.UUID:
        return uuid.UUID(self.exam_a["rubric"]["id"])


async def create_course(client: AsyncClient, prof: User, code: str, name: str = "Data Structures") -> dict:
    r = await client.post(f"{API}/courses", json={"name": name, "course_code": code, "semester": "Autumn", "academic_year": "2026-27"}, headers=auth(prof))
    assert r.status_code == 201, r.text
    return r.json()


async def create_exam(client: AsyncClient, prof: User, course_id: str, name: str = "Midsem") -> dict:
    r = await client.post(f"{API}/exams", json={"course_id": course_id, "name": name, "exam_type": "midterm", "total_marks": 10}, headers=auth(prof))
    assert r.status_code == 201, r.text
    exam = r.json()
    files = {"file": ("rubric.json", json.dumps(RUBRIC).encode(), "application/json")}
    r = await client.post(f"{API}/exams/{exam['id']}/rubric", files=files, headers=auth(prof))
    assert r.status_code == 200, r.text
    return r.json()


async def add_ta(client: AsyncClient, prof: User, course_id: str, ta: User, exam_id: str | None = None) -> None:
    r = await client.post(f"{API}/courses/{course_id}/tas", json={"email": ta.email}, headers=auth(prof))
    assert r.status_code == 201, r.text
    if exam_id:
        r = await client.post(f"{API}/exams/{exam_id}/tas", json={"ta_id": str(ta.id)}, headers=auth(prof))
        assert r.status_code == 200, r.text


async def mark_exam_in_review(session, exam_id: str) -> None:
    from app.db.models import Exam, ExamStatus

    exam = await session.get(Exam, uuid.UUID(exam_id))
    exam.status = ExamStatus.TA_REVIEW
    await session.commit()


async def build_world(client: AsyncClient, session) -> World:
    prof_a = await make_user(session, "sharma@uni.edu", UserRole.PROFESSOR, name="Dr. Sharma")
    prof_b = await make_user(session, "bose@uni.edu", UserRole.PROFESSOR, name="Dr. Bose")
    ta_1 = await make_user(session, "rahul@uni.edu", UserRole.TA, name="Rahul")
    ta_2 = await make_user(session, "ananya@uni.edu", UserRole.TA, name="Ananya")
    ta_b = await make_user(session, "arjun@uni.edu", UserRole.TA, name="Arjun")

    course_a = await create_course(client, prof_a, "CS3001")
    course_b = await create_course(client, prof_b, "MA2001", "Linear Algebra")
    exam_a = await create_exam(client, prof_a, course_a["id"])
    exam_b = await create_exam(client, prof_b, course_b["id"], "Quiz 1")
    await add_ta(client, prof_a, course_a["id"], ta_1, exam_a["id"])
    await add_ta(client, prof_a, course_a["id"], ta_2)
    await add_ta(client, prof_b, course_b["id"], ta_b, exam_b["id"])

    world = World(prof_a, prof_b, ta_1, ta_2, ta_b, course_a, course_b, exam_a, exam_b)
    for i, (q1, q2) in enumerate([(3.0, 4.0), (4.0, 6.0), (1.0, 2.0)]):
        world.subs_a.append(
            await seed_evaluated_submission(
                session, exam_id=uuid.UUID(exam_a["id"]), course_id=uuid.UUID(course_a["id"]),
                rubric_id=uuid.UUID(exam_a["rubric"]["id"]), student_id=f"2401220{i}", q1=q1, q2=q2,
                conf1=0.9 - i * 0.2, conf2=0.7,
            )
        )
    world.subs_b.append(
        await seed_evaluated_submission(
            session, exam_id=uuid.UUID(exam_b["id"]), course_id=uuid.UUID(course_b["id"]),
            rubric_id=uuid.UUID(exam_b["rubric"]["id"]), student_id="99000001",
        )
    )
    await mark_exam_in_review(session, exam_a["id"])
    await mark_exam_in_review(session, exam_b["id"])
    return world
