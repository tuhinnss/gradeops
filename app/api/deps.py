"""FastAPI dependencies."""

from app.services.pipeline import GradeOpsPipeline


_pipeline: GradeOpsPipeline | None = None


def get_pipeline() -> GradeOpsPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = GradeOpsPipeline()
    return _pipeline
