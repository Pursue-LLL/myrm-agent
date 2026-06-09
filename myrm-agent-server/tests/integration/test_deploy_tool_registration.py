"""Integration test: deploy tool registration in the agent factory.

Verifies that _setup_deploy_tools() correctly creates the tool
and adds it to deferred_tools without mocking the harness imports.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_deploy_tool_registers_into_deferred_tools():
    """_setup_deploy_tools must add exactly 1 tool named 'deploy_artifact' to deferred_tools."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)

    deferred_tools: list = []

    with patch(
        "app.platform_utils.workspace_root.get_workspace_root",
        return_value="/tmp/test_workspace",
    ):
        mixin._setup_deploy_tools(deferred_tools)

    assert len(deferred_tools) == 1
    assert deferred_tools[0].name == "deploy_artifact"


def test_deploy_tool_is_async():
    """The deploy_artifact tool must be async (coroutine function)."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)

    deferred_tools: list = []

    with patch(
        "app.platform_utils.workspace_root.get_workspace_root",
        return_value="/tmp/test_workspace",
    ):
        mixin._setup_deploy_tools(deferred_tools)

    tool = deferred_tools[0]
    assert tool.coroutine is not None, "deploy_artifact must be an async tool"


def test_deploy_backend_is_protocol_compliant():
    """AgentDeployService must satisfy DeployBackend Protocol at integration level."""
    from myrm_agent_harness.toolkits.deploy.deploy_agent_tools import DeployBackend

    from app.services.deploy.agent_deploy_service import AgentDeployService

    svc = AgentDeployService(workspace_root="/tmp/test")
    assert isinstance(svc, DeployBackend)


def test_deploy_tool_graceful_degradation():
    """If AgentDeployService constructor raises, _setup_deploy_tools logs warning and skips."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)

    deferred_tools: list = []

    with patch(
        "app.services.deploy.agent_deploy_service.AgentDeployService",
        side_effect=RuntimeError("simulated init failure"),
    ):
        mixin._setup_deploy_tools(deferred_tools)

    assert len(deferred_tools) == 0
