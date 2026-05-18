from fastapi import APIRouter

from app.api.routes import analytics, auth, bulk, evaluate, results, review, upload

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(bulk.router, prefix="/bulk", tags=["bulk"])
api_router.include_router(evaluate.router, prefix="/evaluate", tags=["evaluate"])
api_router.include_router(results.router, prefix="/results", tags=["results"])
api_router.include_router(review.router, prefix="/review", tags=["review"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
