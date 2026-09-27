"""Upload API schemas."""

from uuid import UUID

from app.schemas.common import ApiModel


class UploadResponse(ApiModel):
    id: UUID
    message: str
    filename: str


class RubricUploadResponse(UploadResponse):
    question_count: int


class EvaluateRequest(ApiModel):
    submission_id: UUID
    rubric_id: UUID | None = None
    run_plagiarism_check: bool = True


class BatchEvaluateRequest(ApiModel):
    submission_ids: list[UUID]
    rubric_id: UUID
    run_plagiarism_check: bool = True
