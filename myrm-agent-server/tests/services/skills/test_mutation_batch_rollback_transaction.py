"""Batch rollback on the production SQLite transaction policy (WAL file, deferred read / immediate write).

The restore commits skill version rows through sessions of its own while the request session still has to consume
the batch rows. A request session that keeps its read snapshot open across the restore fails its final DELETE with
SQLITE_BUSY_SNAPSHOT ("database is locked", which busy_timeout does not cover): the files were restored but the undo
answered 503. In-memory SQLite shares one connection and cannot show this, so these tests run on a real file.
"""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.database.factory import register_sqlite_transaction_events
from app.database.models import Base, BatchSnapshot
from app.services.skill_optimization.rollback_service import RollbackService
from app.services.skills import mutation_batch_service as mbs
from app.services.skills.mutation_batch_service import MutationBatchRollbackError, rollback_skill_mutation_batch

SKILL_ID = "skill-1"
BATCH_ID = "batch-1"
MD_BEFORE = "---\nname: demo\n---\n# before\n"
MD_LIVE = "---\nname: demo\n---\n# live\n"
_BUSY_TIMEOUT_MS = 300


def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    cursor.close()


@pytest.fixture()
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'rollback.db'}",
        future=True,
        connect_args={"check_same_thread": False},
        pool_size=3,
        max_overflow=2,
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture()
def storage(session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch) -> SQLAlchemyStorage:
    """The version store every restore writes through, bound to the same database as the request session."""
    bound = SQLAlchemyStorage(session_factory=session_factory)
    monkeypatch.setattr("app.services.skill_optimization.bootstrap.get_skill_optimization_storage", lambda: bound)
    return bound


async def _seed_snapshot(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await RollbackService(session).insert_mutation_batch_snapshot(
            batch_id=BATCH_ID,
            skill_id=SKILL_ID,
            skill_content=MD_BEFORE,
            metadata={"batch_kind": "skill_mutation", "resource_files": {}, "existed_before_batch": True},
        )


async def _snapshot_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    async with session_factory() as session:
        return len((await session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == BATCH_ID))).scalars().all())


@contextmanager
def _live_skill_files() -> Iterator[None]:
    """Stand-ins for the skill files only; the database, the version store and the write orchestrator are real."""
    live = mbs._SkillLiveState(skill_id=SKILL_ID, skill_md=MD_LIVE, resources={}, skill_existed=True)
    with (
        patch.object(mbs, "_capture_live_state", AsyncMock(return_value=live)),
        patch("app.services.skills.write_orchestrator._read_current_text", AsyncMock(return_value=MD_LIVE)),
        patch("app.services.skill_optimization.skill_version_sync.sync_content_to_disk", AsyncMock(return_value=True)),
        patch("app.core.skills.config_version.bump_skill_config_version"),
        patch("app.core.skills.replace.state.clear_last_replace_batch_id", AsyncMock()),
    ):
        yield


@pytest.mark.asyncio
async def test_rollback_consumes_the_snapshot_after_the_restore_committed_version_rows(
    engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession], storage: SQLAlchemyStorage
) -> None:
    await _seed_snapshot(session_factory)

    with _live_skill_files():
        # Default session (expire_on_commit=True), like any caller that is not the app's own session factory.
        async with AsyncSession(engine) as request_session:
            restored = await rollback_skill_mutation_batch(request_session, BATCH_ID)
            await request_session.commit()

    assert restored == 1
    assert await _snapshot_count(session_factory) == 0
    active = await storage.get_active_version(SKILL_ID)
    assert active is not None
    assert active.content == MD_BEFORE
    assert active.created_by == "mutation_rollback"


@pytest.mark.asyncio
async def test_failed_restore_keeps_the_snapshot_so_the_undo_can_be_retried(
    session_factory: async_sessionmaker[AsyncSession], storage: SQLAlchemyStorage
) -> None:
    await _seed_snapshot(session_factory)

    with (
        _live_skill_files(),
        patch.object(mbs, "_apply_row_snapshot", AsyncMock(side_effect=MutationBatchRollbackError("disk full"))),
    ):
        async with session_factory() as request_session:
            with pytest.raises(MutationBatchRollbackError):
                await rollback_skill_mutation_batch(request_session, BATCH_ID)
            await request_session.rollback()

    assert await _snapshot_count(session_factory) == 1
