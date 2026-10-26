"""Keyword-mode listing of a memory type that was never written answers empty.

An embeddings-less deployment creates each ``{collection}_bm25`` mirror on its first
write, so writing one type leaves the other types without a mirror. Listing those used
to raise ``Collection ... not found`` as soon as any mirror existed, which the memory
list endpoints surfaced as HTTP 500.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemoryType, SemanticMemory


@pytest.mark.slow
class TestListUnwrittenTypeWithoutEmbedding:
    @pytest.mark.asyncio
    async def test_listing_an_unwritten_episodic_type_is_empty(self, tmp_path: Path) -> None:
        manager = await create_local_memory_manager(tmp_path / "mem", None)
        try:
            await manager.store(SemanticMemory(id=str(uuid4()), user_id="sandbox_user", content="用户偏好中文回复"))

            assert len(await manager.list_memories(MemoryType.SEMANTIC, limit=10)) == 1
            assert await manager.list_memories(MemoryType.EPISODIC, limit=10) == []
        finally:
            await manager.close()

    @pytest.mark.asyncio
    async def test_listing_an_unwritten_semantic_type_is_empty(self, tmp_path: Path) -> None:
        manager = await create_local_memory_manager(tmp_path / "mem", None)
        try:
            await manager.store(
                EpisodicMemory(id=str(uuid4()), user_id="sandbox_user", content="今天部署了新版本", event_type="note")
            )

            assert len(await manager.list_memories(MemoryType.EPISODIC, limit=10)) == 1
            assert await manager.list_memories(MemoryType.SEMANTIC, limit=10) == []
        finally:
            await manager.close()
