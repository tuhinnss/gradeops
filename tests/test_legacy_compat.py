"""Backward compatibility of the original single-upload workbench API."""

import json
import shutil

import pytest

from app.config import get_settings
from app.db.models import UserRole
from tests.helpers import API, RUBRIC, answer_pdf, auth, make_user

pytestmark = pytest.mark.db

ANSWER = {
    "Q1": "Newton's second law states force equals mass times acceleration. Acceleration is proportional to net force.",
    "Q2": "Kinetic energy equals half mass velocity squared.",
}


async def run_legacy_flow(client, headers: dict) -> dict:
    res = await client.post(
        f"{API}/upload/rubric",
        files={"file": ("rubric.json", json.dumps(RUBRIC).encode(), "application/json")},
        data={"name": "Midterm"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    rubric_id = res.json()["id"]
    assert res.json()["question_count"] == 2

    res = await client.post(
        f"{API}/upload/answer-sheet",
        files={"file": ("stu001.pdf", answer_pdf(ANSWER), "application/pdf")},
        data={"student_id": "STU001", "rubric_id": rubric_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    sid = res.json()["id"]

    res = await client.post(
        f"{API}/evaluate/run", json={"submission_id": sid, "rubric_id": rubric_id, "run_plagiarism_check": False},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    evaluation = res.json()
    # The documented evaluation response contract.
    assert {"submission_id", "student_id", "results", "total", "max_total", "plagiarism_flags", "annotated_pdf_url"} <= evaluation.keys()
    assert evaluation["max_total"] == 10.0
    assert {"question", "marks_awarded", "max_marks", "justification", "confidence", "is_blank"} <= evaluation["results"][0].keys()

    results = (await client.get(f"{API}/results/{sid}", headers=headers)).json()
    assert results["total"] == evaluation["total"]
    pdf = await client.get(f"{API}/results/{sid}/annotated-pdf", headers=headers)
    assert pdf.status_code == 200
    report = (await client.get(f"{API}/results/{sid}/generate-report", headers=headers)).json()
    assert report["logs"] and report["extracted_text"]["answers"]

    review = await client.post(f"{API}/review/{sid}/action", json={"action": "approve"}, headers=headers)
    assert review.status_code == 200, review.text
    analytics = (await client.get(f"{API}/analytics/rubric/{rubric_id}", headers=headers)).json()
    assert analytics["evaluated_count"] == 1 and analytics["review_approved"] == 1
    return {"rubric_id": rubric_id, "submission_id": sid, "review": review.json()}


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract OCR not installed")
async def test_legacy_flow_open_demo_mode(client, db_clean, monkeypatch):
    """AUTH_ENABLED=false keeps the original anonymous workbench working."""
    monkeypatch.setattr(get_settings(), "auth_enabled", False)
    out = await run_legacy_flow(client, {})
    assert out["review"]["review_status"] == "ta_approved"
    # Role dashboards still require a login even in demo mode.
    assert (await client.get(f"{API}/professor/dashboard")).status_code == 401
    me = (await client.get(f"{API}/auth/me")).json()
    assert me["auth_enabled"] is False


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract OCR not installed")
async def test_legacy_flow_authenticated_professor(client, session):
    prof = await make_user(session, "prof@uni.edu", UserRole.PROFESSOR)
    out = await run_legacy_flow(client, auth(prof))
    # Professor's own sign-off in the legacy panel is a professor approval.
    assert out["review"]["review_status"] == "professor_approved"
    # Unscoped legacy uploads belong to their uploader only.
    other = await make_user(session, "other@uni.edu", UserRole.PROFESSOR)
    assert (await client.get(f"{API}/results/{out['submission_id']}", headers=auth(other))).status_code == 404
    listing = (await client.get(f"{API}/analytics/submissions", headers=auth(other))).json()
    assert listing["total"] == 0
    ta = await make_user(session, "ta@uni.edu", UserRole.TA)
    assert (await client.get(f"{API}/results/{out['submission_id']}", headers=auth(ta))).status_code == 404


async def test_ta_cannot_use_legacy_upload(client, session):
    ta = await make_user(session, "ta@uni.edu", UserRole.TA)
    res = await client.post(
        f"{API}/upload/answer-sheet",
        files={"file": ("x.pdf", answer_pdf(ANSWER), "application/pdf")},
        data={"student_id": "S1"},
        headers=auth(ta),
    )
    assert res.status_code == 403
