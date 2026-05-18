"""Batch schema validation."""

import uuid

from app.schemas.batch import BatchJobCreate


def test_batch_job_create():
    body = BatchJobCreate(
        rubric_id=uuid.uuid4(),
        submission_ids=[uuid.uuid4()],
        run_plagiarism_check=True,
    )
    assert body.run_plagiarism_check is True
