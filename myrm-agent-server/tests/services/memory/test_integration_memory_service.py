"""Unit tests for IntegrationMemoryService tree removal (vector + graph cleanup)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.memory.integration_memory import IntegrationMemoryService


@pytest.fixture
def mock_tree_manager():
    """Create a mock IntegrationTreeManager."""
    mgr = MagicMock()
    mgr.remove_tree = AsyncMock(return_value=5)
    return mgr


@pytest.fixture
def mock_vector_store():
    """Create a mock VectorStoreProtocol."""
    vs = AsyncMock()
    vs.delete_by_filter = AsyncMock(return_value=3)
    return vs


@pytest.fixture
def service(mock_tree_manager, mock_vector_store):
    """Create IntegrationMemoryService with mocked dependencies."""
    svc = IntegrationMemoryService.__new__(IntegrationMemoryService)
    svc._tree_manager = mock_tree_manager
    svc._vector_store = mock_vector_store
    svc._fetcher = MagicMock()
    svc._summariser = MagicMock()
    return svc


class TestRemoveTreesByProvider:
    """Tests for remove_trees_by_provider method."""

    @pytest.mark.asyncio
    async def test_no_trees_returns_zero(self, service, mock_tree_manager, mock_vector_store):
        mock_tree_manager.list_trees.return_value = []

        result = await service.remove_trees_by_provider("github")

        assert result == 0
        mock_tree_manager.remove_tree.assert_not_called()
        mock_vector_store.delete_by_filter.assert_not_called()

    @pytest.mark.asyncio
    async def test_removes_all_matching_trees(self, service, mock_tree_manager, mock_vector_store):
        tree1 = MagicMock(id="tree-1")
        tree2 = MagicMock(id="tree-2")
        mock_tree_manager.list_trees.return_value = [tree1, tree2]
        mock_tree_manager.remove_tree = AsyncMock(side_effect=[3, 7])

        result = await service.remove_trees_by_provider("notion")

        assert result == 10
        mock_tree_manager.list_trees.assert_called_once_with(provider="notion")
        assert mock_tree_manager.remove_tree.call_count == 2
        assert mock_vector_store.delete_by_filter.call_count == 2
        mock_vector_store.delete_by_filter.assert_any_call("integration_memory", {"tree_id": "tree-1"})
        mock_vector_store.delete_by_filter.assert_any_call("integration_memory", {"tree_id": "tree-2"})

    @pytest.mark.asyncio
    async def test_single_tree_removed(self, service, mock_tree_manager, mock_vector_store):
        tree = MagicMock(id="tree-only")
        mock_tree_manager.list_trees.return_value = [tree]
        mock_tree_manager.remove_tree = AsyncMock(return_value=12)

        result = await service.remove_trees_by_provider("feishu")

        assert result == 12
        mock_tree_manager.remove_tree.assert_called_once_with("tree-only")
        mock_vector_store.delete_by_filter.assert_called_once_with("integration_memory", {"tree_id": "tree-only"})


class TestRemoveTreesByProviderEdgeCases:
    """Edge case tests for remove_trees_by_provider."""

    @pytest.mark.asyncio
    async def test_partial_failure_still_accumulates(self, service, mock_tree_manager, mock_vector_store):
        """If one tree graph removal raises, the exception propagates."""
        tree1 = MagicMock(id="tree-ok")
        tree2 = MagicMock(id="tree-fail")
        mock_tree_manager.list_trees.return_value = [tree1, tree2]
        mock_tree_manager.remove_tree = AsyncMock(
            side_effect=[5, RuntimeError("graph store error")]
        )

        with pytest.raises(RuntimeError, match="graph store error"):
            await service.remove_trees_by_provider("broken-provider")

    @pytest.mark.asyncio
    async def test_empty_provider_id_searches_correctly(self, service, mock_tree_manager):
        """Empty provider_id passes through to list_trees."""
        mock_tree_manager.list_trees.return_value = []

        result = await service.remove_trees_by_provider("")

        assert result == 0
        mock_tree_manager.list_trees.assert_called_once_with(provider="")


class TestRemoveTree:
    """Tests for remove_tree method — verifies both vector and graph cleanup."""

    @pytest.mark.asyncio
    async def test_cleans_vectors_then_graph(self, service, mock_tree_manager, mock_vector_store):
        mock_tree_manager.remove_tree = AsyncMock(return_value=8)

        result = await service.remove_tree("tree-123")

        assert result == 8
        mock_vector_store.delete_by_filter.assert_called_once_with(
            "integration_memory", {"tree_id": "tree-123"}
        )
        mock_tree_manager.remove_tree.assert_called_once_with("tree-123")

    @pytest.mark.asyncio
    async def test_vector_failure_does_not_block_graph_removal(self, service, mock_tree_manager, mock_vector_store):
        """Vector cleanup failure is logged but graph removal still proceeds."""
        mock_vector_store.delete_by_filter = AsyncMock(side_effect=RuntimeError("vector error"))
        mock_tree_manager.remove_tree = AsyncMock(return_value=4)

        result = await service.remove_tree("tree-resilient")

        assert result == 4
        mock_tree_manager.remove_tree.assert_called_once_with("tree-resilient")


class TestAutoSeedKnowledge:
    """Tests for _auto_seed_knowledge method."""

    @pytest.mark.asyncio
    async def test_empty_new_items_returns_early(self, service):
        """If new_items is empty, should return early."""
        from myrm_agent_harness.toolkits.memory.integration.types import IntegrationSyncResult
        result = IntegrationSyncResult(tree_id="t1", provider="slack", new_items=[])
        await service._auto_seed_knowledge(result)
        # Should not raise or do anything

