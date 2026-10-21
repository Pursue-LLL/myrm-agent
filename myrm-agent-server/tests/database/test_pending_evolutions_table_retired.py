"""Existing databases drop the pending-evolutions table; fresh databases never create it."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.database import migrations
from app.database.models import Base, Chat

_TABLE = "pending_evolutions"
_DROP = f"DROP TABLE IF EXISTS {_TABLE}"

# The shape of an upgrading database: proposals once lived here before moving to `approval_records`.
_UPGRADING_DB_DDL = """
CREATE TABLE pending_evolutions (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    skill_id VARCHAR(255) NOT NULL,
    skill_name VARCHAR(255) NOT NULL,
    skill_path VARCHAR(1000) NOT NULL,
    evolution_type VARCHAR(50) NOT NULL,
    reason TEXT NOT NULL,
    original_content TEXT NOT NULL,
    evolved_content TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    test_passed BOOLEAN NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
    resolved_at DATETIME
);
CREATE INDEX ix_pending_evolutions_skill_id ON pending_evolutions(skill_id);
CREATE INDEX ix_pending_evolutions_status ON pending_evolutions(status);
"""


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in rows}


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_table_and_keeps_everything_else(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in filter(None, (part.strip() for part in _UPGRADING_DB_DDL.split(";"))):
                await conn.execute(text(statement))
            await conn.execute(
                text(
                    "INSERT INTO pending_evolutions "
                    "(id, skill_id, skill_name, skill_path, evolution_type, reason, original_content, evolved_content, "
                    "confidence, test_passed) "
                    "VALUES ('e1', 's1', 'skill', '/tmp/skill', 'fix', 'r', 'a', 'b', 0.9, 1)"
                )
            )
        async with AsyncSession(engine) as session:
            session.add(Chat(id="c1", title="Kept chat", action_mode="fast", source="web"))
            await session.commit()

        full_list = list(migrations.MIGRATION_STATEMENTS)
        # The upgrading user already recorded every migration that preceded the table drop.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[: full_list.index(_DROP)])
        await migrations.run_migrations(engine)
        assert _TABLE in await _tables(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert _TABLE not in await _tables(engine)
        async with engine.connect() as conn:
            assert (await conn.execute(text("SELECT COUNT(*) FROM chats WHERE id = 'c1'"))).scalar_one() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_creates_it_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert _TABLE not in await _tables(engine)
        assert _TABLE not in Base.metadata.tables
    finally:
        await engine.dispose()
