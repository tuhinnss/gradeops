"""End-to-end: the full professor + TA workflow through the API and real pipeline.

Runs actual OCR (Tesseract) on generated answer sheets, the rubric-guided
segmenter, the evaluation engine and the similarity scan — then the human
review, finalisation and publication steps. Skipped when Tesseract is missing.
"""

import asyncio
import json
import shutil

import pytest

from app.db.models import UserRole
from tests.helpers import API, PASSWORD, RUBRIC, answer_pdf, make_user

pytestmark = [
    pytest.mark.db,
    pytest.mark.ocr,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract OCR not installed"),
]

GOOD = {
    "Q1": "Newton's second law states the net force equals mass times acceleration. "
    "The acceleration is proportional to the net force applied.",
    "Q2": "Kinetic energy equals half mass velocity squared. The work done equals the change "
    "in kinetic energy, so the final answer is 45 joules.",
}
WEAK = {
    "Q1": "Objects keep moving unless something stops them.",
    "Q2": "Energy is conserved in the system and nothing else happens here.",
}


async def login(client, email: str, password: str) -> dict:
    res = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def wait_for_job(client, headers, job_id: str, timeout: float = 180) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        job = (await client.get(f"{API}/bulk/jobs/{job_id}", headers=headers)).json()
        if job["status"] in ("completed", "failed"):
            return job
        assert asyncio.get_running_loop().time() < deadline, f"job still {job['status']}"
        await asyncio.sleep(0.5)


