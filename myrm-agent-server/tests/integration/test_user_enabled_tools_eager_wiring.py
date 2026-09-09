"""Integration: user-enabled builtin tools and bound skills mount Turn1 eager.

Product rule: any switch ON (default or manual) → tools list (Turn1 eager).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolSource


def _register_eager_tools(tools: list[object]) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool, source=ToolSource.USER)
    return registry


def _assert_turn1_eager(registry: ToolRegistry, tool_name: str) -> None:
    resolved = {t.name for t in registry.resolve()}
    runtime_only = {t.name for t in registry.get_runtime_tools()}
    assert tool_name in resolved
    assert tool_name not in runtime_only


@pytest.mark.asyncio
async def test_computer_use_tools_eager_when_enabled() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    fake_session = SimpleNamespace(_config=SimpleNamespace(image_constraints=SimpleNamespace(max_edge_px=1568)))
    fake_tools = [
        SimpleNamespace(name="desktop_snapshot_tool"),
        SimpleNamespace(name="desktop_interact_tool"),
        SimpleNamespace(name="desktop_vision_tool"),
    ]

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.model_cfg = MagicMock(model="claude-opus-4", api_key="k", base_url="http://localhost")
    mixin.declared_allowed_roots = ("/tmp/workspace",)

    tools: list[object] = []

    with (
        patch("app.config.deploy_mode.is_local_mode", return_value=True),
        patch("app.config.deploy_mode.is_sandbox", return_value=False),
        patch(
            "myrm_agent_harness.toolkits.computer_use.create_desktop_session",
            return_value=fake_session,
        ) as create_session,
        patch(
            "myrm_agent_harness.toolkits.computer_use.create_desktop_tools",
            return_value=fake_tools,
        ),
    ):
        mixin._setup_computer_use_tools(tools)

    assert tools == fake_tools
    create_session.assert_called_once()
    assert create_session.call_args.kwargs.get("permission_callback") is not None

    registry = _register_eager_tools(tools)
    _assert_turn1_eager(registry, "desktop_snapshot_tool")
    _assert_turn1_eager(registry, "desktop_interact_tool")
    _assert_turn1_eager(registry, "desktop_vision_tool")
