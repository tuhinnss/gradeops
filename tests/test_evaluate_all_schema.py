"""Evaluate-all schema tests (no DB)."""

from app.schemas.evaluation import EvaluateAllRequest, EvaluateAllResponse


def test_evaluate_all_request_defaults():
    from uuid import uuid4

    body = EvaluateAllRequest(rubric_id=uuid4())
    assert body.submission_ids is None
    assert body.run_plagiarism_check is True


def test_evaluate_all_response():
    r = EvaluateAllResponse(
        total_processed=5,
        success_count=4,
        failed_count=1,
    )
    assert r.total_processed == 5
