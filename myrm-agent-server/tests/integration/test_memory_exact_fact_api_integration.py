"""The exact-fact lifecycle through the memory CRUD and approval services, on a real local memory stack.

[INPUT] app.services.memory.operations.crud.list_write::{create_memory, update_memory, search_memories, list_memories_paginated, delete_memory_by_id}; app.services.memory.operations.pending_review::approve_pending; harness create_local_memory_manager (real SQLite + embedded Qdrant sparse mirror)
[OUTPUT] exact-fact fields of the API item across create, reload, edit, lock toggle, approval, search and delete
[POS] Pins the contract the WebUI and API clients see for a memory that carries an identifier: the flag and identifiers survive a reload, follow an edit, can be toggled by the user, are stamped when the user approves a queued proposal, and leave the lookup on delete.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores

from app.schemas.memory.crud import CreateMemoryRequest, MemoryItem, UpdateMemoryRequest
from app.services.memory.operations.crud.list_write import (
    create_memory,
    delete_memory_by_id,
    list_memories_paginated,
    search_memories,
    update_memory,
)
from app.services.memory.operations.pending_review import PendingReviewSource, approve_pending

pytestmark = pytest.mark.integration

ENDPOINT = "10.1.1.29:8029"
MOVED_ENDPOINT = "10.2.2.2:9000"
PLAIN_SENTENCE = "The vault code is four eight one five"


async def _local_manager(tmp_path: Path, *, approval_required: bool) -> AsyncIterator[MemoryManager]:
    await clear_embedded_stores()
    local_manager = await create_local_memory_manager(
        base_path=str(tmp_path / "memory"), embedding_config=None, approval_required=approval_required
    )
    yield local_manager
    await local_manager.close()
    await clear_embedded_stores()


@pytest.fixture
async def manager(tmp_path: Path) -> AsyncIterator[MemoryManager]:
    async for local_manager in _local_manager(tmp_path, approval_required=False):
        yield local_manager


@pytest.fixture
async def gated_manager(tmp_path: Path) -> AsyncIterator[MemoryManager]:
    """A manager whose agent-made saves wait for the user's approval."""
    async for local_manager in _local_manager(tmp_path, approval_required=True):
        yield local_manager


@pytest.fixture
def audit_ledgers() -> Iterator[None]:
    """Approving also writes the review audit trail; its stores are not part of this stack."""
    with (
        patch("app.services.memory.operations.pending_review.record_experience_event", AsyncMock()),
        patch("app.services.memory.operations.pending_review.record_pending_event", AsyncMock()),
    ):
        yield


async def _create(manager: MemoryManager, content: str) -> MemoryItem:
    return await create_memory(CreateMemoryRequest(memory_type="semantic", content=content), manager)


async def _edit(manager: MemoryManager, memory_id: str, **fields: object) -> MemoryItem:
    return await update_memory("semantic", memory_id, UpdateMemoryRequest(**fields), manager)


async def _listed(manager: MemoryManager) -> list[MemoryItem]:
    page = await list_memories_paginated(
        type="semantic",
        search=None,
        tag=None,
        sort_by="created_at",
        sort_order="desc",
        page=1,
        page_size=20,
        manager=manager,
    )
    return page.items


async def _found(manager: MemoryManager, query: str) -> list[MemoryItem]:
    response = await search_memories(query=query, memory_types="semantic", limit=10, session_id=None, manager=manager)
    return response.results


@pytest.mark.asyncio
async def test_a_created_memory_with_an_identifier_is_an_exact_fact_after_a_reload(manager: MemoryManager) -> None:
    created = await _create(manager, f"The staging database listens on {ENDPOINT}")

    assert created.is_exact_fact is True
    assert created.exact_identifiers == [ENDPOINT]

    (reloaded,) = await _listed(manager)
    assert reloaded.id == created.id
    assert reloaded.is_exact_fact is True
    assert reloaded.exact_identifiers == [ENDPOINT]


@pytest.mark.asyncio
async def test_a_memory_without_an_identifier_is_not_an_exact_fact(manager: MemoryManager) -> None:
    created = await _create(manager, "The team prefers short stand-ups on Monday mornings")

    assert created.is_exact_fact is False
    assert created.exact_identifiers == []


@pytest.mark.asyncio
async def test_an_identifier_finds_its_memory_first(manager: MemoryManager) -> None:
    await _create(manager, "The staging database is shared by every team in the data group")
    target = await _create(manager, f"The staging database listens on {ENDPOINT}")

    found = await _found(manager, f"what is {ENDPOINT}")

    assert found
    assert found[0].id == target.id


@pytest.mark.asyncio
async def test_an_edit_moves_the_identifier_to_the_new_text(manager: MemoryManager) -> None:
    created = await _create(manager, f"The staging database listens on {ENDPOINT}")

    updated = await _edit(manager, created.id, content=f"The staging database moved to {MOVED_ENDPOINT}")

    assert updated.exact_identifiers == [MOVED_ENDPOINT]
    (reloaded,) = await _listed(manager)
    assert reloaded.exact_identifiers == [MOVED_ENDPOINT]
    assert [item.id for item in await _found(manager, MOVED_ENDPOINT)] == [created.id]


@pytest.mark.asyncio
async def test_a_deleted_memory_is_no_longer_found_by_its_identifier(manager: MemoryManager) -> None:
    created = await _create(manager, f"The staging database listens on {ENDPOINT}")
    assert [item.id for item in await _found(manager, ENDPOINT)] == [created.id]

    await delete_memory_by_id(memory_id=created.id, memory_type="semantic", permanent=True, manager=manager)

    assert await _found(manager, ENDPOINT) == []


@pytest.mark.asyncio
async def test_the_user_can_lock_and_release_a_plain_sentence(manager: MemoryManager) -> None:
    created = await _create(manager, PLAIN_SENTENCE)
    assert created.is_exact_fact is False

    locked = await _edit(manager, created.id, is_exact_fact=True)
    assert locked.is_exact_fact is True
    assert (await _listed(manager))[0].is_exact_fact is True

    released = await _edit(manager, created.id, is_exact_fact=False)
    assert released.is_exact_fact is False
    assert released.exact_identifiers == []
    assert (await _listed(manager))[0].is_exact_fact is False


@pytest.mark.usefixtures("audit_ledgers")
@pytest.mark.asyncio
async def test_an_approved_proposal_becomes_a_findable_exact_fact(gated_manager: MemoryManager) -> None:
    await gated_manager.add_knowledge(f"The staging database listens on {ENDPOINT}", honor_approval=True)
    (proposal,) = await gated_manager.list_pending()
    assert await _listed(gated_manager) == []

    assert await approve_pending(gated_manager, proposal.id, source=PendingReviewSource.WEB_API) is True

    (stored,) = await _listed(gated_manager)
    assert stored.is_exact_fact is True
    assert stored.exact_identifiers == [ENDPOINT]
    assert [item.id for item in await _found(gated_manager, ENDPOINT)] == [stored.id]


@pytest.mark.usefixtures("audit_ledgers")
@pytest.mark.asyncio
async def test_an_approval_with_edited_text_is_stamped_from_the_edited_text(gated_manager: MemoryManager) -> None:
    await gated_manager.add_knowledge(f"The staging database listens on {ENDPOINT}", honor_approval=True)
    (proposal,) = await gated_manager.list_pending()

    await approve_pending(
        gated_manager,
        proposal.id,
        source=PendingReviewSource.WEB_API,
        edited_content=f"The staging database moved to {MOVED_ENDPOINT}",
    )

    (stored,) = await _listed(gated_manager)
    assert stored.exact_identifiers == [MOVED_ENDPOINT]
