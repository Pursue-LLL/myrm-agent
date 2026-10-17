"""A batch cannot be undone while a newer batch still holds a snapshot of one of its skills.

Undoing the older of two batches writes the older content over what the newer one produced (or removes a skill the
newer one edited), and the newer batch's own undo then has nothing true left to restore. The rows are real (in-memory
SQLite) and the rollback service is the production code; only the skill files it would write are stubbed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base, BatchSnapshot
from app.services.skill_optimization.rollback_service import RollbackService
from app.services.skills import mutation_batch_service as mbs
from app.services.skills.mutation_batch_service import MutationBatchSupersededError, rollback_skill_mutation_batch

_METADATA: dict[str, object] = {"batch_kind": "skill_mutation", "resource_files": {}, "existed_before_batch": True}


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def _snapshot(factory: async_sessionmaker[AsyncSession], batch_id: str, *skill_ids: str) -> None:
    """Record one batch the way the skill_manage hook does: one snapshot row per skill, in one commit."""
    async with factory() as session:
        service = RollbackService(session)
        for skill_id in skill_ids:
            await service.insert_mutation_batch_snapshot(
                batch_id=batch_id,
                skill_id=skill_id,
                skill_content=f"{skill_id} before {batch_id}",
                metadata=_METADATA,
                commit=False,
            )
        await session.commit()


@contextmanager
def _skill_files() -> Iterator[AsyncMock]:
    """Stand-ins for the skill files; the returned mock records every snapshot the undo writes back."""
    apply_snapshot = AsyncMock()

    async def _live(skill_id: str, resource_paths: set[str]) -> mbs._SkillLiveState:
        return mbs._SkillLiveState(skill_id=skill_id, skill_md="live", resources={}, skill_existed=True)

    with (
        patch.object(mbs, "_capture_live_state", _live),
        patch.object(mbs, "_apply_row_snapshot", apply_snapshot),
        patch("app.core.skills.config_version.bump_skill_config_version"),
        patch("app.core.skills.replace.state.clear_last_replace_batch_id", AsyncMock()),
    ):
        yield apply_snapshot


async def _undo(factory: async_sessionmaker[AsyncSession], batch_id: str) -> int:
    """Undo a batch the way the route does: the consumed rows are only gone once the request commits."""
    async with factory() as session:
        restored = await rollback_skill_mutation_batch(session, batch_id)
        await session.commit()
    return restored


async def _held_batches(factory: async_sessionmaker[AsyncSession]) -> set[str]:
    async with factory() as session:
        return set((await session.execute(select(BatchSnapshot.batch_id))).scalars().all())


async def test_the_older_batch_is_refused_while_a_newer_batch_holds_the_same_skill(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _snapshot(session_factory, "older", "skill-a")
    await _snapshot(session_factory, "newer", "skill-a")

    with _skill_files() as apply_snapshot:
        with pytest.raises(MutationBatchSupersededError, match=r"skill-a.*newer"):
            await _undo(session_factory, "older")

    apply_snapshot.assert_not_awaited()
    assert await _held_batches(session_factory) == {"older", "newer"}, "the refusal consumed a snapshot"


async def test_a_newer_batch_of_another_skill_does_not_block_the_undo(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _snapshot(session_factory, "older", "skill-a")
    await _snapshot(session_factory, "newer", "skill-b")

    with _skill_files() as apply_snapshot:
        assert await _undo(session_factory, "older") == 1

    assert [call.args[0].skill_id for call in apply_snapshot.await_args_list] == ["skill-a"]
    assert await _held_batches(session_factory) == {"newer"}


async def test_a_batch_over_two_skills_is_refused_whole_when_one_of_them_changed_again(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _snapshot(session_factory, "wide", "skill-a", "skill-b")
    await _snapshot(session_factory, "narrow", "skill-b")

    with _skill_files() as apply_snapshot:
        with pytest.raises(MutationBatchSupersededError, match="skill-b"):
            await _undo(session_factory, "wide")

    apply_snapshot.assert_not_awaited()
    assert await _held_batches(session_factory) == {"wide", "narrow"}


async def test_batches_of_one_skill_are_undone_newest_first(session_factory: async_sessionmaker[AsyncSession]) -> None:
    for batch_id in ("first", "second", "third"):
        await _snapshot(session_factory, batch_id, "skill-a")

    with _skill_files():
        for blocked in ("first", "second"):
            with pytest.raises(MutationBatchSupersededError):
                await _undo(session_factory, blocked)
        for batch_id in ("third", "second", "first"):
            assert await _undo(session_factory, batch_id) == 1

    assert await _held_batches(session_factory) == set()
