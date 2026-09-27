from fastapi import APIRouter

from app.api.routes import (
    analytics,
    auth,
    bulk,
    courses,
    evaluate,
    exams,
    professor,
    results,
    review,
    rubrics,
    ta,
    upload,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# Legacy single-upload workbench API (kept backward compatible, now access-checked).
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(bulk.router, prefix="/bulk", tags=["bulk"])
api_router.include_router(evaluate.router, prefix="/evaluate", tags=["evaluate"])
api_router.include_router(results.router, prefix="/results", tags=["results"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
# Shared human review (TA + professor).
api_router.include_router(review.router, prefix="/review", tags=["review"])
# Academic hierarchy and role workspaces.
api_router.include_router(courses.router, prefix="/courses", tags=["courses"])
api_router.include_router(exams.router, prefix="/exams", tags=["exams"])
api_router.include_router(rubrics.router, prefix="/rubrics", tags=["rubrics"])
api_router.include_router(professor.router, prefix="/professor", tags=["professor"])
api_router.include_router(ta.router, prefix="/ta", tags=["ta"])
