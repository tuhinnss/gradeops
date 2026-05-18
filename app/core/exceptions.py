"""Custom application exceptions."""

from fastapi import HTTPException, status


class GradeOpsError(Exception):
    """Base exception for domain errors."""

    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class OCRProcessingError(GradeOpsError):
    pass


class RubricParseError(GradeOpsError):
    pass


class EvaluationError(GradeOpsError):
    pass


def http_error(exc: GradeOpsError, status_code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"message": exc.message, "details": exc.details},
    )
