"""Snapshot writes for rollback-eligible batches and the persistent storage accessor."""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.skill_optimization.sqlalchemy_storage import SQLAlchemyStorage
from app.database.models import Base, BatchSnapshot
from app.services.skill_optimization.bootstrap import get_skill_optimization_storage
from app.services.skill_optimization.rollback_service import RollbackService

_METADATA: dict[str, object] = {"batch_kind": "skill_mutation", "resource_files": {}, "existed_before_batch": True}


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_insert_mutation_batch_snapshot_persists_row(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await RollbackService(session).insert_mutation_batch_snapshot(
            batch_id="batch-1",
            skill_id="skill-a",
            skill_content="# before",
            metadata=_METADATA,
        )

    async with session_factory() as session:
        rows = list((await session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == "batch-1"))).scalars())

    assert len(rows) == 1
    assert rows[0].skill_id == "skill-a"
    assert rows[0].skill_content_before == "# before"
    assert rows[0].skill_metadata == _METADATA


@pytest.mark.asyncio
async def test_insert_without_commit_is_discarded_on_session_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The batch hook writes every skill snapshot in one transaction: a failure must leave no partial rows."""
    async with session_factory() as session:
        service = RollbackService(session)
        for skill_id in ("skill-a", "skill-b"):
            await service.insert_mutation_batch_snapshot(
                batch_id="batch-atomic",
                skill_id=skill_id,
                skill_content="# before",
                metadata=_METADATA,
                commit=False,
            )
        await session.rollback()

    async with session_factory() as session:
        rows = list((await session.execute(select(BatchSnapshot).where(BatchSnapshot.batch_id == "batch-atomic"))).scalars())

    assert rows == []


@pytest.mark.asyncio
async def test_storage_accessor_returns_session_backed_sqlalchemy_storage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Snapshot writers open sessions through `_get_session`; only the SQLAlchemy-backed storage provides it."""
    with patch("app.platform_utils.get_session_factory", return_value=session_factory):
        storage = get_skill_optimization_storage()

    assert isinstance(storage, SQLAlchemyStorage)
    async with storage._get_session() as session:
        assert isinstance(session, AsyncSession)
