"""Gradebook aggregation, professor finalisation and publication rules."""

import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.db.models import IntegrityFlag, IntegrityFlagStatus, Student
from tests.helpers import API, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
async def world(client, session):
    return await build_world(client, session)


async def act(client, user, sid, **body):
    res = await client.post(f"{API}/review/{sid}/action", json=body, headers=auth(user))
    assert res.status_code == 200, res.text
    return res.json()


async def summary(client, world):
    res = await client.get(f"{API}/exams/{world.exam_a['id']}/publish-summary", headers=auth(world.prof_a))
    return res.json()


async def test_cannot_approve_or_publish_with_pending_human_review(client, world):
    eid = world.exam_a["id"]
    s = await summary(client, world)
    assert s["awaiting_ta"] == 3 and s["can_approve"] is False
    assert any("awaiting human review" in b for b in s["blockers"])
    res = await client.post(f"{API}/exams/{eid}/approve", json={}, headers=auth(world.prof_a))
    assert res.status_code == 409
    res = await client.post(f"{API}/exams/{eid}/publish", json={"acknowledge_integrity_flags": True}, headers=auth(world.prof_a))
    assert res.status_code == 409  # AI grades can never go straight to published


async def test_escalation_blocks_approval_until_resolved(client, world):
    await act(client, world.ta_1, world.subs_a[0], action="approve")
    await act(client, world.ta_1, world.subs_a[1], action="approve")
    await act(client, world.ta_1, world.subs_a[2], action="escalate", reason="rubric_unclear")
    s = await summary(client, world)
    assert s["escalated"] == 1 and not s["can_approve"]
    await act(client, world.prof_a, world.subs_a[2], action="resolve", notes="Rubric clarified")
    s = await summary(client, world)
    assert s["can_approve"] and s["blockers"] == []


async def full_review(client, world):
    await act(client, world.ta_1, world.subs_a[0], action="approve")
    await act(
        client, world.ta_1, world.subs_a[1], action="override", reason="Q1 method wrong",
        overrides=[{"question": "Q1", "marks_awarded": 2}],
    )
    await act(client, world.ta_1, world.subs_a[2], action="escalate", reason="ocr_unreliable")
    await act(
        client, world.prof_a, world.subs_a[2], action="resolve", reason="Rescanned",
        overrides=[{"question": "Q2", "marks_awarded": 3}],
    )


async def test_full_finalisation_lifecycle(client, session, world):
    eid, prof = world.exam_a["id"], world.prof_a
    await full_review(client, world)

    s = await summary(client, world)
    assert (s["total"], s["ta_reviewed"], s["professor_approved"]) == (3, 2, 1)
    assert s["ta_overrides"] == 1 and s["professor_overrides"] == 1

    # Approve: TA-reviewed become professor-approved in bulk.
    res = await client.post(f"{API}/exams/{eid}/approve", json={"notes": "Checked"}, headers=auth(prof))
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    # TA can no longer change anything once the professor approved.
    res = await client.post(f"{API}/review/{world.subs_a[0]}/action", json={"action": "approve"}, headers=auth(world.ta_1))
    assert res.status_code == 409

    # Lock then publish, with an unresolved similarity flag that must be acknowledged.
    session.add(IntegrityFlag(
        exam_id=uuid.UUID(eid), question="Q1", submission_a_id=world.subs_a[0], submission_b_id=world.subs_a[1],
        student_a="24012200", student_b="24012201", similarity=0.97, status=IntegrityFlagStatus.OPEN,
    ))
    await session.commit()
    res = await client.post(f"{API}/exams/{eid}/lock", json={}, headers=auth(prof))
    assert res.json()["status"] == "locked"
    res = await client.post(f"{API}/exams/{eid}/publish", json={}, headers=auth(prof))
    assert res.status_code == 409 and "similarity" in res.json()["detail"]
    res = await client.post(f"{API}/exams/{eid}/publish", json={"acknowledge_integrity_flags": True}, headers=auth(prof))
    assert res.status_code == 200 and res.json()["status"] == "published"
    assert res.json()["counts"]["published"] == 3

    # Frozen: no review actions, no re-evaluation, no uploads.
    res = await client.post(f"{API}/review/{world.subs_a[0]}/action", json={"action": "approve"}, headers=auth(prof))
    assert res.status_code == 409
    res = await client.post(f"{API}/exams/{eid}/evaluate", json={"reevaluate": True}, headers=auth(prof))
    assert res.status_code == 409

    # Reopen requires a reason; submissions go back to professor-approved.
    assert (await client.post(f"{API}/exams/{eid}/reopen", json={"reason": ""}, headers=auth(prof))).status_code == 422
    res = await client.post(f"{API}/exams/{eid}/reopen", json={"reason": "Regrade request for Q2"}, headers=auth(prof))
    assert res.status_code == 200 and res.json()["status"] == "ta_review"
    assert res.json()["counts"]["professor_approved"] == 3
    actions = [a["action"] for a in res.json()["audit"]]
    assert actions[:4] == ["reopen", "publish", "lock", "approve"]
    # The professor can now amend a grade again.
    res = await client.post(
        f"{API}/review/{world.subs_a[0]}/action",
        json={"action": "override", "reason": "Regrade", "overrides": [{"question": "Q2", "marks_awarded": 6}]},
        headers=auth(prof),
    )
    assert res.status_code == 200 and res.json()["review_status"] == "professor_approved"


