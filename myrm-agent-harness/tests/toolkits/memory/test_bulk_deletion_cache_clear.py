"""``delete_all`` empties the embedding cache whether the cache's ``clear`` is async or sync.

The cache protocol declares ``async def clear``; a cache whose ``clear`` is a plain function
(or one that fails) must neither leave an un-awaited coroutine behind nor abort the deletion.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager


def _manager(
    memory_config: MemoryConfig,
    mock_vector_store: AsyncMock,
    mock_relational_store: AsyncMock,
    mock_embedding: AsyncMock,
    cache: MagicMock,
) -> MemoryManager:
    mock_relational_store.delete_all.return_value = 0
    mock_vector_store.delete_by_filter.return_value = 0
    return MemoryManager(
        memory_config,
        user_id="test_user",
        vector=mock_vector_store,
        relational=mock_relational_store,
        embedding=mock_embedding,
        cache=cache,
        auto_warmup=False,
    )


class TestDeleteAllClearsEmbeddingCache:
    @pytest.mark.asyncio
    async def test_async_clear_is_awaited(
        self, memory_config, mock_vector_store, mock_relational_store, mock_embedding
    ) -> None:
        cache = MagicMock()
        cache.clear = AsyncMock()

        await _manager(memory_config, mock_vector_store, mock_relational_store, mock_embedding, cache).delete_all()

        cache.clear.assert_awaited_once_with()

    @pytest.mark.asyncio
    async def test_sync_clear_is_called(
        self, memory_config, mock_vector_store, mock_relational_store, mock_embedding
    ) -> None:
        cache = MagicMock()
        cache.clear = MagicMock(return_value=None)

        await _manager(memory_config, mock_vector_store, mock_relational_store, mock_embedding, cache).delete_all()

        cache.clear.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_failing_clear_does_not_abort_the_deletion(
        self, memory_config, mock_vector_store, mock_relational_store, mock_embedding
    ) -> None:
        cache = MagicMock()
        cache.clear = AsyncMock(side_effect=RuntimeError("cache backend down"))

        counts = await _manager(
            memory_config, mock_vector_store, mock_relational_store, mock_embedding, cache
        ).delete_all()

        assert counts["relational"] == 0
        cache.clear.assert_awaited_once_with()
