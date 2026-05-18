"""Batch upload and job schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.db.models import BatchJobStatus


class BulkUploadItem(BaseModel):
    id: UUID
    student_id: str
    filename: str


class BulkUploadResponse(BaseModel):
    uploaded: list[BulkUploadItem]
    failed: list[dict] = Field(default_factory=list)
    message: str


class BatchJobCreate(BaseModel):
    rubric_id: UUID
    submission_ids: list[UUID]
    run_plagiarism_check: bool = True


class BatchJobResponse(BaseModel):
    id: UUID
    rubric_id: UUID
    status: BatchJobStatus
    total_count: int
    completed_count: int
    failed_count: int
    progress_percent: float
    submission_ids: list
    errors: list = Field(default_factory=list)

    model_config = {"from_attributes": True}
