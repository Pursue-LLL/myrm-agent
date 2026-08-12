"""Tests for /api/checkpoint file-snapshot store selection.

Verifies the API reads the same store as SnapshotInterceptor (factory-based,
ShadowGit preferred) instead of hardcoding the local fallback store, which
previously made interceptor-created snapshots invisible in Git environments.
"""

from __future__ import annotations

from importlib import import_module
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

checkpoint_router_module = import_module("app.api.checkpoint.router")

app = build_minimal_app("checkpoint")


@pytest.fixture(autouse=True)
def _reset_store():
    saved = checkpoint_router_module._file_snapshot_store
    checkpoint_router_module._file_snapshot_store = None
    yield
    checkpoint_router_module._file_snapshot_store = saved


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


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


@pytest.mark.asyncio
async def test_create_file_snapshot_takes_manual_snapshot(
    async_client: httpx.AsyncClient,
) -> None:
    """POST /file-snapshot/create snapshots with MANUAL trigger and returns the id."""
    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(return_value="snap-abc")
    with patch(
        "myrm_agent_harness.agent.file_snapshot.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ):
        response = await async_client.post(
            "/api/v1/checkpoint/file-snapshot/create",
            json={"working_dir": "/ws", "description": "Before refactor"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["snapshot_id"] == "snap-abc"
    assert body["working_dir"] == "/ws"
    mock_store.take_snapshot.assert_awaited_once_with(
        working_dir="/ws",
        trigger=checkpoint_router_module.SnapshotTrigger.MANUAL,
        description="Before refactor",
    )


@pytest.mark.asyncio
async def test_create_file_snapshot_strips_description(
    async_client: httpx.AsyncClient,
) -> None:
    """Leading/trailing whitespace in the description is trimmed before persist."""
    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(return_value="snap-abc")
    with patch(
        "myrm_agent_harness.agent.file_snapshot.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ):
        response = await async_client.post(
            "/api/v1/checkpoint/file-snapshot/create",
            json={"working_dir": "/ws", "description": "  milestone  "},
        )

    assert response.status_code == 200
    mock_store.take_snapshot.assert_awaited_once_with(
        working_dir="/ws",
        trigger=checkpoint_router_module.SnapshotTrigger.MANUAL,
        description="milestone",
    )


@pytest.mark.asyncio
async def test_create_file_snapshot_propagates_store_error(
    async_client: httpx.AsyncClient,
) -> None:
    """A failing store surfaces as a 500 instead of a silent partial success."""
    mock_store = AsyncMock()
    mock_store.take_snapshot = AsyncMock(side_effect=RuntimeError("git failure"))
    with patch(
        "myrm_agent_harness.agent.file_snapshot.create_file_snapshot_store",
        new_callable=AsyncMock,
        return_value=mock_store,
    ):
        response = await async_client.post(
            "/api/v1/checkpoint/file-snapshot/create",
            json={"working_dir": "/ws"},
        )

    assert response.status_code == 500

