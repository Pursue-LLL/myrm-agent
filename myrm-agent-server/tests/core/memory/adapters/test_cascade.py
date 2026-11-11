"""The cascade manager deletes chat-derived memories whatever embedding model or scope wrote them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.context_bundle import ContextBundleFacade
from myrm_agent_harness.toolkits.memory.setup import open_local_graph_store
from myrm_agent_harness.toolkits.vector.base import VectorDocument

from app.config.settings import settings
from app.core.memory import get_cascade_memory_manager

_MODELS = ("cascade-test-model-a", "cascade-test-model-b")
_USER = "sandbox_user"


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


@pytest.mark.asyncio
async def test_purge_reaches_memories_written_under_an_agent_channel_or_project_scope() -> None:
    manager = await get_cascade_memory_manager()
    chat_id = f"chat-{uuid4().hex}"
    collection = f"memory_semantic_{_MODELS[0]}"

    def doc(user_id: str, primary_namespace: str) -> VectorDocument:
        return VectorDocument(
            id=str(uuid4()),
            content="a memory of the chat",
            vector=[0.1, 0.2, 0.3],
            metadata={"source_chat_id": chat_id, "user_id": user_id, "primary_namespace": primary_namespace},
        )

    scoped = [doc(_USER, scope) for scope in ("agent:default", "client:web", "project:demo", "global")]
    another_users = doc("another-user", "agent:default")
    await manager._vector.upsert(collection, [*scoped, another_users])  # type: ignore[union-attr]
    try:
        preview = await manager.count_by_source_chat_id(chat_id)
        purged = await manager.purge_by_source_chat_id(chat_id)

        assert preview["semantic"] == len(scoped)
        assert purged["semantic"] == len(scoped)
        left, _ = await manager._vector.scroll(collection, limit=10, filters={"source_chat_id": chat_id})  # type: ignore[union-attr]
        assert [remaining.id for remaining in left] == [another_users.id]
    finally:
        if await manager._vector.collection_exists(collection):  # type: ignore[union-attr]
            await manager._vector.delete_by_filter(collection, {"source_chat_id": chat_id})  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_the_cascade_manager_opens_the_claim_graph_the_memory_writers_use() -> None:
    manager = await get_cascade_memory_manager()
    memory_path = Path(ContextBundleFacade.from_state_dir(settings.database.state_dir, ensure_layout=False).memory_path())
    writers_graph = open_local_graph_store(memory_path)
    try:
        assert manager._graph is not None
        assert manager._graph._db_path == writers_graph._db_path  # type: ignore[attr-defined]
    finally:
        await writers_graph.close()


@pytest.mark.asyncio
async def test_purge_removes_the_claim_graph_compiled_from_the_chats_digests() -> None:
    manager = await get_cascade_memory_manager()
    graph = manager._graph
    assert graph is not None
    chats = {name: f"chat-{uuid4().hex}" for name in ("deleted", "kept")}
    digests = {name: f"digest-{uuid4().hex}" for name in chats}
    node_ids: list[str] = []
    for name, chat_id in chats.items():
        evidence = await graph.create_node(
            ["Evidence"],
            {"id": f"evidence:{digests[name]}", "source_memory_id": digests[name], "source_chat_id": chat_id},
        )
        claim = await graph.create_node(
            ["Claim"], {"id": f"claim:{digests[name]}", "latest_source_memory_id": digests[name], "evidence_count": 3}
        )
        node_ids += [evidence.id, claim.id]
    try:
        await manager.purge_by_source_chat_id(chats["deleted"])

        assert await graph.find_nodes(["Evidence"], {"source_chat_id": chats["deleted"]}) == []
        assert await graph.find_nodes(["Claim"], {"latest_source_memory_id": digests["deleted"]}) == []
        assert len(await graph.find_nodes(["Evidence"], {"source_chat_id": chats["kept"]})) == 1
        assert len(await graph.find_nodes(["Claim"], {"latest_source_memory_id": digests["kept"]})) == 1
    finally:
        for node_id in node_ids:
            await graph.delete_subgraph(node_id)
