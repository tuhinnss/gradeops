"""Authorization: role checks + ownership/assignment checks on every resource.

Knowing a UUID must never be enough. Inaccessible resources answer 404 (no
existence leak); visible resources the role may not change answer 403.
"""

import json
import uuid

import pytest

from app.db.models import StudentSubmission
from tests.helpers import API, RUBRIC, auth, build_world

pytestmark = pytest.mark.db


@pytest.fixture
async def world(client, session):
    return await build_world(client, session)


# --- Authentication required ---------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/professor/dashboard"),
        ("get", "/ta/dashboard"),
        ("get", "/courses"),
        ("get", "/exams"),
        ("get", "/ta/reviews"),
        ("get", "/rubrics"),
        ("get", "/analytics/submissions"),
    ],
)
async def test_unauthenticated_requests_rejected(client, db_clean, method, path):
    res = await getattr(client, method)(f"{API}{path}")
    assert res.status_code == 401


async def test_legacy_endpoints_require_auth_by_default(client, world):
    sid = world.subs_a[0]
    for path in (f"/results/{sid}", f"/review/{sid}", f"/results/{sid}/json", f"/review/{sid}/detail"):
        res = await client.get(f"{API}{path}")
        assert res.status_code == 401, path
    res = await client.post(f"{API}/review/{sid}/action", json={"action": "approve"})
    assert res.status_code == 401
    res = await client.post(
        f"{API}/upload/rubric", files={"file": ("r.json", json.dumps(RUBRIC).encode(), "application/json")}
    )
    assert res.status_code == 401


# --- Role checks ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path_tpl,body",
    [
        ("get", "/professor/dashboard", None),
        ("get", "/professor/escalations", None),
        ("get", "/professor/integrity", None),
        ("get", "/professor/submissions", None),
        ("post", "/courses", {"name": "X", "course_code": "X1"}),
        ("patch", "/courses/{course_a}", {"name": "Hacked"}),
        ("delete", "/courses/{course_a}", None),
        ("get", "/courses/{course_a}/students", None),
        ("post", "/courses/{course_a}/students", {"students": [{"student_id": "S9"}]}),
        ("get", "/courses/{course_a}/tas", None),
        ("post", "/courses/{course_a}/tas", {"email": "x@uni.edu"}),
        ("delete", "/courses/{course_a}/tas/{ta_2}", None),
        ("post", "/exams", {"course_id": "{course_a}", "name": "Evil"}),
        ("patch", "/exams/{exam_a}", {"name": "Renamed"}),
        ("post", "/exams/{exam_a}/tas", {"ta_id": "{ta_2}"}),
        ("delete", "/exams/{exam_a}/tas/{ta_1}", None),
        ("post", "/exams/{exam_a}/distribute", {}),
        ("post", "/exams/{exam_a}/evaluate", {}),
        ("put", "/exams/{exam_a}/rubric", {"rubric_id": "{rubric_a}"}),
        ("get", "/exams/{exam_a}/publish-summary", None),
        ("post", "/exams/{exam_a}/approve", {}),
        ("post", "/exams/{exam_a}/lock", {}),
        ("post", "/exams/{exam_a}/publish", {"acknowledge_integrity_flags": True}),
        ("post", "/exams/{exam_a}/reopen", {"reason": "because"}),
        ("get", "/exams/{exam_a}/gradebook", None),
        ("get", "/exams/{exam_a}/gradebook.csv", None),
        ("get", "/exams/{exam_a}/integrity", None),
        ("get", "/rubrics", None),
        ("put", "/rubrics/{rubric_a}", {"name": "TA edit"}),
        ("post", "/evaluate/run", {"submission_id": "{sub_a0}"}),
        ("post", "/evaluate/all", {"rubric_id": "{rubric_a}"}),
        ("post", "/bulk/jobs", {"rubric_id": "{rubric_a}", "submission_ids": ["{sub_a0}"]}),
        ("get", "/analytics/rubric/{rubric_a}", None),
    ],
)
async def test_assigned_ta_cannot_use_professor_functions(client, world, method, path_tpl, body):
    """Even the TA assigned to exam A cannot manage it (403), and nothing changes."""
    subs = {
        "course_a": world.course_a["id"], "exam_a": world.exam_a["id"], "rubric_a": str(world.rubric_a),
        "ta_1": str(world.ta_1.id), "ta_2": str(world.ta_2.id), "sub_a0": str(world.subs_a[0]),
    }
    path = path_tpl.format(**subs)
    payload = json.loads(_fill(json.dumps(body), subs)) if body is not None else None
    kwargs = {"headers": auth(world.ta_1)}
    if payload is not None:
        kwargs["json"] = payload
    res = await client.request(method.upper(), f"{API}{path}", **kwargs)
    assert res.status_code in (403, 404), f"{method} {path}: {res.status_code} {res.text}"
    if path.startswith("/professor") or path in ("/courses", "/exams", "/rubrics"):
        assert res.status_code == 403


