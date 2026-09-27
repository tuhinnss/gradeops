"""GRADEOPS FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import api_router
from app.config import get_settings
from app.core.exceptions import GradeOpsError
from app.core.logging import setup_logging
from app.db.session import init_db

logger = logging.getLogger(__name__)
settings = get_settings()


DEFAULT_JWT_SECRETS = {"change-me-in-production-use-openssl-rand", "change-me-in-production"}


def check_security_settings() -> None:
    if settings.auth_enabled and settings.jwt_secret_key in DEFAULT_JWT_SECRETS:
        if settings.environment == "production":
            raise RuntimeError("JWT_SECRET_KEY must be set to a random value in production")
        logger.warning("JWT_SECRET_KEY is the default value — set a random secret before deploying")
    if not settings.auth_enabled:
        if settings.environment == "production":
            raise RuntimeError("AUTH_ENABLED=false is not allowed in production")
        logger.warning(
            "AUTH_ENABLED=false: legacy workbench endpoints are open to anonymous users "
            "(local demo mode). Role dashboards still require login."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(settings.debug)
    check_security_settings()
    await init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    description="AI-powered handwritten exam evaluation API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Read by the dashboard: CSV download names and answer-image page/crop info.
    expose_headers=["Content-Disposition", "X-Page-Index", "X-Cropped"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.exception_handler(GradeOpsError)
async def gradeops_error_handler(_request: Request, exc: GradeOpsError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": type(exc).__name__, "message": exc.message}},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.app_name, "version": "0.1.0"}


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/health",
        "api": settings.api_prefix,
    }
