"""Courses, rosters, TA management, exams, submission upload & mapping."""

import json

import pytest

from app.db.models import BatchJobStatus, UserRole
from tests.helpers import API, RUBRIC, add_ta, answer_pdf, auth, create_course, create_exam, make_user

pytestmark = pytest.mark.db


@pytest.fixture
async def prof(session):
    return await make_user(session, "prof@uni.edu", UserRole.PROFESSOR, name="Dr. Sharma")


async def test_course_create_edit_archive(client, prof):
    course = await create_course(client, prof, " cs3001 ")
    assert course["course_code"] == "CS3001"
    assert course["professor"]["email"] == prof.email
    assert course["stats"]["student_count"] == 0

    dup = await client.post(
        f"{API}/courses", json={"name": "Again", "course_code": "CS3001", "semester": "Autumn", "academic_year": "2026-27"},
        headers=auth(prof),
    )
    assert dup.status_code == 409

    res = await client.patch(f"{API}/courses/{course['id']}", json={"name": "Advanced DS", "description": "Trees"}, headers=auth(prof))
    assert res.status_code == 200 and res.json()["name"] == "Advanced DS"

    res = await client.delete(f"{API}/courses/{course['id']}", headers=auth(prof))
    assert res.status_code == 200 and res.json()["status"] == "archived"
    active = (await client.get(f"{API}/courses", headers=auth(prof))).json()
    assert active == []
    archived = (await client.get(f"{API}/courses", params={"status": "archived"}, headers=auth(prof))).json()
    assert [c["id"] for c in archived] == [course["id"]]
    # Archived: no new exams or staff until unarchived.
    res = await client.post(f"{API}/exams", json={"course_id": course["id"], "name": "X"}, headers=auth(prof))
    assert res.status_code == 409
    res = await client.patch(f"{API}/courses/{course['id']}", json={"status": "active"}, headers=auth(prof))
    assert res.json()["status"] == "active"


async def test_student_roster_json_and_csv(client, prof):
    course = await create_course(client, prof, "CS3001")
    res = await client.post(
        f"{API}/courses/{course['id']}/students",
        json={"students": [{"student_id": "240122065", "name": "Asha"}, {"student_id": "240122066", "name": "Bilal"}]},
        headers=auth(prof),
    )
    assert res.json() == {"created": 2, "enrolled": 2, "already_enrolled": 0, "reactivated": 0, "errors": []}
    csv_body = "student_id,name,email\n240122066,Bilal,\n240122067,Chen,chen@uni.edu\nbad id!,X,\n"
    res = await client.post(
        f"{API}/courses/{course['id']}/students/import-csv",
        files={"file": ("roster.csv", csv_body.encode(), "text/csv")},
        headers=auth(prof),
    )
    body = res.json()
    assert body["created"] == 1 and body["already_enrolled"] == 1 and len(body["errors"]) == 1
    students = (await client.get(f"{API}/courses/{course['id']}/students", headers=auth(prof))).json()
    assert [s["student_id"] for s in students] == ["240122065", "240122066", "240122067"]
    # Drop, then the course stats reflect the active roster.
    await client.delete(f"{API}/courses/{course['id']}/students/{students[0]['id']}", headers=auth(prof))
    course = (await client.get(f"{API}/courses/{course['id']}", headers=auth(prof))).json()
    assert course["stats"]["student_count"] == 2


async def test_ta_add_create_remove(client, session, prof):
    course = await create_course(client, prof, "CS3001")
    ta = await make_user(session, "rahul@uni.edu", UserRole.TA, name="Rahul")
    other_prof = await make_user(session, "other@uni.edu", UserRole.PROFESSOR)
    res = await client.post(f"{API}/courses/{course['id']}/tas", json={"email": ta.email}, headers=auth(prof))
    assert res.status_code == 201 and res.json()["user"]["email"] == ta.email
    again = await client.post(f"{API}/courses/{course['id']}/tas", json={"email": ta.email}, headers=auth(prof))
    assert again.status_code == 409
    not_ta = await client.post(f"{API}/courses/{course['id']}/tas", json={"email": other_prof.email}, headers=auth(prof))
    assert not_ta.status_code == 400
    missing = await client.post(f"{API}/courses/{course['id']}/tas", json={"email": "new@uni.edu"}, headers=auth(prof))
    assert missing.status_code == 404
    created = await client.post(
        f"{API}/courses/{course['id']}/tas",
        json={"email": "new@uni.edu", "full_name": "New TA", "password": "a-strong-pass"},
        headers=auth(prof),
    )
    assert created.status_code == 201
    login = await client.post(f"{API}/auth/login", json={"email": "new@uni.edu", "password": "a-strong-pass"})
    assert login.json()["user"]["role"] == "ta"

    tas = (await client.get(f"{API}/courses/{course['id']}/tas", headers=auth(prof))).json()
    assert {t["user"]["email"] for t in tas} == {ta.email, "new@uni.edu"}
    res = await client.delete(f"{API}/courses/{course['id']}/tas/{ta.id}", headers=auth(prof))
    assert res.status_code == 204
    tas = (await client.get(f"{API}/courses/{course['id']}/tas", headers=auth(prof))).json()
    assert next(t for t in tas if t["user"]["email"] == ta.email)["active"] is False


