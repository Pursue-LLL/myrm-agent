"""Command center views must read the approval queue, not the conflict-only ORM table."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord, PendingResolutionAction

from app.database.models.memory import PendingMemory
from app.services.memory.command_center import command_center_pending as pending_views
from tests.services.memory.conftest import SessionFactory


def _record(
    pending_id: str,
    *,
    action: PendingResolutionAction = PendingResolutionAction.STORE,
    target_content: str | None = None,
) -> PendingRecord:
    return PendingRecord(
        id=pending_id,
        memory_type=MemoryType.SEMANTIC,
        content=f"content of {pending_id}",
        memory_data={"confidence": 0.9},
        resolution_action=action,
        target_memory_id="old-1" if target_content else None,
        target_content=target_content,
    )


def _manager(records: list[PendingRecord], *, approval_required: bool = True) -> AsyncMock:
    manager = AsyncMock()
    manager.approval_required = approval_required
    manager.list_pending = AsyncMock(return_value=records)
    manager.count_pending = AsyncMock(return_value=len(records))
    return manager


async def _seed_orm_rows(factory: SessionFactory) -> None:
    async with factory() as db:
        db.add_all(
            [
                PendingMemory(id="conflict-1", memory_type="semantic", content="conflict text", is_conflict=True),
                PendingMemory(id="legacy-1", memory_type="semantic", content="never written today", is_conflict=False),
            ]
        )
        await db.commit()


@pytest.mark.asyncio
async def test_count_is_queue_plus_open_conflicts_only(test_db: SessionFactory) -> None:
    await _seed_orm_rows(test_db)
    async with test_db() as db:
        count = await pending_views.count_pending_review(db, _manager([_record("p-1"), _record("p-2")]))

    assert count == 3  # 2 queued proposals + 1 conflict; the non-conflict ORM row is not a review item


@pytest.mark.asyncio
async def test_count_ignores_queue_when_approval_is_off(test_db: SessionFactory) -> None:
    await _seed_orm_rows(test_db)
    async with test_db() as db:
        count = await pending_views.count_pending_review(db, _manager([_record("p-1")], approval_required=False))

    assert count == 1


@pytest.mark.asyncio
async def test_count_survives_a_queue_read_failure(test_db: SessionFactory) -> None:
    await _seed_orm_rows(test_db)
    manager = _manager([])
    manager.count_pending = AsyncMock(side_effect=RuntimeError("sqlite locked"))
    async with test_db() as db:
        assert await pending_views.count_pending_review(db, manager) == 1


@pytest.mark.asyncio
async def test_candidates_list_queue_first_then_conflicts(test_db: SessionFactory) -> None:
    await _seed_orm_rows(test_db)
    async with test_db() as db:
        candidates = await pending_views.build_candidate_records(db, _manager([_record("p-1")]))

    assert [c.id for c in candidates] == ["p-1", "conflict-1"]
    assert candidates[0].confidence == pytest.approx(0.9)
    assert candidates[0].memory_type == "semantic"


@pytest.mark.asyncio
async def test_candidates_respect_the_limit(test_db: SessionFactory) -> None:
    await _seed_orm_rows(test_db)
    async with test_db() as db:
        candidates = await pending_views.build_candidate_records(db, _manager([_record("p-1"), _record("p-2")]), limit=2)

    assert [c.id for c in candidates] == ["p-1", "p-2"]


@pytest.mark.asyncio
async def test_governance_discloses_the_target_and_has_no_edit_action() -> None:
    correct = _record("p-1", action=PendingResolutionAction.CORRECT, target_content="User uses Python")
    forget = _record("p-2", action=PendingResolutionAction.DELETE, target_content="Lives in Shanghai")

    items = await pending_views.build_pending_governance(_manager([correct, forget]))

    assert [item.target_kind for item in items] == ["pending_memory", "pending_memory"]
    assert all(item.available_actions == ["approve", "reject"] for item in items)
    assert items[0].existing_value == "User uses Python"
    assert items[0].candidate_value == "content of p-1"
    assert items[1].existing_value == "Lives in Shanghai"
    assert items[1].candidate_value == ""


@pytest.mark.asyncio
async def test_timeline_fallback_lists_queued_proposals() -> None:
    events = await pending_views.build_pending_timeline(_manager([_record("p-1")]))

    assert [event.id for event in events] == ["pending:p-1"]
    assert events[0].memory_type == "semantic"
    assert events[0].source == "pending_memory"


@pytest.mark.asyncio
async def test_views_are_empty_when_approval_is_off() -> None:
    manager = _manager([_record("p-1")], approval_required=False)

    assert await pending_views.build_pending_governance(manager) == []
    assert await pending_views.build_pending_timeline(manager) == []
    manager.list_pending.assert_not_awaited()