async def test_gradebook_aggregation(client, session, world):
    # An enrolled student with no submission shows up as missing.
    from app.db.models import Enrollment, EnrollmentStatus

    st = Student(student_id="24019999", name="No Show")
    session.add(st)
    await session.flush()
    session.add(Enrollment(course_id=uuid.UUID(world.course_a["id"]), student_id=st.id, status=EnrollmentStatus.ACTIVE))
    await session.commit()

    await full_review(client, world)
    gb = (await client.get(f"{API}/exams/{world.exam_a['id']}/gradebook", headers=auth(world.prof_a))).json()
    assert gb["questions"] == ["Q1", "Q2"] and gb["max_score"] == 10 and gb["is_final"] is False
    rows = {r["student_id"]: r for r in gb["rows"]}
    approved = rows["24012200"]
    assert (approved["ai_score"], approved["ta_score"], approved["final_score"]) == (7.0, 7.0, 7.0)
    assert approved["status_label"] == "TA approved" and approved["reviewed_by"] == "Rahul"
    overridden = rows["24012201"]
    assert (overridden["ai_score"], overridden["ta_score"], overridden["final_score"]) == (10.0, 8.0, 8.0)
    assert overridden["overridden"] is True and overridden["question_scores"] == {"Q1": 2.0, "Q2": 6.0}
    escalated = rows["24012202"]
    assert (escalated["ai_score"], escalated["professor_score"], escalated["final_score"]) == (3.0, 4.0, 4.0)
    assert escalated["percentage"] == 40.0 and escalated["approved_by"] == "Dr. Sharma"
    assert rows["24019999"]["status_label"] == "No submission"

    analytics = (await client.get(f"{API}/exams/{world.exam_a['id']}/analytics", headers=auth(world.prof_a))).json()
    assert analytics["summary"]["count"] == 3
    assert analytics["summary"]["average"] == round((7 + 8 + 4) / 3, 2)
    assert analytics["summary"]["median"] == 7.0
    q1 = next(q for q in analytics["questions"] if q["question"] == "Q1")
    assert q1["attempts"] == 3 and q1["overridden"] == 1
    assert analytics["review"]["ta_override_rate"] == 33.3  # 1 of 3 TA-touched submissions
    assert analytics["review"]["ai_ta_disagreement_rate"] == 50.0  # sub1: 10→8; sub0 unchanged
    assert len(analytics["students"]) == 3


