"""Exact-identifier recall answers only what the caller may read, in the state the memory is in now.

The identifier index only locates candidates. A mock cannot show what a stream hands to ranking, so each
case drives a real manager over SQLite and an embedded Qdrant and reads the exact-identifier stream the
search pipeline consumes, then the end-to-end search.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryStatus, MemoryType, SemanticMemory

NewManager = Callable[..., MemoryManager]

OWNER = ["conv:owner"]
GUEST = ["conv:guest"]
SHARED = ["team:shared"]


async def remember(manager: MemoryManager, content: str) -> SemanticMemory:
    stored = await manager.store(SemanticMemory(content=content, importance=0.5), _bypass_approval=True)
    assert isinstance(stored, SemanticMemory)
    return stored


async def exact_stream(manager: MemoryManager, query: str, limit: int = 5) -> list[MemorySearchResult]:
    """What the pipeline's exact-identifier stream hands to ranking, after its own status filter."""
    service = manager._search_service
    hits = await service._search_exact_stream(service._fts5_searcher, query, limit, None, None)
    return service._filter_results(hits)


async def exact_contents(manager: MemoryManager, query: str, limit: int = 5) -> list[str]:
    return [hit.memory.content for hit in await exact_stream(manager, query, limit)]


async def searched_contents(manager: MemoryManager, query: str, limit: int = 5) -> list[str]:
    results = await manager.search(query, memory_types=[MemoryType.SEMANTIC], limit=limit, track_access=False)
    return [result.memory.content for result in results]


async def test_an_identifier_never_recalls_another_namespaces_memory(new_manager: NewManager) -> None:
    owner, guest = new_manager(OWNER), new_manager(GUEST)
    await remember(owner, "Owner private: database at 10.1.1.3:8003")
    own = "Guest sandbox: box at 10.1.1.200:7777"
    await remember(guest, own)

    assert await exact_contents(guest, "10.1.1.3:8003") == [own]
    assert await searched_contents(guest, "10.1.1.3:8003") == [own]


async def test_a_namespace_set_that_reads_nothing_recalls_nothing(new_manager: NewManager) -> None:
    owner = new_manager(OWNER)
    await remember(owner, "Owner private: database at 10.1.1.3:8003")

    assert await owner._relational.search_fts5("10.1.1.3:8003", 5, None, None, namespaces=[]) == []


async def test_the_precise_identifier_outranks_memories_sharing_its_subnet(new_manager: NewManager) -> None:
    owner = new_manager(OWNER)
    for index in range(30):
        await remember(owner, f"Owner private: service {index} at 10.1.1.{index}:80{index:02d}")
    target = "Owner private: service 29 at 10.1.1.29:8029"

    assert (await exact_contents(owner, "10.1.1.29:8029"))[0] == target
    assert target in await searched_contents(owner, "10.1.1.29:8029")


async def test_a_shared_namespace_is_recalled_and_a_sibling_agents_private_one_is_not(new_manager: NewManager) -> None:
    publisher = new_manager(SHARED)
    agent_b = new_manager([*SHARED, "agent:b"])
    agent_c = new_manager([*SHARED, "agent:c"])
    outsider = new_manager(GUEST)
    shared = "Team shared: wiki at 10.9.9.9:8000"
    await remember(publisher, shared)
    await remember(agent_c, "Agent C private: box at 10.9.9.10:8001")

    assert await exact_contents(agent_b, "10.9.9.9:8000") == [shared]
    assert await exact_contents(agent_b, "10.9.9.10:8001") == [shared]
    assert await exact_contents(outsider, "10.9.9.9:8000") == []


async def test_an_archived_memory_is_not_recalled_until_it_is_restored(new_manager: NewManager) -> None:
    manager = new_manager(OWNER)
    fact = await remember(manager, "Staging box at 10.7.0.5:8080")

    await manager.update_memory(fact.id, status=MemoryStatus.ARCHIVED)
    assert await exact_contents(manager, "10.7.0.5:8080") == []

    await manager.update_memory(fact.id, status=MemoryStatus.ACTIVE)
    assert await exact_contents(manager, "10.7.0.5:8080") == [fact.content]


async def test_a_hit_carries_the_stored_memory_not_one_built_from_the_index(new_manager: NewManager) -> None:
    manager = new_manager(OWNER)
    fact = await remember(manager, "Staging box at 10.7.0.5:8080")
    stored = await manager.get_memory(fact.id)
    assert stored is not None

    (hit,) = await exact_stream(manager, "10.7.0.5:8080")

    assert hit.memory.created_at == stored.created_at
    assert hit.memory.status == stored.status
    assert hit.memory.scope == stored.scope


async def test_a_content_update_is_what_the_identifier_stream_serves(new_manager: NewManager) -> None:
    manager = new_manager(OWNER)
    fact = await remember(manager, "Staging box at 10.7.0.5:8080")

    await manager.update_memory(fact.id, content="Staging box moved to 10.7.0.9:9090")

    assert await exact_contents(manager, "10.7.0.9:9090") == ["Staging box moved to 10.7.0.9:9090"]


async def test_an_index_row_whose_memory_is_gone_is_not_served(new_manager: NewManager) -> None:
    manager = new_manager(OWNER)
    orphan = await remember(manager, "Orphan box at 10.8.8.8:1111")
    await manager._vector.delete(manager._config.semantic_collection, [orphan.id])

    assert await exact_contents(manager, "10.8.8.8:1111") == []
