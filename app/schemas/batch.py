"""Batch upload and job schemas."""

from uuid import UUID

from pydantic import Field

from app.db.models import BatchJobStatus
from app.schemas.common import ApiModel


class BulkUploadItem(ApiModel):
    id: UUID
    student_id: str
    filename: str


class BulkUploadResponse(ApiModel):
    uploaded: list[BulkUploadItem]
    failed: list[dict] = Field(default_factory=list)
    message: str


class BatchJobCreate(ApiModel):
    rubric_id: UUID
    submission_ids: list[UUID]
    run_plagiarism_check: bool = True


class JobError(ApiModel):
    submission_id: str | None = None
    error: str | None = None
    message: str | None = None


class BatchJobResponse(ApiModel):
    id: UUID
    rubric_id: UUID
    exam_id: UUID | None = None
    status: BatchJobStatus
    total_count: int
    completed_count: int
    failed_count: int
    progress_percent: float
    submission_ids: list[str]
    errors: list[JobError] = Field(default_factory=list)

    model_config = {"from_attributes": True}
