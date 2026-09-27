"""Async SQLAlchemy session management."""

import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import Base

logger = logging.getLogger(__name__)

settings = get_settings()
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _alembic_head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        root = Path(__file__).resolve().parents[2]
        cfg = Config(str(root / "alembic.ini"))
        cfg.set_main_option("script_location", str(root / "alembic"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:  # alembic files not shipped (e.g. slim image)
        return None


async def init_db() -> None:
    """Check the schema on startup. Tables are created by Alembic, not here.

    ``DB_AUTO_CREATE=true`` restores the old ``create_all`` behaviour for throwaway
    local databases only; it never alters existing tables.
    """
    if settings.db_auto_create:
        logger.warning("DB_AUTO_CREATE=true: creating missing tables with create_all()")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return

    head = _alembic_head()
    try:
        async with engine.connect() as conn:
            current = (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one_or_none()
    except Exception:
        current = None
    if head and current != head:
        logger.warning(
            "Database schema revision is %s but the code expects %s. "
            "Run `alembic upgrade head` before serving traffic.",
            current or "<none>",
            head,
        )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
