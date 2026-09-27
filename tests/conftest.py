"""Pytest fixtures.

Database tests run against a real PostgreSQL database (JSONB, native enums), built
with the project's Alembic migrations. Configure it with ``TEST_DATABASE_URL``
(default ``postgresql+asyncpg://gradeops:gradeops@localhost:5432/gradeops_test``);
tests marked ``db`` are skipped when it is unreachable.
"""

import asyncio
import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

# Must run before any ``app`` import: settings are cached at import time.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://gradeops:gradeops@localhost:5432/gradeops_test"
)
_TMP = Path(tempfile.mkdtemp(prefix="gradeops-tests-"))
os.environ.update(
    {
        "DATABASE_URL": TEST_DATABASE_URL,
        "ENVIRONMENT": "test",
        "AUTH_ENABLED": "true",
        "JWT_SECRET_KEY": "test-secret-" + uuid.uuid4().hex,
        "UPLOAD_DIR": str(_TMP / "uploads"),
        "OUTPUT_DIR": str(_TMP / "outputs"),
        "MODELS_CACHE_DIR": str(_TMP / "models"),
        "OCR_ENGINE": "tesseract",
        "OCR_PREPROCESS": "false",
        "EMBEDDING_FALLBACK": "lexical",
        "BCRYPT_ROUNDS": "4",
    }
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _postgres_available() -> bool:
    async def probe() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        finally:
            await engine.dispose()

    try:
        asyncio.run(asyncio.wait_for(probe(), timeout=5))
        return True
    except Exception:
        return False


def _reset_and_migrate() -> None:
    async def reset() -> None:
        engine = create_async_engine(TEST_DATABASE_URL)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    command.upgrade(cfg, "head")


_DB_STATE: dict[str, bool] = {}


@pytest.fixture(scope="session")
def migrated_db() -> None:
    if "ready" not in _DB_STATE:
        _DB_STATE["ready"] = _postgres_available()
        if _DB_STATE["ready"]:
            _reset_and_migrate()
    if not _DB_STATE["ready"]:
        pytest.skip(f"PostgreSQL test database unavailable ({TEST_DATABASE_URL})")


TABLES = (
    "integrity_flags, exam_audits, review_audits, evaluation_logs, extracted_answers, "
    "plagiarism_reports, student_submissions, batch_jobs, exam_tas, exams, enrollments, "
    "students, course_members, courses, rubrics, users"
)


@pytest.fixture
async def db_clean(migrated_db) -> AsyncIterator[None]:
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
async def session(db_clean):
    from app.db.session import async_session_factory

    async with async_session_factory() as s:
        yield s


@pytest.fixture
async def client(db_clean) -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_rubric_dict():
    return {
        "title": "Test Exam",
        "items": [
            {
                "question_number": "Q1",
                "max_marks": 5,
                "key_points": [
                    "Newton's second law F=ma",
                    "Force is proportional to acceleration",
                ],
                "negative_conditions": ["Wrong formula"],
                "partial_credit_rules": [
                    {"condition": "Partial explanation of force", "marks": 2}
                ],
            }
        ],
    }


