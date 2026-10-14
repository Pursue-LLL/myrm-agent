"""Existing databases drop the shadow A/B verification tables and the version quality score; fresh databases never create them."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.database import migrations
from app.database.models import Base

_RETIRED_TABLES = (
    "skill_shadow_samples",
    "skill_ab_test_results",
    "skill_optimization_records",
    "skill_quality_history",
)
_FIRST_DROP = "DROP TABLE IF EXISTS skill_shadow_samples"

# The shape of an upgrading database: the retired tables carry their own indexes and skill_versions
# still carries the per-version quality score.
_UPGRADING_DB_DDL = """
CREATE TABLE skill_shadow_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_id VARCHAR(255) NOT NULL,
    skill_id VARCHAR(255) NOT NULL,
    inputs JSON NOT NULL,
    is_match BOOLEAN NOT NULL,
    baseline_latency_ms FLOAT NOT NULL,
    candidate_latency_ms FLOAT NOT NULL
);
CREATE INDEX ix_skill_shadow_samples_test_id ON skill_shadow_samples(test_id);
CREATE TABLE skill_ab_test_results (
    test_id VARCHAR(255) PRIMARY KEY,
    skill_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL
);
CREATE TABLE skill_optimization_records (
    optimization_id VARCHAR(255) PRIMARY KEY,
    skill_id VARCHAR(255) NOT NULL
);
CREATE TABLE skill_quality_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id VARCHAR(255) NOT NULL,
    overall_score FLOAT NOT NULL
);
CREATE INDEX idx_score ON skill_quality_history(overall_score);
ALTER TABLE skill_versions ADD COLUMN quality_score JSON;
"""


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        return {row[0] for row in rows}


async def _skill_version_columns(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(text("PRAGMA table_info(skill_versions)"))
        return {row[1] for row in rows}


@pytest.mark.asyncio
async def test_an_upgrading_database_loses_the_retired_tables_and_keeps_its_skill_versions(
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
                    "INSERT INTO skill_versions (skill_id, version, content, created_at, created_by, is_active, quality_score) "
                    "VALUES ('s1', 1, 'body', '2026-01-01 00:00:00', 'llm', 1, '{\"overall\": 0.9}')"
                )
            )
            await conn.execute(
                text(
                    "INSERT INTO skill_shadow_samples (test_id, skill_id, inputs, is_match, baseline_latency_ms, candidate_latency_ms) "
                    "VALUES ('t1', 's1', '{}', 1, 1.0, 1.0)"
                )
            )

        full_list = list(migrations.MIGRATION_STATEMENTS)
        # The upgrading user already recorded every migration that preceded the retirement.
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list[: full_list.index(_FIRST_DROP)])
        await migrations.run_migrations(engine)
        assert set(_RETIRED_TABLES) <= await _tables(engine)
        assert "quality_score" in await _skill_version_columns(engine)

        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", full_list)
        await migrations.run_migrations(engine)

        assert not set(_RETIRED_TABLES) & await _tables(engine)
        assert "quality_score" not in await _skill_version_columns(engine)
        async with engine.connect() as conn:
            row = (await conn.execute(text("SELECT content, is_active FROM skill_versions WHERE skill_id = 's1'"))).one()
        assert (row[0], row[1]) == ("body", 1)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_new_database_never_creates_them_and_migrations_stay_idempotent(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await migrations.run_migrations(engine)
        await migrations.run_migrations(engine)

        assert not set(_RETIRED_TABLES) & await _tables(engine)
        assert not set(_RETIRED_TABLES) & set(Base.metadata.tables)
        assert "quality_score" not in await _skill_version_columns(engine)
    finally:
        await engine.dispose()
