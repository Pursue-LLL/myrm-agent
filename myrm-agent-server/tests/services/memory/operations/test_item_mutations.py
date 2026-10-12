"""Protection semantics of the shared single-item memory mutation service."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType

from app.schemas.memory.crud import UpdateMemoryRequest
from app.services.memory.operations.crud.item_mutations import update_memory_item

EVENT_PATCH = "app.services.memory.operations.crud.item_mutations._record_memory_event"


def _memory(*, pinned: bool) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id="mem-1",
        content="edited",
        importance=0.5,
        tags=[],
        status="active",
        pinned=pinned,
        created_at=now,
        updated_at=now,
    )


def _manager() -> AsyncMock:
    manager = AsyncMock()
    manager.update_memory.return_value = _memory(pinned=False)
    manager.pin_memory.return_value = _memory(pinned=True)
    return manager


@pytest.mark.asyncio
@pytest.mark.parametrize("mem_type", [MemoryType.SEMANTIC, MemoryType.EPISODIC])
@pytest.mark.parametrize(
    "body", [UpdateMemoryRequest(content="edited", is_user_locked=True), UpdateMemoryRequest(is_user_locked=True)]
)
async def test_explicit_lock_pins_vector_memory(mem_type, body):
    manager = _manager()

    with patch(EVENT_PATCH, new_callable=AsyncMock):
        await update_memory_item(manager, mem_type, "mem-1", body)

    manager.pin_memory.assert_awaited_once_with("mem-1")
    assert manager.update_memory.await_args.kwargs["is_user_locked"] is None


@pytest.mark.asyncio
async def test_response_reflects_the_pinned_state_not_the_pre_pin_snapshot():
    manager = _manager()

    with patch(EVENT_PATCH, new_callable=AsyncMock):
        item = await update_memory_item(
            manager, MemoryType.SEMANTIC, "mem-1", UpdateMemoryRequest(content="edited", is_user_locked=True)
        )

    assert item.is_user_locked is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        UpdateMemoryRequest(content="edited"),
        UpdateMemoryRequest(tags=["work"]),
        UpdateMemoryRequest(content="edited", is_user_locked=False),
    ],
)
async def test_vector_memory_is_not_pinned_without_an_explicit_lock(body):
    manager = _manager()

    with patch(EVENT_PATCH, new_callable=AsyncMock):
        await update_memory_item(manager, MemoryType.SEMANTIC, "mem-1", body)

    manager.pin_memory.assert_not_awaited()


@pytest.mark.asyncio
async def test_procedural_edit_locks_through_the_rule_flag_not_pin():
    manager = _manager()

    with patch(EVENT_PATCH, new_callable=AsyncMock):
        await update_memory_item(manager, MemoryType.PROCEDURAL, "mem-1", UpdateMemoryRequest(content="edited"))

    assert manager.update_memory.await_args.kwargs["is_user_locked"] is True
    manager.pin_memory.assert_not_awaited()