def _fill(text: str, subs: dict[str, str]) -> str:
    for key, value in subs.items():
        text = text.replace("{" + key + "}", value)
    return text


async def test_ta_cannot_upload_or_modify_rubric_through_legacy_api(client, world):
    res = await client.post(
        f"{API}/upload/rubric",
        files={"file": ("r.json", json.dumps(RUBRIC).encode(), "application/json")},
        headers=auth(world.ta_1),
    )
    assert res.status_code == 403
    res = await client.post(
        f"{API}/exams/{world.exam_a['id']}/rubric",
        files={"file": ("r.json", json.dumps(RUBRIC).encode(), "application/json")},
        headers=auth(world.ta_1),
    )
    assert res.status_code == 403
    res = await client.post(
        f"{API}/exams/{world.exam_a['id']}/submissions",
        files=[("files", ("x.pdf", b"%PDF-1.4", "application/pdf"))],
        headers=auth(world.ta_1),
    )
    assert res.status_code == 403


async def test_professor_cannot_use_ta_workspace(client, world):
    for path in ("/ta/dashboard", "/ta/exams", "/ta/reviews", "/ta/history", f"/ta/reviews/{world.subs_a[0]}"):
        res = await client.get(f"{API}{path}", headers=auth(world.prof_a))
        assert res.status_code == 403, path


# --- Ownership: professor A vs professor B ----------------------------------------------------


async def test_professor_cannot_access_another_professors_resources(client, world):
    h = auth(world.prof_a)
    cid, eid, sid = world.course_b["id"], world.exam_b["id"], world.subs_b[0]
    rid = world.exam_b["rubric"]["id"]
    for path in (
        f"/courses/{cid}", f"/courses/{cid}/students", f"/courses/{cid}/tas", f"/courses/{cid}/analytics",
        f"/exams/{eid}", f"/exams/{eid}/gradebook", f"/exams/{eid}/analytics", f"/exams/{eid}/rubric",
        f"/exams/{eid}/submissions", f"/rubrics/{rid}", f"/results/{sid}", f"/review/{sid}",
        f"/review/{sid}/detail", f"/review/{sid}/pages/0", f"/results/{sid}/annotated-pdf",
    ):
        res = await client.get(f"{API}{path}", headers=h)
        assert res.status_code == 404, f"{path}: {res.status_code}"
    for method, path, body in (
        ("PATCH", f"/courses/{cid}", {"name": "Taken over"}),
        ("POST", f"/courses/{cid}/tas", {"email": world.ta_1.email}),
        ("POST", "/exams", {"course_id": cid, "name": "Injected"}),
        ("POST", f"/exams/{eid}/publish", {"acknowledge_integrity_flags": True}),
        ("POST", f"/review/{sid}/action", {"action": "approve"}),
        ("PUT", f"/rubrics/{rid}", {"name": "stolen"}),
    ):
        res = await client.request(method, f"{API}{path}", json=body, headers=h)
        assert res.status_code == 404, f"{method} {path}: {res.status_code}"
    # Listings never include the other professor's data.
    courses = (await client.get(f"{API}/courses", headers=h)).json()
    assert [c["id"] for c in courses] == [world.course_a["id"]]
    exams = (await client.get(f"{API}/exams", headers=h)).json()
    assert [e["id"] for e in exams] == [world.exam_a["id"]]
    subs = (await client.get(f"{API}/professor/submissions", headers=h)).json()
    assert {i["submission_id"] for i in subs["items"]} == {str(s) for s in world.subs_a}


# --- Assignment: TA scope -------------------------------------------------------------------