async def test_exam_creation_rubric_and_ta_assignment(client, session, prof):
    course = await create_course(client, prof, "CS3001")
    exam = await create_exam(client, prof, course["id"])
    assert exam["status"] == "draft" and exam["stage"] == "setup"
    assert exam["rubric"]["question_count"] == 2 and exam["rubric"]["total_marks"] == 10
    assert [a["action"] for a in exam["audit"]][:2] == ["rubric_uploaded", "created"]
    activity = (await client.get(f"{API}/courses/{course['id']}/activity", headers=auth(prof))).json()
    assert {a["action"] for a in activity} >= {"created", "rubric_uploaded"}

    ta = await make_user(session, "rahul@uni.edu", UserRole.TA)
    # Must be course staff before exam assignment.
    res = await client.post(f"{API}/exams/{exam['id']}/tas", json={"ta_id": str(ta.id)}, headers=auth(prof))
    assert res.status_code == 400
    await add_ta(client, prof, course["id"], ta, exam["id"])
    exam = (await client.get(f"{API}/exams/{exam['id']}", headers=auth(prof))).json()
    assert [t["email"] for t in exam["tas"]] == [ta.email]

    rubric = (await client.get(f"{API}/exams/{exam['id']}/rubric", headers=auth(ta))).json()
    assert rubric["structured_data"]["items"][0]["question_number"] == "Q1"
    # Rubric library + edit by owner.
    lib = (await client.get(f"{API}/rubrics", headers=auth(prof))).json()
    assert lib[0]["used_by_exams"][0]["id"] == exam["id"]
    edited = dict(RUBRIC, items=[dict(RUBRIC["items"][0], max_marks=5), RUBRIC["items"][1]])
    res = await client.put(f"{API}/rubrics/{lib[0]['id']}", json={"structured_data": edited}, headers=auth(prof))
    assert res.status_code == 200 and res.json()["total_marks"] == 11


async def test_submission_mapping_validation_and_upload(client, prof):
    course = await create_course(client, prof, "CS3001")
    await client.post(
        f"{API}/courses/{course['id']}/students",
        json={"students": [{"student_id": "240122065", "name": "Asha"}, {"student_id": "240122066", "name": "Bilal"}]},
        headers=auth(prof),
    )
    exam = await create_exam(client, prof, course["id"])
    check = await client.post(
        f"{API}/exams/{exam['id']}/submissions/validate",
        json={"items": [
            {"filename": "midsem_240122065.pdf"},
            {"filename": "scan-3.pdf", "student_id": "240122066"},
            {"filename": "999.pdf"},
            {"filename": "notes.txt"},
            {"filename": "again_240122065.pdf"},
        ]},
        headers=auth(prof),
    )
    statuses = [i["status"] for i in check.json()["items"]]
    assert statuses == ["ok", "ok", "not_enrolled", "invalid", "duplicate_in_upload"]
    assert check.json()["items"][0]["student_name"] == "Asha"

    pdf = answer_pdf({"Q1": "Force equals mass times acceleration"})
    res = await client.post(
        f"{API}/exams/{exam['id']}/submissions",
        files=[
            ("files", ("midsem_240122065.pdf", pdf, "application/pdf")),
            ("files", ("unknown_777.pdf", pdf, "application/pdf")),
            ("files", ("fake_240122066.pdf", b"not a pdf at all", "application/pdf")),
        ],
        headers=auth(prof),
    )
    body = res.json()
    assert [u["student_id"] for u in body["uploaded"]] == ["240122065"]
    assert {f["filename"] for f in body["failed"]} == {"unknown_777.pdf", "fake_240122066.pdf"}

    # Duplicate for same student is rejected; auto_enroll adds unknown students.
    res = await client.post(
        f"{API}/exams/{exam['id']}/submissions",
        data={"student_ids": json.dumps(["240122065", "777"]), "auto_enroll": "true"},
        files=[("files", ("a.pdf", pdf, "application/pdf")), ("files", ("b.pdf", pdf, "application/pdf"))],
        headers=auth(prof),
    )
    body = res.json()
    assert [u["student_id"] for u in body["uploaded"]] == ["777"]
    assert body["failed"][0]["student_id"] == "240122065"
    assert any("777" in w for w in body["warnings"])

    subs = (await client.get(f"{API}/exams/{exam['id']}/submissions", headers=auth(prof))).json()
    assert subs["total"] == 2
    assert all(s["status"] == "uploaded" and s["review_status"] == "not_evaluated" for s in subs["items"])
    # Unreviewed uploads can be deleted by the professor.
    res = await client.delete(f"{API}/exams/{exam['id']}/submissions/{subs['items'][0]['id']}", headers=auth(prof))
    assert res.status_code == 204


