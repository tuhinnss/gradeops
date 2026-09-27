"""Review lifecycle: approve / override / escalate / resolve / return, with audit."""

import pytest

from tests.helpers import API, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
async def world(client, session):
    return await build_world(client, session)


async def act(client, user, sid, **body):
    return await client.post(f"{API}/review/{sid}/action", json=body, headers=auth(user))


async def detail(client, user, sid):
    res = await client.get(f"{API}/review/{sid}/detail", headers=auth(user))
    assert res.status_code == 200, res.text
    return res.json()


async def test_ta_approve(client, world):
    sid = world.subs_a[0]
    res = await act(client, world.ta_1, sid, action="approve", notes="Looks right")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["review_status"] == "ta_approved"
    assert body["ta_total"] == body["total"] == 7.0
    audit = body["audit_history"][0]
    assert audit["action"] == "approve"
    assert audit["from_status"] == "ai_evaluated" and audit["to_status"] == "ta_approved"
    assert audit["reviewer"]["email"] == world.ta_1.email
    assert audit["actor_role"] == "ta"


async def test_ta_override_records_old_and_new_marks(client, world):
    sid = world.subs_a[0]
    res = await act(
        client, world.ta_1, sid, action="override", reason="Units were correct",
        notes="Checked handwriting", overrides=[{"question": "q2", "marks_awarded": 5.5, "justification": "Full working shown"}],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["review_status"] == "ta_overridden"
    assert body["total"] == 8.5
    assert body["ai_total"] == 7.0  # original AI score preserved
    q2 = next(r for r in body["results"] if r["question"] == "Q2")
    assert q2["marks_awarded"] == 5.5 and q2["ai_marks_awarded"] == 4.0
    assert q2["justification"] == "Q2 AI remark"  # AI explanation kept
    assert q2["reviewer_comment"] == "Full working shown"
    audit = body["audit_history"][0]
    assert (audit["question"], audit["old_marks"], audit["new_marks"]) == ("Q2", 4.0, 5.5)
    assert audit["reason"] == "Units were correct" and audit["notes"] == "Checked handwriting"


@pytest.mark.parametrize(
    "overrides,reason,expected",
    [
        ([{"question": "Q1", "marks_awarded": 4.5}], "too high", 422),
        ([{"question": "Q1", "marks_awarded": -1}], "negative", 422),
        ([{"question": "Q9", "marks_awarded": 1}], "unknown q", 400),
        ([{"question": "Q1", "marks_awarded": 2}], None, 400),  # reason required
        ([], "empty", 400),
        ([{"question": "Q1", "marks_awarded": 3.0}], "no change", 400),
        ([{"question": "Q1", "marks_awarded": 1}, {"question": "q1", "marks_awarded": 2}], "dup", 400),
    ],
)
async def test_override_validation(client, world, overrides, reason, expected):
    res = await act(client, world.ta_1, world.subs_a[0], action="override", reason=reason, overrides=overrides)
    assert res.status_code == expected, res.text
    # Nothing was changed by a rejected request.
    d = await detail(client, world.ta_1, world.subs_a[0])
    assert d["submission"]["review_status"] == "ai_evaluated"
    assert d["submission"]["total"] == 7.0
    assert d["audit_history"] == []


async def test_escalation_flow_and_ta_cannot_finalise_escalated(client, world):
    sid = world.subs_a[1]
    bad = await act(client, world.ta_1, sid, action="escalate", reason="because")
    assert bad.status_code == 422
    other_without_notes = await act(client, world.ta_1, sid, action="escalate", reason="other")
    assert other_without_notes.status_code == 400

    res = await act(client, world.ta_1, sid, action="escalate", reason="ocr_unreliable", notes="Page 2 is smudged")
    assert res.status_code == 200, res.text
    assert res.json()["review_status"] == "escalated"

    for action in ("approve", "escalate"):
        res = await act(client, world.ta_1, sid, action=action, reason="ocr_unreliable")
        assert res.status_code == 409
    res = await act(client, world.ta_1, sid, action="override", reason="x", overrides=[{"question": "Q1", "marks_awarded": 1}])
    assert res.status_code == 409
    # TA cannot resolve.
    assert (await act(client, world.ta_1, sid, action="resolve")).status_code == 403

    # Shows up in the professor escalation queue with reason and TA.
    esc = (await client.get(f"{API}/professor/escalations", headers=auth(world.prof_a))).json()
    assert len(esc) == 1
    assert esc[0]["reason"] == "ocr_unreliable" and esc[0]["reason_label"] == "OCR unreliable"
    assert esc[0]["escalated_by"]["email"] == world.ta_1.email
    assert esc[0]["notes"] == "Page 2 is smudged"

    # Professor resolves with a mark change.
    res = await act(
        client, world.prof_a, sid, action="resolve", reason="Rechecked scan",
        overrides=[{"question": "Q2", "marks_awarded": 5}],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["review_status"] == "professor_approved"
    assert body["professor_total"] == 9.0
    actions = [a["action"] for a in body["audit_history"]]
    assert actions[:2] == ["resolve", "override"] and actions[-1] == "escalate"
    assert (await client.get(f"{API}/professor/escalations", headers=auth(world.prof_a))).json() == []


async def test_return_to_ta_requires_note_and_requeues(client, world):
    sid = world.subs_a[0]
    await act(client, world.ta_1, sid, action="approve")
    assert (await act(client, world.prof_a, sid, action="return_to_ta")).status_code == 400
    res = await act(client, world.prof_a, sid, action="return_to_ta", notes="Re-check Q2 units")
    assert res.status_code == 200
    assert res.json()["review_status"] == "ta_pending"
    queue = (await client.get(f"{API}/ta/reviews", headers=auth(world.ta_1))).json()
    assert str(sid) in {i["submission_id"] for i in queue["items"]}


async def test_professor_cannot_escalate_and_ta_cannot_touch_professor_approved(client, world):
    sid = world.subs_a[0]
    assert (await act(client, world.prof_a, sid, action="escalate", reason="other", notes="x")).status_code == 400
    assert (await act(client, world.prof_a, sid, action="approve")).status_code == 200
    res = await act(client, world.ta_1, sid, action="override", reason="nope", overrides=[{"question": "Q1", "marks_awarded": 0}])
    assert res.status_code == 409
    assert (await act(client, world.ta_1, sid, action="approve")).status_code == 409


async def test_optimistic_concurrency(client, world):
    sid = world.subs_a[0]
    await act(client, world.ta_1, sid, action="approve")
    stale = await act(client, world.ta_1, sid, action="escalate", reason="rubric_unclear", expected_review_status="ai_evaluated")
    assert stale.status_code == 409


async def test_unknown_action_and_legacy_reject_alias(client, world):
    assert (await act(client, world.ta_1, world.subs_a[0], action="delete")).status_code == 400
    res = await act(client, world.ta_1, world.subs_a[0], action="reject")
    assert res.status_code == 200
    assert res.json()["review_status"] == "escalated"
    assert res.json()["escalation_reason"] == "ai_grading_incorrect"


async def test_detail_contains_rubric_ai_evidence_and_permissions(client, world):
    d = await detail(client, world.ta_1, world.subs_a[2])
    assert d["exam"]["course_code"] == "CS3001"
    q1 = d["questions"][0]
    assert q1["rubric"]["key_points"][0].startswith("Newton")
    assert q1["criteria"][0]["criterion"] == "crit"
    assert d["permissions"] == {
        "can_approve": True, "can_override": True, "can_escalate": True,
        "can_resolve": False, "can_return": False, "read_only_reason": None,
    }
    prof = await detail(client, world.prof_a, world.subs_a[2])
    assert prof["permissions"]["can_escalate"] is False and prof["permissions"]["can_return"] is True


async def test_navigation_orders_by_lowest_confidence(client, world):
    # confidences: sub0 min 0.7, sub1 min 0.7 (0.7 vs 0.7), sub2 min 0.5 → sub2 first
    d = await detail(client, world.ta_1, world.subs_a[2])
    nav = d["navigation"]
    assert nav["position"] == 1 and nav["queue_size"] == 3
    assert nav["prev_id"] is None and nav["next_id"] is not None
    await act(client, world.ta_1, world.subs_a[2], action="approve")
    d = await detail(client, world.ta_1, world.subs_a[2])
    assert d["navigation"]["next_pending_id"] in {str(world.subs_a[0]), str(world.subs_a[1])}


async def test_queue_filters_and_sorting(client, world):
    h = auth(world.ta_1)
    q = (await client.get(f"{API}/ta/reviews", params={"sort": "confidence_asc"}, headers=h)).json()
    assert q["items"][0]["submission_id"] == str(world.subs_a[2])
    assert q["items"][0]["focus"]["question"] == "Q1"  # Q1 conf 0.5 < Q2 conf 0.7
    q = (await client.get(f"{API}/ta/reviews", params={"max_confidence": 0.6}, headers=h)).json()
    assert [i["submission_id"] for i in q["items"]] == [str(world.subs_a[2])]
    q = (await client.get(f"{API}/ta/reviews", params={"student": "24012201"}, headers=h)).json()
    assert [i["student_id"] for i in q["items"]] == ["24012201"]
    q = (await client.get(f"{API}/ta/reviews", params={"question": "q1"}, headers=h)).json()
    assert q["total"] == 3 and all(i["focus"]["question"] == "Q1" for i in q["items"])
    await act(client, world.ta_1, world.subs_a[0], action="escalate", reason="rubric_unclear")
    assert (await client.get(f"{API}/ta/reviews", params={"status": "escalated"}, headers=h)).json()["total"] == 1
    assert (await client.get(f"{API}/ta/reviews", headers=h)).json()["total"] == 2
    assert (await client.get(f"{API}/ta/reviews", params={"status": "bogus"}, headers=h)).status_code == 422


async def test_ta_history_and_dashboard_come_from_audit(client, world):
    await act(client, world.ta_1, world.subs_a[0], action="approve")
    res = await act(client, world.ta_1, world.subs_a[1], action="override", reason="Misread", overrides=[{"question": "Q1", "marks_awarded": 2}])
    assert res.status_code == 200, res.text
    await act(client, world.ta_1, world.subs_a[2], action="escalate", reason="ambiguous_answer")
    hist = (await client.get(f"{API}/ta/history", headers=auth(world.ta_1))).json()
    assert [i["action"] for i in hist["items"]] == ["escalate", "override", "approve"]
    assert hist["items"][1]["old_marks"] == 4.0 and hist["items"][1]["new_marks"] == 2.0
    dash = (await client.get(f"{API}/ta/dashboard", headers=auth(world.ta_1))).json()
    assert dash["reviewed_today"] == 3 and dash["total_reviewed"] == 3
    assert dash["overrides"] == 1 and dash["escalations_open"] == 1 and dash["pending_reviews"] == 0
    assert dash["assigned_exams"] == 1
    # Other TAs see none of it.
    assert (await client.get(f"{API}/ta/history", headers=auth(world.ta_2))).json()["total"] == 0


async def test_unevaluated_submission_cannot_be_reviewed(client, session, world):
    from app.db.models import ReviewStatus, StudentSubmission, SubmissionStatus

    sub = await session.get(StudentSubmission, world.subs_a[0])
    sub.status = SubmissionStatus.UPLOADED
    sub.review_status = ReviewStatus.NOT_EVALUATED
    await session.commit()
    assert (await act(client, world.ta_1, world.subs_a[0], action="approve")).status_code == 409
