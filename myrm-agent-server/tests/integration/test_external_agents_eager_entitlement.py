"""Entitlement: external agent delegate mounts Turn1 eager when backends exist."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
async def _reset_chat_runtime_pool_registry() -> None:
    from app.services.external_agents.runtime_pool_registry import (
        get_chat_runtime_pool_registry,
    )

    await get_chat_runtime_pool_registry().close_all()
    yield
    await get_chat_runtime_pool_registry().close_all()


@pytest.mark.asyncio
async def test_delegate_to_agent_mounts_in_tools_not_deferred() -> None:
    from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin

    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = [
        {
            "name": "test-cli",
            "type": "cli",
            "command": "echo",
            "args": [],
        }
    ]
    mixin.chat_id = "chat-1"
    mixin.agent_id = "general"
    mixin.force_delegate_agent = None
    mixin._runtime_pool_scope_id = "chat-1"

    tools: list[object] = []
    deferred_tools: list[object] = []

    mock_pool = MagicMock()
    mock_pool.available_backends = ["test-cli"]
    mock_pool.start_monitoring = AsyncMock()
    mock_tool = MagicMock()
    mock_tool.name = "delegate_to_agent_tool"

    with (
        patch(
            "myrm_agent_harness.toolkits.acp.runtime.pool.RuntimePool",
            return_value=mock_pool,
        ),
        patch(
            "myrm_agent_harness.toolkits.create_delegate_to_agent_tool",
            return_value=mock_tool,
        ),
    ):
        await mixin._do_setup_external_agents(tools, deferred_tools, mount_delegate_tool=True)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "delegate_to_agent_tool"
    assert deferred_tools == []
    mock_pool.start_monitoring.assert_awaited_once()


@pytest.mark.asyncio
async def test_direct_only_skips_delegate_tool_but_keeps_pool() -> None:
    from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin

    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = [
        {
            "name": "test-cli",
            "type": "cli",
            "command": "echo",
            "args": [],
        }
    ]
    mixin.chat_id = "chat-1"
    mixin.agent_id = "builtin-cli_visual"
    mixin.force_delegate_agent = None
    mixin._runtime_pool_scope_id = "chat-1"

    tools: list[object] = []
    deferred_tools: list[object] = []

    mock_pool = MagicMock()
    mock_pool.available_backends = ["test-cli"]
    mock_pool.start_monitoring = AsyncMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.acp.runtime.pool.RuntimePool",
            return_value=mock_pool,
        ),
        patch(
            "myrm_agent_harness.toolkits.create_delegate_to_agent_tool",
        ) as create_tool,
    ):
        await mixin._do_setup_external_agents(tools, deferred_tools, mount_delegate_tool=False)

    assert tools == []
    assert mixin._runtime_pool is not None
    assert mixin._runtime_pool.available_backends == ["test-cli"]
    assert mixin._runtime_pool_from_registry is True
    create_tool.assert_not_called()
    mock_pool.start_monitoring.assert_awaited_once()


def test_should_mount_delegate_tool_matrix() -> None:
    from app.ai_agents.general_agent.external_agents import (
        BUILTIN_CLI_VISUAL_AGENT_ID,
        should_mount_delegate_tool,
    )

    assert should_mount_delegate_tool(agent_id="general", force_delegate_agent=None) is True
    assert should_mount_delegate_tool(agent_id=BUILTIN_CLI_VISUAL_AGENT_ID, force_delegate_agent=None) is False
    assert should_mount_delegate_tool(agent_id="general", force_delegate_agent="claude") is False
