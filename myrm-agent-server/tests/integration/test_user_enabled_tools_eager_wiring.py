"""Integration: user-enabled builtin tools and bound skills mount Turn1 eager.

Product rule: any switch ON (default or manual) → tools list, not discoverable_tools.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.tool_management.registry import ToolRegistry
from myrm_agent_harness.agent.tool_management.types import ToolSource
from app.core.skills.oauth_availability import X_LIVE_SEARCH_SKILL_ID


def _register_eager_tools(tools: list[object]) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool, source=ToolSource.USER)
    return registry


def _assert_turn1_eager(registry: ToolRegistry, tool_name: str) -> None:
    resolved = {t.name for t in registry.resolve()}
    deferred = {t.name for t in registry.get_discoverable_tools()}
    assert tool_name in resolved
    assert tool_name not in deferred


def test_render_ui_eager_when_enabled() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.enable_web_search = False
    mixin.search_service_cfg = None
    mixin.reranker_config = None
    mixin.enable_advanced_retrieval = False
    mixin.embedding_config = None
    mixin.fetch_raw_webpage = False
    mixin.enable_render_ui = True
    mixin.image_generation_params = None
    mixin.video_generation_params = None
    mixin.tts_params = None
    mixin.search_depth = "normal"
    mixin.model_cfg = MagicMock(model="test-model", api_key="k", base_url="http://localhost")
    mixin.skill_ids = []

    tools: list[object] = []
    discoverable_tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools, discoverable_tools)

    assert any(getattr(t, "name", None) == "render_ui_tool" for t in tools)
    assert not any(getattr(t, "name", None) == "render_ui_tool" for t in discoverable_tools)

    registry = _register_eager_tools(tools)
    _assert_turn1_eager(registry, "render_ui_tool")


def test_x_search_tool_eager_when_skill_bound() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.enable_web_search = False
    mixin.search_service_cfg = None
    mixin.reranker_config = None
    mixin.enable_advanced_retrieval = False
    mixin.embedding_config = None
    mixin.fetch_raw_webpage = False
    mixin.enable_render_ui = False
    mixin.image_generation_params = None
    mixin.video_generation_params = None
    mixin.tts_params = None
    mixin.search_depth = "normal"
    mixin.model_cfg = MagicMock(model="test-model", api_key="k", base_url="http://localhost")
    mixin.skill_ids = [X_LIVE_SEARCH_SKILL_ID]

    tools: list[object] = []
    discoverable_tools: list[object] = []

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        mixin._setup_search_and_basic_tools(tools, discoverable_tools)

    assert any(getattr(t, "name", None) == "x_search_tool" for t in tools)
    assert not any(getattr(t, "name", None) == "x_search_tool" for t in discoverable_tools)

    registry = _register_eager_tools(tools)
    _assert_turn1_eager(registry, "x_search_tool")


def test_canvas_tools_eager_when_enabled_and_bound() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    fake_tools = [
        SimpleNamespace(name="canvas_get_state"),
        SimpleNamespace(name="canvas_insert_element"),
    ]
    stub = SimpleNamespace(
        enable_canvas=True,
        canvas_id="12345678-1234-1234-1234-123456789abc",
    )
    stub._setup_canvas_tools = ToolSetupMixin._setup_canvas_tools.__get__(stub)

    tools: list[object] = []
    with patch(
        "app.services.canvas.canvas_agent_tools.create_canvas_tools",
        return_value=fake_tools,
    ):
        stub._setup_canvas_tools(tools)

    assert len(tools) == 2
    registry = _register_eager_tools(tools)
    for tool in fake_tools:
        _assert_turn1_eager(registry, tool.name)


@pytest.mark.asyncio
async def test_computer_use_tools_eager_when_enabled() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    fake_session = SimpleNamespace(_config=SimpleNamespace(image_constraints=SimpleNamespace(max_edge_px=1568)))
    fake_tools = [
        SimpleNamespace(name="desktop_inspect_tool"),
        SimpleNamespace(name="desktop_snapshot_tool"),
    ]

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.model_cfg = MagicMock(model="claude-opus-4", api_key="k", base_url="http://localhost")

    tools: list[object] = []

    with (
        patch(
            "myrm_agent_harness.toolkits.computer_use.create_desktop_session",
            return_value=fake_session,
        ),
        patch(
            "myrm_agent_harness.toolkits.computer_use.create_desktop_tools",
            return_value=fake_tools,
        ),
    ):
        mixin._setup_computer_use_tools(tools)

    assert tools == fake_tools

    registry = _register_eager_tools(tools)
    _assert_turn1_eager(registry, "desktop_inspect_tool")
    _assert_turn1_eager(registry, "desktop_snapshot_tool")
