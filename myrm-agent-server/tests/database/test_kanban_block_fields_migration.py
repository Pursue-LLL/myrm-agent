"""A task outside the blocked column loses the block details it still stores; a blocked task keeps them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.database import migrations
from app.database.models import Base
from app.database.models.kanban import KanbanBoardModel, KanbanTaskModel

_REASON = "Need your decision: Postgres or SQLite?"
_WAKE_AT = datetime(2030, 1, 1, 3, tzinfo=UTC)

# Captured once: the tests below swap ``MIGRATION_STATEMENTS`` for a prefix of it.
_FULL_LIST = list(migrations.MIGRATION_STATEMENTS)
_BLOCK_FIELDS_STATEMENT = next(stmt for stmt in _FULL_LIST if stmt.lstrip().startswith("UPDATE kanban_tasks SET blocked_reason"))
_BLOCK_FIELDS_INDEX = _FULL_LIST.index(_BLOCK_FIELDS_STATEMENT)


@pytest.fixture
async def legacy_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    """A database that already recorded every migration preceding the block-field cleanup."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy.db'}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST[:_BLOCK_FIELDS_INDEX])
        await migrations.run_migrations(engine)
        yield engine
    finally:
        await engine.dispose()


async def _seed(engine: AsyncEngine) -> None:
    def task(task_id: str, status: str, **block: object) -> KanbanTaskModel:
        return KanbanTaskModel(id=task_id, board_id="b1", title=task_id, status=status, **block)

    async with AsyncSession(engine) as session:
        session.add(KanbanBoardModel(id="b1", name="Board"))
        await session.flush()
        session.add_all(
            [
                task("moved-to-backlog", "backlog", blocked_reason=_REASON, block_kind="human"),
                task("moved-to-ready", "ready", block_kind="scheduled", scheduled_until=_WAKE_AT),
                task("moved-to-done", "completed", blocked_reason=_REASON),
                task("plain-backlog", "backlog"),
                task("blocked-by-user", "blocked", blocked_reason=_REASON, block_kind="human"),
                task("blocked-until-later", "blocked", block_kind="scheduled", scheduled_until=_WAKE_AT),
            ]
        )
        await session.commit()


async def _block_details(engine: AsyncEngine) -> dict[str, tuple[str | None, str | None, bool]]:
    """Each task's reason, kind and whether it still holds a wake-up time."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT id, blocked_reason, block_kind, scheduled_until FROM kanban_tasks"))
        return {row[0]: (row[1], row[2], row[3] is not None) for row in rows}


@pytest.mark.asyncio
async def test_the_cleanup_clears_only_tasks_outside_the_blocked_column(
    legacy_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _seed(legacy_engine)

    monkeypatch.setattr(migrations, "MIGRATION_STATEMENTS", _FULL_LIST[: _BLOCK_FIELDS_INDEX + 1])
    await migrations.run_migrations(legacy_engine)

    assert await _block_details(legacy_engine) == {
        "moved-to-backlog": (None, None, False),
        "moved-to-ready": (None, None, False),
        "moved-to-done": (None, None, False),
        "plain-backlog": (None, None, False),
        "blocked-by-user": (_REASON, "human", False),
        "blocked-until-later": (None, "scheduled", True),
    }


@pytest.mark.asyncio
async def test_the_cleanup_changes_nothing_on_a_second_run(legacy_engine: AsyncEngine) -> None:
    await _seed(legacy_engine)
    async with legacy_engine.begin() as conn:
        await conn.execute(text(_BLOCK_FIELDS_STATEMENT))
    after_first = await _block_details(legacy_engine)

    async with legacy_engine.begin() as conn:
        await conn.execute(text(_BLOCK_FIELDS_STATEMENT))

    assert await _block_details(legacy_engine) == after_first
