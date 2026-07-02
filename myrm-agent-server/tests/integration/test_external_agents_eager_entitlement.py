"""Entitlement: external agent delegate mounts Turn1 eager when backends exist."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_delegate_to_agent_mounts_in_tools_not_deferred() -> None:
    from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin

    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin.external_agents_config = [
        {
            "name": "test-cli",
            "backendType": "cli",
            "command": "echo",
            "args": [],
        }
    ]
    mixin.chat_id = "chat-1"

    tools: list[object] = []
    deferred_tools: list[object] = []

    mock_pool = MagicMock()
    mock_pool.available_backends = ["test-cli"]
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
        await mixin._do_setup_external_agents(tools, deferred_tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "delegate_to_agent_tool"
    assert deferred_tools == []
