"""Batch rollback on the production SQLite transaction policy (WAL file, deferred read / immediate write).

The restore commits skill version rows through sessions of its own while the request session still has to consume
the batch rows. A request session that keeps its read snapshot open across the restore fails its final DELETE with
SQLITE_BUSY_SNAPSHOT ("database is locked", which busy_timeout does not cover): the files were restored but the undo
answered 503. In-memory SQLite shares one connection and cannot show this, so these tests run on a real file.

Two undo requests for one batch (two tabs) overlap the same way: they need separate connections, so they run here too.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.api.skill_optimization.routes import versions as versions_routes
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


async def _seed_snapshot(
    session_factory: async_sessionmaker[AsyncSession], *, content: str = MD_BEFORE, existed_before: bool = True
) -> None:
    async with session_factory() as session:
        await RollbackService(session).insert_mutation_batch_snapshot(
            batch_id=BATCH_ID,
            skill_id=SKILL_ID,
            skill_content=content,
            metadata={"batch_kind": "skill_mutation", "resource_files": {}, "existed_before_batch": existed_before},
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


@dataclass
class _CreatedSkill:
    """The skill a batch created, standing in for the skill files (the database and the version store stay real)."""

    exists: bool = True


_CAPTURE_SEC = 0.2


@contextmanager
def _created_skill_files(skill: _CreatedSkill) -> Iterator[None]:
    async def capture(skill_id: str, _resource_paths: set[str]) -> mbs._SkillLiveState:
        state = mbs._SkillLiveState(
            skill_id=skill_id, skill_md=MD_LIVE if skill.exists else None, resources={}, skill_existed=skill.exists
        )
        # Reading the live skill takes real time; that is what lets a second undo start before the first one is done.
        await asyncio.sleep(_CAPTURE_SEC)
        return state

    async def remove_created(_skill_id: str) -> bool:
        removed, skill.exists = skill.exists, False
        return removed

    async def read_current_text(_skill_id: str, _filename: str) -> str | None:
        return MD_LIVE if skill.exists else None

    async def sync_to_disk(_skill_id: str, _content: str, *, disk_path: Path | None = None) -> bool:
        return skill.exists  # a removed skill has no SKILL.md path to sync to

    with (
        patch.object(mbs, "_capture_live_state", capture),
        patch.object(mbs, "_delete_skill_created_in_batch", remove_created),
        patch("app.services.skills.write_orchestrator._read_current_text", read_current_text),
        patch("app.services.skill_optimization.skill_version_sync.sync_content_to_disk", sync_to_disk),
        patch("app.core.skills.config_version.bump_skill_config_version"),
        patch("app.core.skills.replace.state.clear_last_replace_batch_id", AsyncMock()),
    ):
        yield


async def _undo_through_the_route(session_factory: async_sessionmaker[AsyncSession]) -> tuple[int, str]:
    """One undo request as the route serves it: its own session, a commit on success, an HTTP error otherwise."""
    async with session_factory() as db:
        try:
            await versions_routes.rollback_skill_mutation_batch_route(BATCH_ID, db)
        except HTTPException as error:
            detail = error.detail
            assert isinstance(detail, dict)
            return error.status_code, str(detail["code"])
    return 200, "rolled_back"


@pytest.mark.asyncio
async def test_concurrent_undos_of_a_created_skill_batch_leave_one_winner_and_no_trace_of_the_other(
    session_factory: async_sessionmaker[AsyncSession], storage: SQLAlchemyStorage
) -> None:
    """Two tabs undoing one batch: the second must answer "already undone", not "rollback failed".

    Unserialized, the second request captures the live skill before the first one removed it, fails on a skill that
    is already gone, and "compensates" by writing its stale capture back as a version of that removed skill.
    """
    await _seed_snapshot(session_factory, content="", existed_before=False)
    skill = _CreatedSkill()

    with _created_skill_files(skill):
        outcomes = await asyncio.gather(_undo_through_the_route(session_factory), _undo_through_the_route(session_factory))

    assert sorted(outcomes) == [(200, "rolled_back"), (409, "batch_already_consumed")]
    assert not skill.exists
    assert await _snapshot_count(session_factory) == 0
    assert await storage.get_active_version(SKILL_ID) is None