async def test_ta_cannot_access_other_course_exam_or_submission(client, world):
    h = auth(world.ta_1)
    cid, eid, sid = world.course_b["id"], world.exam_b["id"], world.subs_b[0]
    for path in (
        f"/courses/{cid}", f"/exams/{eid}", f"/exams/{eid}/analytics", f"/exams/{eid}/rubric",
        f"/ta/reviews/{sid}", f"/review/{sid}", f"/review/{sid}/detail", f"/results/{sid}",
        f"/review/{sid}/source-pdf", f"/review/{sid}/answer-image?question=Q1",
    ):
        res = await client.get(f"{API}{path}", headers=h)
        assert res.status_code == 404, f"{path}: {res.status_code}"
    res = await client.post(f"{API}/review/{sid}/action", json={"action": "approve"}, headers=h)
    assert res.status_code == 404


async def test_unassigned_ta_on_same_course_cannot_see_exam(client, world):
    """ta_2 is course staff but not assigned to exam A."""
    h = auth(world.ta_2)
    assert (await client.get(f"{API}/exams/{world.exam_a['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=h)).status_code == 404
    queue = (await client.get(f"{API}/ta/reviews", headers=h)).json()
    assert queue["total"] == 0
    exams = (await client.get(f"{API}/ta/exams", headers=h)).json()
    assert exams == []
    # Course itself is visible read-only (they are staff on it).
    assert (await client.get(f"{API}/courses/{world.course_a['id']}", headers=h)).status_code == 200


async def test_assigned_ta_sees_only_assigned_scope(client, world):
    h = auth(world.ta_1)
    queue = (await client.get(f"{API}/ta/reviews", headers=h)).json()
    assert {i["submission_id"] for i in queue["items"]} == {str(s) for s in world.subs_a}
    exams = (await client.get(f"{API}/ta/exams", headers=h)).json()
    assert [e["id"] for e in exams] == [world.exam_a["id"]]
    detail = await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=h)
    assert detail.status_code == 200
    # Limited analytics: no per-student list for TAs.
    analytics = (await client.get(f"{API}/exams/{world.exam_a['id']}/analytics", headers=h)).json()
    assert analytics["students"] is None


async def test_removed_ta_loses_access_immediately(client, world):
    res = await client.delete(
        f"{API}/courses/{world.course_a['id']}/tas/{world.ta_1.id}", headers=auth(world.prof_a)
    )
    assert res.status_code == 204
    h = auth(world.ta_1)
    assert (await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/exams/{world.exam_a['id']}", headers=h)).status_code == 404
    assert (await client.get(f"{API}/ta/reviews", headers=h)).json()["total"] == 0


async def test_unassigning_ta_from_exam_revokes_access(client, world):
    res = await client.delete(
        f"{API}/exams/{world.exam_a['id']}/tas/{world.ta_1.id}", headers=auth(world.prof_a)
    )
    assert res.status_code == 200
    assert (await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=auth(world.ta_1))).status_code == 404


async def test_per_submission_assignment_restricts_other_tas(client, session, world):
    # Put ta_2 on the exam too, then give sub 0 explicitly to ta_2.
    await client.post(
        f"{API}/exams/{world.exam_a['id']}/tas", json={"ta_id": str(world.ta_2.id)}, headers=auth(world.prof_a)
    )
    sub = await session.get(StudentSubmission, world.subs_a[0])
    sub.assigned_ta_id = world.ta_2.id
    await session.commit()
    res = await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=auth(world.ta_1))
    assert res.status_code == 404
    res = await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=auth(world.ta_2))
    assert res.status_code == 200


async def test_archived_course_hides_it_from_tas(client, world):
    await client.delete(f"{API}/courses/{world.course_a['id']}", headers=auth(world.prof_a))
    assert (await client.get(f"{API}/ta/reviews/{world.subs_a[0]}", headers=auth(world.ta_1))).status_code == 404
    # The professor still has read access to the archived course.
    assert (await client.get(f"{API}/courses/{world.course_a['id']}", headers=auth(world.prof_a))).status_code == 200


async def test_random_uuid_is_404_not_500(client, world):
    for path in (f"/exams/{uuid.uuid4()}", f"/courses/{uuid.uuid4()}", f"/review/{uuid.uuid4()}/detail"):
        res = await client.get(f"{API}{path}", headers=auth(world.prof_a))
        assert res.status_code == 404
