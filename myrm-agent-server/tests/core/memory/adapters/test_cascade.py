"""The cascade manager deletes chat-derived memories whatever embedding model wrote them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.vector.base import VectorDocument

from app.core.memory import get_cascade_memory_manager

_MODELS = ("cascade-test-model-a", "cascade-test-model-b")


@pytest_asyncio.fixture
async def written_by_two_models() -> AsyncIterator[tuple[str, list[str]]]:
    """One memory of a chat in the semantic collection of each of two embedding models."""
    manager = await get_cascade_memory_manager()
    chat_id = f"chat-{uuid4().hex}"
    collections = [f"memory_semantic_{model}" for model in _MODELS]
    for collection in collections:
        await manager._vector.upsert(  # type: ignore[union-attr]
            collection,
            [
                VectorDocument(
                    id=str(uuid4()),
                    content="a memory of the chat",
                    vector=[0.1, 0.2, 0.3],
                    metadata={"source_chat_id": chat_id},
                )
            ],
        )
    try:
        yield chat_id, collections
    finally:
        for collection in collections:
            if await manager._vector.collection_exists(collection):  # type: ignore[union-attr]
                await manager._vector.delete_by_filter(collection, {"source_chat_id": chat_id})  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_purge_removes_the_chats_memories_from_every_models_collection(
    written_by_two_models: tuple[str, list[str]],
) -> None:
    chat_id, collections = written_by_two_models
    manager = await get_cascade_memory_manager()

    preview = await manager.count_by_source_chat_id(chat_id)
    purged = await manager.purge_by_source_chat_id(chat_id)

    assert preview["semantic"] == 2
    assert purged["semantic"] == 2
    # Each collection held only this chat's memory, so purging empties them and they are retired.
    for collection in collections:
        assert not await manager._vector.collection_exists(collection)  # type: ignore[union-attr]
