"""Integration test: deploy tool registration in the agent factory."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_deploy_tool_registers_when_credentials_available():
    """_setup_deploy_tools must add deploy_artifact when credentials exist."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    deferred_tools: list = []

    with (
        patch(
            "app.services.deploy.credentials.has_deploy_credentials",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.platform_utils.workspace_root.get_workspace_root",
            return_value="/tmp/test_workspace",
        ),
    ):
        await mixin._setup_deploy_tools(deferred_tools)

    assert len(deferred_tools) == 1
    assert deferred_tools[0].name == "deploy_artifact"


@pytest.mark.asyncio
async def test_deploy_tool_skipped_without_credentials():
    """_setup_deploy_tools must skip when no Vercel credentials."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    deferred_tools: list = []

    with patch(
        "app.services.deploy.credentials.has_deploy_credentials",
        new=AsyncMock(return_value=False),
    ):
        await mixin._setup_deploy_tools(deferred_tools)

    assert deferred_tools == []


@pytest.mark.asyncio
async def test_deploy_tool_is_async():
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    deferred_tools: list = []

    with (
        patch(
            "app.services.deploy.credentials.has_deploy_credentials",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "app.platform_utils.workspace_root.get_workspace_root",
            return_value="/tmp/test_workspace",
        ),
    ):
        await mixin._setup_deploy_tools(deferred_tools)

    tool = deferred_tools[0]
    assert tool.coroutine is not None


def test_deploy_backend_is_protocol_compliant():
    from app.services.deploy.deploy_agent_tools import DeployBackend
    from app.services.deploy.agent_deploy_service import AgentDeployService

    svc = AgentDeployService(workspace_root="/tmp/test")
    assert isinstance(svc, DeployBackend)


@pytest.mark.asyncio
async def test_deploy_tool_graceful_degradation():
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    deferred_tools: list = []

    with patch(
        "app.services.deploy.agent_deploy_service.AgentDeployService",
        side_effect=RuntimeError("simulated init failure"),
    ), patch(
        "app.services.deploy.credentials.has_deploy_credentials",
        new=AsyncMock(return_value=True),
    ):
        await mixin._setup_deploy_tools(deferred_tools)

    assert len(deferred_tools) == 0
