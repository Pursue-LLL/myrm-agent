"""Existing databases lose the batch image job table and ``media_library.batch_job_id``; fresh ones never keep them."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.database import migrations
from app.database.models import Base, MediaLibrary

_TABLE = "batch_image_jobs"
_COLUMN = "batch_job_id"
_INDEX = "idx_media_library_batch_job_id"
_CREATE_INDEX = f"CREATE INDEX IF NOT EXISTS {_INDEX} ON media_library({_COLUMN})"
_DROP_INDEX = f"DROP INDEX IF EXISTS {_INDEX}"
_DROP_COLUMN = f"ALTER TABLE media_library DROP COLUMN {_COLUMN}"
_DROP_TABLE = f"DROP TABLE IF EXISTS {_TABLE}"
_FULL_LIST = list(migrations.INDEX_STATEMENTS)
# An upgrading database already recorded every statement that precedes the first drop.
_RELEASED = _FULL_LIST[: _FULL_LIST.index(_DROP_INDEX)]

# The shape of an upgrading database: the table the models no longer map, and the link column with its index.
_UPGRADING_DB_DDL = (
    f"ALTER TABLE media_library ADD COLUMN {_COLUMN} VARCHAR(32)",
    _CREATE_INDEX,
    """CREATE TABLE batch_image_jobs (
        id VARCHAR(32) PRIMARY KEY,
        status VARCHAR(20) NOT NULL DEFAULT 'draft',
        plan JSON,
        concurrency INTEGER NOT NULL DEFAULT 3,
        total_items INTEGER NOT NULL DEFAULT 0,
        completed_items INTEGER NOT NULL DEFAULT 0,
        failed_items INTEGER NOT NULL DEFAULT 0,
        estimated_cost VARCHAR(32),
        session_id VARCHAR(255),
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        finished_at TIMESTAMP
    )""",
)


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[0] for row in await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}


async def _indexes(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[0] for row in await conn.execute(text("SELECT name FROM sqlite_master WHERE type='index'"))}


async def _media_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return {row[1] for row in await conn.execute(text("PRAGMA table_info(media_library)"))}


def test_the_index_goes_before_the_column_it_covers() -> None:
    # SQLite refuses to drop an indexed column, and both statements share one list and one ledger.
    assert _FULL_LIST.index(_CREATE_INDEX) < _FULL_LIST.index(_DROP_INDEX) < _FULL_LIST.index(_DROP_COLUMN)
    assert _FULL_LIST.index(_DROP_TABLE) > _FULL_LIST.index(_DROP_INDEX)


def test_the_models_map_neither_the_table_nor_the_column() -> None:
    assert _TABLE not in Base.metadata.tables
    assert _COLUMN not in MediaLibrary.__table__.columns


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_table_and_the_column_and_keeps_its_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'upgrading.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in _UPGRADING_DB_DDL:
                await conn.execute(text(statement))
        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _RELEASED)
        await migrations.create_indexes(engine)
        assert _COLUMN in await _media_columns(engine)
        assert _INDEX in await _indexes(engine)

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO media_library (id, media_type, source, content_type, file_size, storage_key, "
                    "prompt, model, session_id, batch_job_id) VALUES ('media_kept', 'image', 'generate', 'image/png', "
                    "3, 'media/sandbox/media_kept.png', 'a lighthouse', 'gpt-image-2.6-sunburst', 'chat-1', 'job-1')"
                )
            )
            await conn.execute(text("INSERT INTO batch_image_jobs (id, status) VALUES ('job-1', 'completed')"))

        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_LIST)
        await migrations.create_indexes(engine)

        assert _TABLE not in await _tables(engine)
        assert _COLUMN not in await _media_columns(engine)
        assert _INDEX not in await _indexes(engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            media = (await session.execute(select(MediaLibrary))).scalar_one()
        assert (media.id, media.prompt, media.model, media.session_id, media.storage_key) == (
            "media_kept",
            "a lighthouse",
            "gpt-image-2.6-sunburst",
            "chat-1",
            "media/sandbox/media_kept.png",
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_database_that_never_had_them_skips_the_drops(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'never_had_them.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _RELEASED)
        await migrations.create_indexes(engine)

        monkeypatch.setattr(migrations, "INDEX_STATEMENTS", _FULL_LIST)
        await migrations.create_indexes(engine)

        assert _TABLE not in await _tables(engine)
        assert _COLUMN not in await _media_columns(engine)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_keeps_them_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.create_indexes(engine)
        await migrations.create_indexes(engine)

        assert _TABLE not in await _tables(engine)
        assert _COLUMN not in await _media_columns(engine)
        assert _INDEX not in await _indexes(engine)
    finally:
        await engine.dispose()