async def test_csv_export_provisional_and_final(client, session, world):
    eid = world.exam_a["id"]
    # Formula-injection guard for user-controlled text.
    st = await session.scalar(select(Student).where(Student.student_id == "24012200"))
    st.name = "=HYPERLINK(\"http://evil\")"
    await session.commit()

    res = await client.get(f"{API}/exams/{eid}/gradebook.csv", headers=auth(world.prof_a))
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows[0][:3] == ["grade_status", "student_id", "student_name"]
    assert rows[1][0] == "PROVISIONAL"
    assert rows[1][2].startswith("'=")
    # Final export only after approval.
    assert (await client.get(f"{API}/exams/{eid}/gradebook.csv?final=true", headers=auth(world.prof_a))).status_code == 409
    await full_review(client, world)
    await client.post(f"{API}/exams/{eid}/approve", json={}, headers=auth(world.prof_a))
    res = await client.get(f"{API}/exams/{eid}/gradebook.csv?final=true", headers=auth(world.prof_a))
    assert res.status_code == 200
    assert "final.csv" in res.headers["content-disposition"]


async def test_integrity_flag_resolution_requires_note(client, session, world):
    flag = IntegrityFlag(
        exam_id=uuid.UUID(world.exam_a["id"]), question="Q2", submission_a_id=world.subs_a[0],
        submission_b_id=world.subs_a[1], student_a="24012200", student_b="24012201", similarity=0.95,
        note="Similarity flag", evidence={"excerpt_a": "text a", "excerpt_b": "text b"},
    )
    session.add(flag)
    await session.commit()
    h = auth(world.prof_a)
    flags = (await client.get(f"{API}/professor/integrity", headers=h)).json()
    assert len(flags) == 1 and flags[0]["a"]["excerpt"] == "text a" and flags[0]["status"] == "open"
    res = await client.patch(f"{API}/professor/integrity/{flag.id}", json={"status": "dismissed"}, headers=h)
    assert res.status_code == 400
    res = await client.patch(
        f"{API}/professor/integrity/{flag.id}", json={"status": "dismissed", "notes": "Common textbook derivation"}, headers=h
    )
    assert res.status_code == 200 and res.json()["resolved_by"]["email"] == world.prof_a.email
    # TA sees the flag on the review screen but cannot resolve it.
    detail = (await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=auth(world.ta_1))).json()
    assert detail["integrity_flags"][0]["other_student_id"] == "24012201"
    res = await client.patch(
        f"{API}/professor/integrity/{flag.id}", json={"status": "confirmed", "notes": "x"}, headers=auth(world.ta_1)
    )
    assert res.status_code == 403
    # Professor B cannot see or change it.
    assert (await client.get(f"{API}/professor/integrity", headers=auth(world.prof_b))).json() == []
    res = await client.patch(
        f"{API}/professor/integrity/{flag.id}", json={"status": "confirmed", "notes": "x"}, headers=auth(world.prof_b)
    )
    assert res.status_code == 404


async def test_professor_dashboard_counts_are_real(client, world):
    await act(client, world.ta_1, world.subs_a[0], action="approve")
    await act(client, world.ta_1, world.subs_a[1], action="escalate", reason="ambiguous_answer")
    dash = (await client.get(f"{API}/professor/dashboard", headers=auth(world.prof_a))).json()
    assert dash["active_courses"] == 1 and dash["active_exams"] == 1
    assert dash["students"] == 3 and dash["submissions"] == 3
    assert dash["pending_ta_reviews"] == 1 and dash["awaiting_professor_approval"] == 1
    assert dash["escalated"] == 1 and dash["ready_to_publish"] == 0
    actions = [a["action"] for a in dash["recent_activity"]]
    assert "escalate" in actions and "approve" in actions
    exam = dash["exams"][0]
    assert exam["counts"]["awaiting_ta"] == 1 and exam["counts"]["escalated"] == 1
    assert exam["stage"] == "ta_review"
