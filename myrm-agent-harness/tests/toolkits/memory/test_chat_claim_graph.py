"""Deleting a chat deletes the claims its task digests were compiled into.

Maintenance compiles each task digest into an evidence node and folds it into a claim, and the claim carries the
wording of the digest that updated it last; search recalls claims next to ordinary memories. A purge that stopped at the
digests would leave the chat's words recallable from the graph. Real manager over an embedded Qdrant, SQLite and a
SQLite graph; the digests are compiled by the maintenance functions themselves.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from myrm_agent_harness.toolkits.memory._internal.graph_cascade import drop_chat_claims
from myrm_agent_harness.toolkits.memory._internal.maintenance import (
    _search_claim_graph,
    compile_claim_graph,
    evaporate_task_digests,
    run_forgetting,
)
from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.graph import SQLiteGraphStore
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.protocols.graph import GraphNode
from myrm_agent_harness.toolkits.memory.protocols.vector import VectorDocument
from myrm_agent_harness.toolkits.memory.strategies.chat_fence import close_chat
from myrm_agent_harness.toolkits.memory.strategies.forgetting import ForgettingConfig, ForgettingMode
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemoryLifecycle, SemanticMemory
from tests.support.consolidation_seeds import NewManager

SCOPE = ["agent:x"]


@pytest_asyncio.fixture
async def graph(tmp_path: Path) -> AsyncIterator[SQLiteGraphStore]:
    store = SQLiteGraphStore(str(tmp_path / "graph.db"))
    yield store
    await store.close()


def digest(chat_id: str, title: str, result: str) -> EpisodicMemory:
    """A task digest as the extractor writes it, one per chat."""
    return EpisodicMemory(
        content=f"**Title**: {title}\n**Goal**: {title} for the team\n**Result**: {result}",
        event_type="task_digest",
        importance=0.85,
        source_chat_id=chat_id,
        lifecycle=MemoryLifecycle.new_task_digest(),
    )


async def compile_digests(manager: MemoryManager, graph: SQLiteGraphStore) -> int:
    """Run the two maintenance steps that turn pending digests into evidence and claims."""
    vector = manager._vector
    assert vector is not None
    await evaporate_task_digests(vector, manager._config, namespaces=SCOPE)
    return await compile_claim_graph(vector, graph, manager._config, namespaces=SCOPE)


def nonzero(counts: dict[str, int]) -> dict[str, int]:
    return {kind: count for kind, count in counts.items() if count}


async def evidence_digests(graph: SQLiteGraphStore, chat_id: str) -> list[str]:
    nodes = await graph.find_nodes(["Evidence"], {"source_chat_id": chat_id})
    return [str(node.properties["source_memory_id"]) for node in nodes]


async def claim_titles(graph: SQLiteGraphStore) -> set[str]:
    return {str(node.properties["title"]) for node in await graph.find_nodes(["Claim"], {})}


async def recalled_titles(graph: SQLiteGraphStore, query: str) -> list[str]:
    results = await _search_claim_graph(graph, query=query, current_channel_id=None, namespaces=SCOPE, limit=5)
    return [str(result.memory.title) for result in results]


async def two_chats_worded_one_claim(new_manager: NewManager, graph: SQLiteGraphStore) -> None:
    """Chat A's digest opens the claim, chat B's later digest backs it and becomes its wording."""
    writer = new_manager(SCOPE, graph=graph)
    await writer.store(digest("chat-a", "Weekly report", "draft"), _bypass_approval=True)
    await compile_digests(writer, graph)
    await writer.store(digest("chat-b", "Weekly report", "shipped"), _bypass_approval=True)
    await compile_digests(writer, graph)
    [claim] = await graph.find_nodes(["Claim"], {})
    assert claim.properties["last_result"] == "shipped"
    assert len(await evidence_digests(graph, "chat-a")) == len(await evidence_digests(graph, "chat-b")) == 1


async def test_a_deleted_chat_takes_the_claims_its_digests_produced(
    new_manager: NewManager, graph: SQLiteGraphStore
) -> None:
    writer = new_manager(SCOPE, graph=graph)
    await writer.store(digest("chat-a", "Weekly report", "shipped"), _bypass_approval=True)
    await writer.store(digest("chat-b", "Budget review", "approved"), _bypass_approval=True)
    assert await compile_digests(writer, graph) == 2
    assert await recalled_titles(graph, "weekly report") == ["Weekly report"]

    await new_manager(all_scopes=True, graph=graph).purge_by_source_chat_id("chat-a")

    assert await claim_titles(graph) == {"Budget review"}
    assert await evidence_digests(graph, "chat-a") == []
    assert len(await evidence_digests(graph, "chat-b")) == 1
    assert await recalled_titles(graph, "weekly report") == []


async def test_a_claim_worded_from_the_deleted_chat_goes_though_another_chat_backs_it(
    new_manager: NewManager, graph: SQLiteGraphStore
) -> None:
    await two_chats_worded_one_claim(new_manager, graph)

    await new_manager(all_scopes=True, graph=graph).purge_by_source_chat_id("chat-b")

    assert await graph.find_nodes(["Claim"], {}) == []
    assert await evidence_digests(graph, "chat-b") == []
    assert len(await evidence_digests(graph, "chat-a")) == 1


async def test_a_claim_worded_from_another_chat_keeps_its_wording(
    new_manager: NewManager, graph: SQLiteGraphStore
) -> None:
    await two_chats_worded_one_claim(new_manager, graph)

    await new_manager(all_scopes=True, graph=graph).purge_by_source_chat_id("chat-a")

    [claim] = await graph.find_nodes(["Claim"], {})
    assert claim.properties["last_result"] == "shipped"
    assert await evidence_digests(graph, "chat-a") == []
    assert len(await evidence_digests(graph, "chat-b")) == 1


async def test_a_manager_without_a_graph_still_purges_the_chats_digests(new_manager: NewManager) -> None:
    writer = new_manager(SCOPE)
    await writer.store(digest("chat-a", "Weekly report", "shipped"), _bypass_approval=True)

    purged = await new_manager(all_scopes=True).purge_by_source_chat_id("chat-a")

    assert nonzero(purged) == {"episodic": 1}


async def test_a_manager_that_owns_one_scope_leaves_the_claims_of_another_scope(
    new_manager: NewManager, graph: SQLiteGraphStore
) -> None:
    other_scope = new_manager(["agent:y"], graph=graph)
    await other_scope.store(digest("chat-a", "Weekly report", "shipped"), _bypass_approval=True)
    vector = other_scope._vector
    assert vector is not None
    await evaporate_task_digests(vector, other_scope._config, namespaces=["agent:y"])
    await compile_claim_graph(vector, graph, other_scope._config, namespaces=["agent:y"])

    await new_manager(SCOPE, graph=graph).purge_by_source_chat_id("chat-a")

    assert await claim_titles(graph) == {"Weekly report"}
    assert len(await evidence_digests(graph, "chat-a")) == 1


async def test_a_chat_with_more_evidence_than_one_page_loses_all_of_it(graph: SQLiteGraphStore) -> None:
    for index in range(450):
        await graph.create_node(
            ["Evidence"], {"id": f"evidence:{index}", "source_memory_id": f"d{index}", "source_chat_id": "chat-a"}
        )
        await graph.create_node(
            ["Claim"], {"id": f"claim:{index}", "latest_source_memory_id": f"d{index}", "evidence_count": 3}
        )
    await graph.create_node(["Evidence"], {"id": "evidence:other", "source_memory_id": "x", "source_chat_id": "chat-b"})

    await drop_chat_claims(graph, "chat-a")

    assert await evidence_digests(graph, "chat-a") == []
    assert await graph.find_nodes(["Claim"], {}) == []
    assert await evidence_digests(graph, "chat-b") == ["x"]


async def test_a_failing_graph_is_skipped_so_the_purge_still_deletes_the_memories(
    new_manager: NewManager, graph: SQLiteGraphStore, caplog: pytest.LogCaptureFixture
) -> None:
    await new_manager(SCOPE, graph=graph).store(digest("chat-a", "Weekly report", "shipped"), _bypass_approval=True)
    cascade = new_manager(all_scopes=True, graph=graph)

    with (
        patch.object(graph, "find_nodes", AsyncMock(side_effect=RuntimeError("graph is down"))),
        caplog.at_level(logging.WARNING),
    ):
        purged = await cascade.purge_by_source_chat_id("chat-a")

    assert nonzero(purged) == {"episodic": 1}
    assert "Graph cleanup failed for chat chat-a" in caplog.text


async def test_digests_of_a_chat_being_deleted_are_not_compiled_or_written_back(
    new_manager: NewManager, graph: SQLiteGraphStore
) -> None:
    writer = new_manager(SCOPE, graph=graph)
    stored = await writer.store(digest("chat-a", "Weekly report", "shipped"), _bypass_approval=True)
    vector = writer._vector
    assert vector is not None
    await evaporate_task_digests(vector, writer._config, namespaces=SCOPE)
    close_chat("u1", "chat-a")

    assert await compile_claim_graph(vector, graph, writer._config, namespaces=SCOPE) == 0

    assert await graph.find_nodes(["Claim"], {}) == []
    [stored_doc] = await vector.get(writer._config.episodic_collection, [stored.id])
    assert stored_doc.metadata["claim_graph_state"] == "pending"


async def test_a_chat_deleted_while_digests_are_compiled_is_not_written_back(
    new_manager: NewManager, graph: SQLiteGraphStore
) -> None:
    writer = new_manager(SCOPE, graph=graph)
    first = await writer.store(digest("chat-a", "Weekly report", "shipped"), _bypass_approval=True)
    second = await writer.store(digest("chat-b", "Budget review", "approved"), _bypass_approval=True)
    vector = writer._vector
    assert vector is not None
    await evaporate_task_digests(vector, writer._config, namespaces=SCOPE)
    compile_node = graph.get_or_create_node

    async def delete_both_chats_on_first_node(
        labels: list[str], match_keys: list[str], properties: dict[str, str | int | float | bool]
    ) -> GraphNode:
        close_chat("u1", "chat-a")
        close_chat("u1", "chat-b")
        return await compile_node(labels, match_keys, properties)

    with patch.object(graph, "get_or_create_node", delete_both_chats_on_first_node):
        await compile_claim_graph(vector, graph, writer._config, namespaces=SCOPE)

    states = {
        doc.id: doc.metadata["claim_graph_state"]
        for doc in await vector.get(writer._config.episodic_collection, [first.id, second.id])
    }
    assert states == {first.id: "pending", second.id: "pending"}


async def test_a_chat_deleted_during_the_forgetting_scan_is_not_archived_back() -> None:
    config = MemoryConfig(
        embedding_model="test", forgetting=ForgettingConfig(mode=ForgettingMode.ARCHIVE, max_forget_per_run=10)
    )
    vector = AsyncMock()
    purged = VectorDocument(
        id="doc1",
        content="test",
        metadata={"importance": 0.1, "user_id": "u1", "source_chat_id": "chat-a"},
        embedding=[0.1],
    )
    kept = VectorDocument(
        id="doc2",
        content="test",
        metadata={"importance": 0.1, "user_id": "u1", "source_chat_id": "chat-b"},
        embedding=[0.1],
    )
    vector.scroll.side_effect = [([purged, kept], None), ([], None)]
    close_chat("u1", "chat-a")

    with patch(
        "myrm_agent_harness.toolkits.memory.strategies.forgetting.ForgettingStrategy.select_candidates"
    ) as select:
        select.return_value = [
            (SemanticMemory(id="doc1", content="test", metadata={}), AsyncMock(total_score=0.1)),
            (SemanticMemory(id="doc2", content="test", metadata={}), AsyncMock(total_score=0.1)),
        ]
        result = await run_forgetting(vector, config)

    assert [doc.id for doc in vector.upsert.await_args_list[0].args[1]] == ["doc2"]
    assert result.archived_count == 1
