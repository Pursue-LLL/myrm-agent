"""The recall boundary snapshot over a real local memory stack.

[INPUT] app.services.memory.command_center.command_center_recall_boundary::build_recall_boundary; harness create_local_memory_manager (real SQLite + embedded Qdrant sparse mirror); an in-memory ORM session
[OUTPUT] partition counts, approved sample and candidate pool of a snapshot built from real stored memories
[POS] Pins that the four partitions count each stored memory once, that task digests are shown as session memory and not as evidence, and that queued proposals are the candidates.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import cast

import pytest
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import SemanticMemory
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models.base import Base
from app.database.models.memory import PendingMemory
from app.services.memory.command_center.command_center_recall_boundary import build_recall_boundary

pytestmark = pytest.mark.integration


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[MemoryManager]:
    await clear_embedded_stores()
    local_manager = await create_local_memory_manager(base_path=str(tmp_path / "memory"), embedding_config=None)
    yield local_manager
    await local_manager.close()
    await clear_embedded_stores()


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"sqlite+aiosqlite:///file:rb_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[cast(Table, PendingMemory.__table__)]))
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _store_one_of_each(manager: MemoryManager) -> None:
    await manager.set_profile_attribute("reply_style", "concise")
    await manager.add_knowledge("The team prefers short stand-ups on Monday mornings")
    await manager.add_knowledge("Releases are cut on the first Thursday of the month")
    await manager.add_event("Moved the data pipeline to the new cluster", event_type="user_manual")
    await manager.add_event("Finished migrating the billing reports", event_type="task_digest")
    await manager.add_rule("a pull request is opened", "ask for a review from the owner first")


@pytest.mark.asyncio
async def test_each_stored_memory_is_counted_in_exactly_one_partition(manager: MemoryManager, db: AsyncSession) -> None:
    await _store_one_of_each(manager)

    boundary = await build_recall_boundary(db, manager)

    partitions = boundary.partitions
    assert partitions.identity_count == 1
    assert partitions.session_memory_count == 1  # the task digest
    assert partitions.operating_instructions_count == 1
    assert partitions.retrievable_evidence_count == 3  # two knowledge memories and one event, not the digest
    assert boundary.total_approved == 6


@pytest.mark.asyncio
async def test_the_sample_leaves_a_task_digest_out_of_the_evidence_partition(manager: MemoryManager, db: AsyncSession) -> None:
    await _store_one_of_each(manager)

    boundary = await build_recall_boundary(db, manager)

    sampled = {record.id: record for record in boundary.approved_records}
    assert len(sampled) == len(boundary.approved_records)
    digest_previews = [r for r in boundary.approved_records if "billing reports" in r.content_preview]
    assert [record.partition for record in digest_previews] == ["session_memory"]
    assert {record.partition for record in boundary.approved_records} <= {
        "identity",
        "session_memory",
        "operating_instructions",
        "retrievable_evidence",
    }


@pytest.mark.asyncio
async def test_queued_proposals_are_the_candidates_and_not_approved(manager: MemoryManager, db: AsyncSession) -> None:
    await manager.store_batch([SemanticMemory(content="The user may be moving to Lisbon next year")], _force_pending=True)

    boundary = await build_recall_boundary(db, manager)

    assert boundary.total_candidates == 1
    assert [record.content_preview for record in boundary.candidate_records] == ["The user may be moving to Lisbon next year"]
    assert boundary.total_approved == 0
    assert boundary.approved_records == []
