"""A chat's deletion reaches a memory built from several chats when the keyword mirror is the only store.

Without an embedding backend the memories live in the BM25 mirror alone. The chat links are payload keys the mirror must
carry and filter on exactly like a dense collection, so each case drives the manager ``create_local_memory_manager``
assembles without an embedding.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from myrm_agent_harness.toolkits.memory.setup import create_local_memory_manager
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, SemanticMemory


@pytest.mark.slow
@pytest.mark.asyncio
async def test_purging_one_source_chat_removes_the_memories_derived_from_it(tmp_path: Path) -> None:
    manager = await create_local_memory_manager(tmp_path / "mem", None)
    try:
        first, second = f"chat-{uuid4().hex}", f"chat-{uuid4().hex}"
        merged = SemanticMemory(
            id=str(uuid4()),
            user_id="sandbox_user",
            content="谱系校验：TypeScript strict",
            source_chat_id=first,
            source_chat_ids=[first, second],
        )
        episode = EpisodicMemory(
            id=str(uuid4()),
            user_id="sandbox_user",
            content="谱系校验：重试风暴复盘",
            source_chat_id=first,
            source_chat_ids=[first, second],
        )
        unrelated = SemanticMemory(id=str(uuid4()), user_id="sandbox_user", content="谱系校验：Vitest 优先")
        await manager.store_batch([merged, episode, unrelated])

        assert await manager.count_by_source_chat_id(second) == {"semantic": 1, "episodic": 1}

        purged = await manager.purge_by_source_chat_id(second)

        assert (purged["semantic"], purged["episodic"]) == (1, 1)
        assert await manager.count_by_source_chat_id(first) == {}
        assert await manager.search("TypeScript", limit=5) == []
        assert len(await manager.search("Vitest", limit=5)) == 1
    finally:
        await manager.close()
