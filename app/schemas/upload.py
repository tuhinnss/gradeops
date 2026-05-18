"""Upload API schemas."""

from uuid import UUID

from pydantic import BaseModel


class UploadResponse(BaseModel):
    id: UUID
    message: str
    filename: str


class RubricUploadResponse(UploadResponse):
    question_count: int


class EvaluateRequest(BaseModel):
    submission_id: UUID
    rubric_id: UUID | None = None
    run_plagiarism_check: bool = True


class BatchEvaluateRequest(BaseModel):
    submission_ids: list[UUID]
    rubric_id: UUID
    run_plagiarism_check: bool = True
