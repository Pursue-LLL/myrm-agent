"""MCP endpoint setup on the boot path builds no MemoryManager.

[INPUT]
- app.api.mcp::setup_mcp_endpoint, shutdown_mcp_endpoint (POS: mounts the /mcp endpoint during startup)

[POS]
Guards the startup budget: the endpoint binds the manager of the token's agent on every
request, so mounting it must not open the vector store, read the retrieval configuration
or probe the embedding backend (a network call that would hold readiness back).
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.mcp import setup_mcp_endpoint, shutdown_mcp_endpoint
from app.services.connect.service import VerifiedConnectToken

_LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


@pytest.fixture
def boot_forbidden_calls() -> Iterator[tuple[AsyncMock, AsyncMock]]:
    """Patch the heavy dependencies so any boot-time use fails the test."""
    create_manager = AsyncMock(side_effect=AssertionError("startup must not build a MemoryManager"))
    load_configs = AsyncMock(side_effect=AssertionError("startup must not load the retrieval configuration"))
    with (
        patch("app.core.memory.adapters.setup.create_memory_manager", create_manager),
        patch("app.services.agent.platform_config.load_platform_retrieval_configs", load_configs),
    ):
        yield create_manager, load_configs


@pytest.mark.asyncio
async def test_setup_mounts_endpoint_without_building_a_memory_manager(
    boot_forbidden_calls: tuple[AsyncMock, AsyncMock],
) -> None:
    create_manager, load_configs = boot_forbidden_calls
    app = FastAPI()

    try:
        await setup_mcp_endpoint(app)

        assert any(getattr(route, "path", None) == "/mcp" for route in app.routes)
        create_manager.assert_not_awaited()
        load_configs.assert_not_awaited()
    finally:
        await shutdown_mcp_endpoint()


@pytest.mark.asyncio
async def test_request_binds_the_token_agents_manager(
    boot_forbidden_calls: tuple[AsyncMock, AsyncMock],
) -> None:
    app = FastAPI()
    service = MagicMock()
    service.resolve_token.return_value = VerifiedConnectToken(profile_id="cursor", agent_id="agent-7")
    agent_manager = AsyncMock(return_value=MagicMock())

    with (
        patch("app.services.connect.get_connect_service", return_value=service),
        patch("app.api.mcp.endpoint._memory_manager_for_agent", agent_manager),
        patch("app.api.mcp.endpoint._wiki_boundary_enabled_for_agent", AsyncMock(return_value=False)),
        patch("app.api.mcp.endpoint._is_desktop_control_enabled_for_agent", AsyncMock(return_value=False)),
    ):
        try:
            await setup_mcp_endpoint(app)
            response = TestClient(app).post(
                "/mcp",
                headers={"Authorization": "Bearer token", "Content-Type": "application/json"},
                json=_LIST_TOOLS,
            )
        finally:
            await shutdown_mcp_endpoint()

    assert response.status_code == 200
    tool_names = {tool["name"] for tool in response.json()["result"]["tools"]}
    assert {"memory_recall", "memory_list", "memory_store", "memory_manage"} <= tool_names
    agent_manager.assert_awaited_once_with("agent-7")
