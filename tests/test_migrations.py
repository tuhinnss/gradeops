"""The Alembic migrations produce exactly the schema the ORM models describe."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.db.models import Base

pytestmark = pytest.mark.db


async def test_models_match_migrated_schema(db_clean):
    from app.db.session import engine

    def diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)

    async with engine.connect() as conn:
        changes = await conn.run_sync(diff)
    assert changes == [], f"Models and migrations differ — add a migration: {changes}"


async def test_migrated_to_head(db_clean):
    from sqlalchemy import text

    from app.db.session import _alembic_head, engine

    async with engine.connect() as conn:
        current = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    assert current == _alembic_head()
