"""Keyword-mode (embeddings-less) lifecycle through the memory CRUD services.

The WebUI creates and clears memories through these service functions; without an
embedding backend the memories live in the BM25 sparse mirror, so the type gates
must follow the manager's enabled types and ``delete_all_memories`` must reach the
mirror instead of reporting success while nothing was deleted.

A real manager over an embedded Qdrant runs the whole storage path; only the
operation ledger write is patched out (it needs a request-scoped DB session).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import MemoryType

from app.schemas.memory.crud import CreateMemoryRequest
from app.services.memory.operations.crud.list_write import create_memory, delete_all_memories

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def keyword_manager(tmp_path: Path):
    """A real embeddings-less manager: semantic/episodic memories live in the sparse mirror."""
    manager = await create_local_memory_manager(tmp_path / "memory", None)
    try:
        yield manager
    finally:
        await manager.close()


@pytest.fixture(autouse=True)
def _skip_ledger():
    """The ledger write needs a request-scoped DB session this service-level test has not."""
    with patch(
        "app.services.memory.operations.crud.list_write._record_memory_event",
        new=AsyncMock(),
    ):
        yield


async def test_create_memory_accepts_knowledge_and_event_without_embedding(keyword_manager) -> None:
    """Manual creation must not gate on dense capability: the mirror accepts both types."""
    knowledge = await create_memory(
        CreateMemoryRequest(memory_type="semantic", content="关键词模式校验：TypeScript strict"),
        manager=keyword_manager,
    )
    event = await create_memory(
        CreateMemoryRequest(memory_type="episodic", content="关键词模式校验：重试风暴复盘"),
        manager=keyword_manager,
    )

    assert knowledge.content == "关键词模式校验：TypeScript strict"
    assert event.content == "关键词模式校验：重试风暴复盘"
    assert await keyword_manager.count_memories(MemoryType.SEMANTIC) == 1
    assert await keyword_manager.count_memories(MemoryType.EPISODIC) == 1
    hits = await keyword_manager.search("TypeScript", limit=5)
    assert [h.memory.id for h in hits] == [knowledge.id]


async def test_delete_all_memories_clears_the_mirror(keyword_manager) -> None:
    """The WebUI's clear-all must erase the mirror, not report success on a no-op."""
    for index in range(2):
        await create_memory(
            CreateMemoryRequest(memory_type="semantic", content=f"清空校验 {index}：TypeScript strict"),
            manager=keyword_manager,
        )

    result = await delete_all_memories(memory_type=None, manager=keyword_manager)

    assert result["deleted_count"] == 2
    assert await keyword_manager.count_memories(MemoryType.SEMANTIC) == 0
    assert await keyword_manager.search("TypeScript", limit=5) == []


async def test_delete_all_memories_by_type_clears_only_that_type(keyword_manager) -> None:
    """Deleting one type through the API reaches the mirror and leaves the other type alone."""
    await create_memory(
        CreateMemoryRequest(memory_type="semantic", content=f"类型清空校验：TypeScript {uuid4().hex}"),
        manager=keyword_manager,
    )
    await create_memory(
        CreateMemoryRequest(memory_type="episodic", content=f"类型清空校验：重试风暴 {uuid4().hex}"),
        manager=keyword_manager,
    )

    result = await delete_all_memories(memory_type="semantic", manager=keyword_manager)

    assert result["deleted_count"] == 1
    assert await keyword_manager.count_memories(MemoryType.SEMANTIC) == 0
    assert await keyword_manager.count_memories(MemoryType.EPISODIC) == 1
