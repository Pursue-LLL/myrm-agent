"""A candidate waiting in the approval queue can always be approved, identifiers included.

Auto-extraction queues every candidate it distils, so a candidate that cannot be rebuilt on approval
stays in the queue for good and its fact is never learned.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemoryType, SemanticMemory

NewManager = Callable[..., MemoryManager]

PLAIN = "The user prefers concise answers with bullet points"
WITH_IDENTIFIER = "The staging server is reachable at 10.0.0.5:8080 and runs v2.4.1"
WITH_ENV_NAME = "The deploy key lives in the DEPLOY_TOKEN environment variable"


async def searched_contents(manager: MemoryManager, query: str) -> list[str]:
    results = await manager.search(query, memory_types=[MemoryType.SEMANTIC], limit=5, track_access=False)
    return [result.memory.content for result in results]


async def test_every_queued_candidate_is_approved_and_keeps_its_exact_fact_state(new_manager: NewManager) -> None:
    manager = new_manager()
    await manager.store_batch(
        [SemanticMemory(content=text) for text in (PLAIN, WITH_IDENTIFIER, WITH_ENV_NAME)], _force_pending=True
    )
    queued = await manager.list_pending()
    assert len(queued) == 3

    approved = {record.content: await manager.approve(record.id) for record in queued}

    assert await manager.list_pending() == []
    for text in (WITH_IDENTIFIER, WITH_ENV_NAME):
        reloaded = await manager.get_memory(approved[text].id)
        assert reloaded is not None
        assert reloaded.is_exact_fact is True, text
        assert reloaded.is_user_protected is True, text
    assert WITH_IDENTIFIER in await searched_contents(manager, "10.0.0.5:8080")


async def test_a_row_queued_with_identifier_lists_in_its_metadata_is_approved(new_manager: NewManager) -> None:
    manager = new_manager()
    await manager.store_batch([SemanticMemory(content=WITH_IDENTIFIER)], _force_pending=True)
    [queued] = await manager.list_pending()
    stored_metadata = queued.memory_data.get("metadata")
    assert isinstance(stored_metadata, dict)
    identifiers = queued.memory_data["exact_identifiers"]
    # The shape of rows queued while the identifiers were also stamped into the metadata as a list.
    stuck_data = {
        **queued.memory_data,
        "metadata": {**stored_metadata, "is_exact_fact": True, "exact_identifiers": identifiers},
    }
    await manager._relational.submit_pending(queued.model_copy(update={"id": "stuck-row", "memory_data": stuck_data}))

    approved = await manager.approve("stuck-row")

    assert [record.id for record in await manager.list_pending()] == [queued.id]
    reloaded = await manager.get_memory(approved.id)
    assert reloaded is not None
    assert reloaded.is_exact_fact is True
    assert reloaded.exact_identifiers == identifiers
    assert reloaded.metadata.get("exact_identifiers") is None


async def test_an_edited_approval_is_stamped_from_the_edited_text(new_manager: NewManager) -> None:
    manager = new_manager()
    await manager.store_batch([SemanticMemory(content=WITH_IDENTIFIER)], _force_pending=True)
    [queued] = await manager.list_pending()

    approved = await manager.approve(queued.id, edited_content="The staging server moved to 10.2.2.2:9000")

    reloaded = await manager.get_memory(approved.id)
    assert reloaded is not None
    assert reloaded.is_exact_fact is True
    assert reloaded.exact_identifiers == ["10.2.2.2:9000"]
    assert "10.0.0.5:8080" not in await searched_contents(manager, "10.0.0.5:8080")


async def test_an_edit_that_drops_every_identifier_keeps_the_fact_flagged_without_identifiers(
    new_manager: NewManager,
) -> None:
    manager = new_manager()
    await manager.store_batch([SemanticMemory(content=WITH_IDENTIFIER)], _force_pending=True)
    [queued] = await manager.list_pending()

    approved = await manager.approve(queued.id, edited_content="The staging server runs on the shared test network")

    reloaded = await manager.get_memory(approved.id)
    assert reloaded is not None
    assert reloaded.is_exact_fact is True
    assert reloaded.exact_identifiers == []
