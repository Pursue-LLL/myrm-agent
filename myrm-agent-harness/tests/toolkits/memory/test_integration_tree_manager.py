"""IntegrationTreeManager unit tests against a real SQLiteGraphStore.

Covers tree removal: ``delete_subgraph`` drops one node with its edges, so ``remove_tree`` has to take the provider,
account, category and leaf nodes down explicitly or their titles and account labels stay in the graph after the user
deleted the tree.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.memory.graph import SQLiteGraphStore
from myrm_agent_harness.toolkits.memory.integration.tree_manager import IntegrationTreeManager
from myrm_agent_harness.toolkits.memory.integration.types import IntegrationTree
from myrm_agent_harness.toolkits.memory.types import IntegrationMemory


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SQLiteGraphStore]:
    s = SQLiteGraphStore(str(tmp_path / "integration_tree.db"))
    yield s
    await s.close()


def _memory(memory_id: str, *, provider: str, source_type: str) -> IntegrationMemory:
    return IntegrationMemory(
        id=memory_id,
        content=f"body of {memory_id}",
        provider=provider,
        account_key="account@example.com",
        account_label="Account",
        source_type=source_type,
        title=f"title of {memory_id}",
        user_id="u",
    )


async def _build_tree(manager: IntegrationTreeManager, provider: str, leaf_prefix: str) -> IntegrationTree:
    tree = await manager.get_or_create_tree(provider, account_key="account@example.com", account_label="Account")
    for index, source_type in enumerate(("email", "email", "doc")):
        await manager.attach_leaf(tree, _memory(f"{leaf_prefix}-{index}", provider=provider, source_type=source_type))
    return tree


async def _node_ids(manager: IntegrationTreeManager, tree: IntegrationTree) -> set[str]:
    return {tree.id, *(node.id for node in await manager.get_tree_structure(tree.id))}


async def test_remove_tree_deletes_every_node_of_the_tree(store: SQLiteGraphStore) -> None:
    manager = IntegrationTreeManager(store)
    doomed = await _build_tree(manager, "mcp:doomed", "d")
    kept = await _build_tree(manager, "mcp:kept", "k")
    doomed_ids = await _node_ids(manager, doomed)
    kept_ids = await _node_ids(manager, kept)
    # root + provider + account + two categories + three leaves
    assert len(doomed_ids) == 8

    deleted = await manager.remove_tree(doomed.id)

    assert deleted >= len(doomed_ids)
    assert [await store.get_node(node_id) for node_id in doomed_ids] == [None] * len(doomed_ids)
    assert all([await store.get_node(node_id) is not None for node_id in kept_ids])
    assert manager.list_trees(provider="mcp:doomed") == []
    assert [tree.id for tree in manager.list_trees(provider="mcp:kept")] == [kept.id]


async def test_remove_tree_leaves_no_leaf_metadata_behind(store: SQLiteGraphStore) -> None:
    manager = IntegrationTreeManager(store)
    tree = await _build_tree(manager, "mcp:doomed", "d")

    await manager.remove_tree(tree.id)

    remaining = await store.list_nodes(limit=100)
    assert remaining == []