async def test_professor_and_ta_end_to_end(client, session):
    # 1. Professor account is provisioned (not self-registered); logs in.
    await make_user(session, "sharma@uni.edu", UserRole.PROFESSOR, name="Dr. Sharma")
    prof = await login(client, "sharma@uni.edu", PASSWORD)
    me = (await client.get(f"{API}/auth/me", headers=prof)).json()
    assert me["role"] == "professor"

    # 2. Course + roster.
    course = (await client.post(
        f"{API}/courses",
        json={"name": "Engineering Mechanics", "course_code": "ME1001", "semester": "Autumn", "academic_year": "2026-27"},
        headers=prof,
    )).json()
    roster = [{"student_id": sid, "name": name} for sid, name in (("240122065", "Asha Rao"), ("240122066", "Bilal Khan"), ("240122067", "Chen Li"))]
    res = await client.post(f"{API}/courses/{course['id']}/students", json={"students": roster}, headers=prof)
    assert res.json()["enrolled"] == 3

    # 3. TA account created by the professor, added to the course.
    res = await client.post(
        f"{API}/courses/{course['id']}/tas",
        json={"email": "rahul@uni.edu", "full_name": "Rahul Sharma", "password": "ta-password-1"},
        headers=prof,
    )
    assert res.status_code == 201
    ta_id = res.json()["user"]["id"]
    ta = await login(client, "rahul@uni.edu", "ta-password-1")

    # 4. Exam, rubric, TA assignment.
    exam = (await client.post(
        f"{API}/exams",
        json={"course_id": course["id"], "name": "Mid Semester Examination", "exam_type": "midterm", "total_marks": 10, "exam_date": "2026-09-20"},
        headers=prof,
    )).json()
    res = await client.post(
        f"{API}/exams/{exam['id']}/rubric",
        files={"file": ("midsem_rubric.json", json.dumps(RUBRIC).encode(), "application/json")},
        headers=prof,
    )
    assert res.json()["rubric"]["question_count"] == 2
    res = await client.post(f"{API}/exams/{exam['id']}/tas", json={"ta_id": ta_id}, headers=prof)
    assert res.status_code == 200
    # Before evaluation the TA sees the exam but nothing to review.
    assert (await client.get(f"{API}/ta/reviews", headers=ta)).json()["total"] == 0

    # 5. Upload answer sheets (mapping validated against the roster).
    files = [
        ("files", ("240122065_midsem.pdf", answer_pdf(GOOD), "application/pdf")),
        ("files", ("240122066_midsem.pdf", answer_pdf(WEAK), "application/pdf")),
        ("files", ("240122067_midsem.pdf", answer_pdf(GOOD), "application/pdf")),  # copy of the first
    ]
    check = await client.post(
        f"{API}/exams/{exam['id']}/submissions/validate",
        json={"items": [{"filename": f[1][0]} for f in files]},
        headers=prof,
    )
    assert check.json()["problems"] == 0
    res = await client.post(f"{API}/exams/{exam['id']}/submissions", files=files, headers=prof)
    assert len(res.json()["uploaded"]) == 3, res.text

    # 6. Run the AI pipeline as a batch job and monitor it.
    res = await client.post(f"{API}/exams/{exam['id']}/evaluate", json={"run_plagiarism_check": True}, headers=prof)
    assert res.status_code == 200, res.text
    job = await wait_for_job(client, prof, res.json()["id"])
    assert job["status"] == "completed" and job["completed_count"] == 3, job
    detail = (await client.get(f"{API}/exams/{exam['id']}", headers=prof)).json()
    assert detail["status"] == "ta_review"
    assert detail["counts"]["processed"] == 3 and detail["counts"]["awaiting_ta"] == 3
    assert [a["action"] for a in detail["audit"]][:2] == ["processing_finished", "processing_started"]

    gb = (await client.get(f"{API}/exams/{exam['id']}/gradebook", headers=prof)).json()
    scores = {r["student_id"]: r["ai_score"] for r in gb["rows"]}
    # Evidence-based scoring: the rubric-matching answer outscores the weak one.
    assert scores["240122065"] > scores["240122066"]
    assert scores["240122066"] <= 3

    # Similarity scan flagged the identical pair (for professor review, not a verdict).
    flags = (await client.get(f"{API}/exams/{exam['id']}/integrity", headers=prof)).json()
    pairs = {frozenset((f["a"]["student_id"], f["b"]["student_id"])) for f in flags}
    assert frozenset(("240122065", "240122067")) in pairs
    assert all(f["status"] == "open" for f in flags)

    # 7. TA works the queue: open item, see OCR + rubric + AI evidence + original image.
    queue = (await client.get(f"{API}/ta/reviews", headers=ta)).json()
    assert queue["total"] == 3
    by_student = {i["student_id"]: i["submission_id"] for i in queue["items"]}
    item = (await client.get(f"{API}/ta/reviews/{by_student['240122065']}", headers=ta)).json()
    q1 = item["questions"][0]
    assert "newton" in q1["answer"]["text"].lower()  # OCR text of the handwritten region
    assert q1["rubric"]["key_points"] and q1["criteria"]
    assert item["permissions"]["can_approve"]
    img = await client.get(f"{API}/review/{by_student['240122065']}/answer-image", params={"question": "Q1"}, headers=ta)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.headers["x-cropped"] == "1"

    # TA approves one, overrides one, escalates another.
    res = await client.post(f"{API}/review/{by_student['240122065']}/action", json={"action": "approve"}, headers=ta)
    assert res.json()["review_status"] == "ta_approved"
    weak = (await client.get(f"{API}/ta/reviews/{by_student['240122066']}", headers=ta)).json()
    q2_ai = weak["questions"][1]["marks_awarded"]
    res = await client.post(
        f"{API}/review/{by_student['240122066']}/action",
        json={"action": "override", "reason": "Conservation argument earns partial credit",
              "overrides": [{"question": "Q2", "marks_awarded": min(q2_ai + 1, 6)}]},
        headers=ta,
    )
    assert res.json()["review_status"] == "ta_overridden"
    res = await client.post(
        f"{API}/review/{by_student['240122067']}/action",
        json={"action": "escalate", "reason": "integrity_concern", "notes": "Identical to 240122065"},
        headers=ta,
    )
    assert res.json()["review_status"] == "escalated"

    # Publishing is impossible while an escalation is open.
    s = (await client.get(f"{API}/exams/{exam['id']}/publish-summary", headers=prof)).json()
    assert not s["can_approve"] and s["escalated"] == 1

    # 8. Professor resolves the escalation and the similarity flag.
    escalations = (await client.get(f"{API}/professor/escalations", headers=prof)).json()
    assert escalations[0]["escalated_by"]["email"] == "rahul@uni.edu"
    res = await client.post(
        f"{API}/review/{by_student['240122067']}/action",
        json={"action": "resolve", "notes": "Discussed with student; answers written independently in exam hall"},
        headers=prof,
    )
    assert res.json()["review_status"] == "professor_approved"
    for f in flags:
        res = await client.patch(
            f"{API}/professor/integrity/{f['id']}", json={"status": "dismissed", "notes": "Standard derivation"}, headers=prof
        )
        assert res.status_code == 200

    # 9. Finalise: approve → lock → publish.
    s = (await client.get(f"{API}/exams/{exam['id']}/publish-summary", headers=prof)).json()
    assert s["can_approve"] and s["ta_overrides"] == 1 and s["integrity_open"] == 0
    assert (await client.post(f"{API}/exams/{exam['id']}/approve", json={}, headers=prof)).json()["status"] == "approved"
    assert (await client.post(f"{API}/exams/{exam['id']}/lock", json={}, headers=prof)).json()["status"] == "locked"
    published = (await client.post(f"{API}/exams/{exam['id']}/publish", json={}, headers=prof)).json()
    assert published["status"] == "published" and published["counts"]["published"] == 3

    final = (await client.get(f"{API}/exams/{exam['id']}/gradebook", headers=prof)).json()
    assert final["is_final"] and all(r["status_label"] == "Published" for r in final["rows"])
    csv_res = await client.get(f"{API}/exams/{exam['id']}/gradebook.csv?final=true", headers=prof)
    assert csv_res.status_code == 200 and "240122066" in csv_res.text

    # Annotated sheet now carries the final (overridden) marks.
    import fitz

    pdf = await client.get(f"{API}/results/{by_student['240122066']}/annotated-pdf", headers=prof)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    with fitz.open(stream=pdf.content, filetype="pdf") as doc:
        text = "".join(page.get_text() for page in doc)
    final_total = next(r["final_score"] for r in final["rows"] if r["student_id"] == "240122066")
    assert f"Total: {final_total:.1f}/10.0" in text

    # 10. Audit trail is complete and persisted.
    history = (await client.get(f"{API}/ta/history", headers=ta)).json()
    assert [i["action"] for i in history["items"]] == ["escalate", "override", "approve"]
    trail = (await client.get(f"{API}/review/{by_student['240122066']}", headers=prof)).json()["audit_history"]
    assert [a["action"] for a in trail] == ["publish", "professor_approve_exam", "override"]
    # Legacy results endpoint still serves the evaluation contract.
    legacy = (await client.get(f"{API}/results/{by_student['240122065']}/json", headers=prof)).json()
    assert {"submission_id", "student_id", "results", "total", "max_total"} <= legacy.keys()
