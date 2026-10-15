"""Stored ``code_interpreter_tool`` capability tokens must become ``code_interpreter`` through the migration list."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.database import migrations
from app.database.models import Agent, Base, CronJobModel, SecurityProfile

_STALE = "code_interpreter_tool"
_SCHEDULE = {"kind": "cron", "expr": "0 9 * * *"}

# Captured once: the tests below swap ``MIGRATION_STATEMENTS`` for a prefix of it.
_FULL_LIST = list(migrations.MIGRATION_STATEMENTS)
_TOKEN_STATEMENTS = [stmt for stmt in _FULL_LIST if _STALE in stmt]
_FIRST_TOKEN_STATEMENT = _FULL_LIST.index(_TOKEN_STATEMENTS[0])


@pytest.fixture
async def legacy_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    """A database that already recorded every migration preceding the token migrations."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST[:_FIRST_TOKEN_STATEMENT])
        await migrations.run_migrations(engine)
        yield engine
    finally:
        await engine.dispose()


async def _seed(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        session.add_all(
            [
                CronJobModel(
                    id="job-stale",
                    name="devops",
                    job_type="agent",
                    schedule=_SCHEDULE,
                    required_capabilities=["shell_exec", "file_read", "file_write", _STALE],
                ),
                CronJobModel(
                    id="job-current",
                    name="research",
                    job_type="agent",
                    schedule=_SCHEDULE,
                    required_capabilities=["web_search_tool", "code_interpreter"],
                ),
                Agent(
                    id="agent-stale",
                    name="coder",
                    security_overrides={
                        "capabilities": ["web_search_tool", _STALE],
                        # Only a whole token is renamed; a value that merely contains the text is left alone.
                        "networkAllowlist": [f"{_STALE}.example.com"],
                    },
                ),
                SecurityProfile(
                    id="profile-stale",
                    profile_key="custom",
                    display_name="Custom",
                    config_json={
                        "capabilities": [
                            {"permission": _STALE, "pattern": "*"},
                            {"permission": "file_read", "pattern": "*"},
                        ]
                    },
                ),
            ]
        )
        await session.commit()


async def _stored(engine: AsyncEngine) -> tuple[object, object, object, object]:
    async with AsyncSession(engine) as session:
        stale_job = await session.get(CronJobModel, "job-stale")
        current_job = await session.get(CronJobModel, "job-current")
        agent = await session.get(Agent, "agent-stale")
        profile = await session.get(SecurityProfile, "profile-stale")
        assert stale_job and current_job and agent and profile
        return (
            stale_job.required_capabilities,
            current_job.required_capabilities,
            agent.security_overrides,
            profile.config_json,
        )


def test_the_token_migrations_are_one_statement_per_table_in_a_row() -> None:
    assert len(_TOKEN_STATEMENTS) == 3, "cron jobs, agents and security profiles"
    assert _FULL_LIST[_FIRST_TOKEN_STATEMENT : _FIRST_TOKEN_STATEMENT + 3] == _TOKEN_STATEMENTS


@pytest.mark.asyncio
async def test_migrations_rename_the_token_where_it_is_stored(
    legacy_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(legacy_engine)

    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST[: _FIRST_TOKEN_STATEMENT + 3])
    await migrations.run_migrations(legacy_engine)

    stale_job, current_job, agent, profile = await _stored(legacy_engine)
    assert stale_job == ["shell_exec", "file_read", "file_write", "code_interpreter"]
    assert current_job == ["web_search_tool", "code_interpreter"]
    assert agent == {
        "capabilities": ["web_search_tool", "code_interpreter"],
        "networkAllowlist": [f"{_STALE}.example.com"],
    }
    assert profile == {
        "capabilities": [
            {"permission": "code_interpreter", "pattern": "*"},
            {"permission": "file_read", "pattern": "*"},
        ]
    }


@pytest.mark.asyncio
async def test_token_statements_change_nothing_on_a_second_run(legacy_engine: AsyncEngine) -> None:
    await _seed(legacy_engine)
    async with legacy_engine.begin() as conn:
        for stmt in _TOKEN_STATEMENTS:
            await conn.execute(text(stmt))
    after_first = await _stored(legacy_engine)

    async with legacy_engine.begin() as conn:
        for stmt in _TOKEN_STATEMENTS:
            await conn.execute(text(stmt))

    assert await _stored(legacy_engine) == after_first
