"""Tests for /api/checkpoint file-snapshot store selection.

Verifies the API reads the same store as SnapshotInterceptor (factory-based,
ShadowGit preferred) instead of hardcoding the local fallback store, which
previously made interceptor-created snapshots invisible in Git environments.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock, patch

import pytest

checkpoint_router_module = import_module("app.api.checkpoint.router")


@pytest.fixture(autouse=True)
def _reset_store():
    saved = checkpoint_router_module._file_snapshot_store
    checkpoint_router_module._file_snapshot_store = None
    yield
    checkpoint_router_module._file_snapshot_store = saved


@pytest.mark.asyncio
async def test_get_file_snapshot_store_uses_shared_factory() -> None:
    """The store comes from create_file_snapshot_store(), not the local fallback."""
    mock_store = AsyncMock()
    with patch(
        "myrm_agent_harness.agent.file_snapshot.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ) as mock_factory:
        store = await checkpoint_router_module._get_file_snapshot_store()

    assert store is mock_store
    mock_factory.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_file_snapshot_store_caches_instance() -> None:
    """Second call reuses the cached store instance."""
    mock_store = AsyncMock()
    with patch(
        "myrm_agent_harness.agent.file_snapshot.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ) as mock_factory:
        await checkpoint_router_module._get_file_snapshot_store()
        await checkpoint_router_module._get_file_snapshot_store()

    mock_factory.assert_awaited_once()