async def test_evaluate_requires_rubric_and_submissions(client, prof):
    course = await create_course(client, prof, "CS3001")
    res = await client.post(f"{API}/exams", json={"course_id": course["id"], "name": "No rubric"}, headers=auth(prof))
    exam = res.json()
    res = await client.post(f"{API}/exams/{exam['id']}/evaluate", json={}, headers=auth(prof))
    assert res.status_code == 400 and "rubric" in res.json()["detail"].lower()
    exam = await create_exam(client, prof, course["id"], "With rubric")
    res = await client.post(f"{API}/exams/{exam['id']}/evaluate", json={}, headers=auth(prof))
    assert res.status_code == 400 and "no submissions" in res.json()["detail"].lower()


async def test_interrupted_job_releases_exam(client, session, prof):
    """A job that died with the API process must not leave the exam in PROCESSING."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select, update

    from app.db import crud
    from app.db.models import BatchJob, Exam, ExamStatus, StudentSubmission, SubmissionStatus
    from tests.helpers import seed_evaluated_submission

    course = await create_course(client, prof, "CS3001")
    exam = await create_exam(client, prof, course["id"])
    exam_id, rubric_id = uuid.UUID(exam["id"]), uuid.UUID(exam["rubric"]["id"])
    await seed_evaluated_submission(
        session, exam_id=exam_id, course_id=uuid.UUID(course["id"]), rubric_id=rubric_id, student_id="24012201"
    )
    stuck = StudentSubmission(
        student_id="24012202", source_filename="24012202.pdf", file_path="/nonexistent.pdf",
        rubric_id=rubric_id, course_id=uuid.UUID(course["id"]), exam_id=exam_id,
        status=SubmissionStatus.PROCESSING,
    )
    session.add(stuck)
    await session.flush()
    job = await crud.create_batch_job(session, rubric_id=rubric_id, submission_ids=[str(stuck.id)], exam_id=exam_id)
    job.status = BatchJobStatus.RUNNING
    (await session.get(Exam, exam_id)).status = ExamStatus.PROCESSING
    await session.commit()

    # Recent progress: treated as still running.
    res = await client.get(f"{API}/exams/{exam_id}", headers=auth(prof))
    assert res.json()["status"] == "processing"
    res = await client.post(f"{API}/exams/{exam_id}/evaluate", json={}, headers=auth(prof))
    assert res.status_code == 409

    # No progress for longer than the stale window: released on the next read.
    await session.execute(
        update(BatchJob).where(BatchJob.id == job.id).values(updated_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await session.commit()
    res = await client.get(f"{API}/bulk/jobs/{job.id}", headers=auth(prof))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "failed"
    assert "interrupted" in body["errors"][-1]["error"].lower()
    res = await client.get(f"{API}/exams/{exam_id}", headers=auth(prof))
    assert res.json()["status"] == "ta_review"
    sub = (
        await session.execute(
            select(StudentSubmission).where(StudentSubmission.id == stuck.id).execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert sub.status == SubmissionStatus.FAILED


async def test_distribute_round_robin(client, session, prof):
    from tests.helpers import mark_exam_in_review, seed_evaluated_submission
    import uuid

    course = await create_course(client, prof, "CS3001")
    exam = await create_exam(client, prof, course["id"])
    ta1 = await make_user(session, "t1@uni.edu", UserRole.TA)
    ta2 = await make_user(session, "t2@uni.edu", UserRole.TA)
    await add_ta(client, prof, course["id"], ta1, exam["id"])
    await add_ta(client, prof, course["id"], ta2, exam["id"])
    for i in range(5):
        await seed_evaluated_submission(
            session, exam_id=uuid.UUID(exam["id"]), course_id=uuid.UUID(course["id"]),
            rubric_id=uuid.UUID(exam["rubric"]["id"]), student_id=f"S{i}",
        )
    await mark_exam_in_review(session, exam["id"])
    res = await client.post(f"{API}/exams/{exam['id']}/distribute", json={}, headers=auth(prof))
    assert res.json()["total"] == 5
    assert sorted(res.json()["assigned"].values()) == [2, 3]
    q1 = (await client.get(f"{API}/ta/reviews", headers=auth(ta1))).json()["total"]
    q2 = (await client.get(f"{API}/ta/reviews", headers=auth(ta2))).json()["total"]
    assert q1 + q2 == 5 and {q1, q2} == {2, 3}
    workload = (await client.get(f"{API}/courses/{course['id']}/tas", headers=auth(prof))).json()
    assert sorted(w["pending"] for w in workload) == [2, 3]
