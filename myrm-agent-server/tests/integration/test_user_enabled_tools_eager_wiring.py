"""Integration: user-enabled builtin tools and bound skills mount Turn1 eager.

Product rule: any switch ON (default or manual) → tools list (Turn1 eager).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.meta_tools.interaction.a2ui_spec import (
    A2UI_REFERENCE_FILENAME,
    get_bundled_reference_content,
)
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
    runtime_only = {t.name for t in registry.get_runtime_tools()}
    assert tool_name in resolved
    assert tool_name not in runtime_only


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
    mixin._setup_search_and_basic_tools(tools)

    assert any(getattr(t, "name", None) == "render_ui_tool" for t in tools)
    assert any(getattr(t, "name", None) == "update_ui_data_tool" for t in tools)

    registry = _register_eager_tools(tools)
    _assert_turn1_eager(registry, "render_ui_tool")
    _assert_turn1_eager(registry, "update_ui_data_tool")


def test_render_ui_seeds_a2ui_reference_when_workspace_present(tmp_path: Path) -> None:
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
    mixin.declared_allowed_roots = (str(tmp_path),)

    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    dest = tmp_path / ".agent" / "docs" / A2UI_REFERENCE_FILENAME
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == get_bundled_reference_content()


def test_render_ui_does_not_seed_when_disabled(tmp_path: Path) -> None:
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
    mixin.skill_ids = []
    mixin.declared_allowed_roots = (str(tmp_path),)

    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    dest = tmp_path / ".agent" / "docs" / A2UI_REFERENCE_FILENAME
    assert not dest.exists()
    assert not any(getattr(t, "name", None) == "render_ui_tool" for t in tools)


def test_render_ui_skips_seed_without_workspace_roots() -> None:
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
    mixin.declared_allowed_roots = ()

    tools: list[object] = []
    mixin._setup_search_and_basic_tools(tools)

    assert any(getattr(t, "name", None) == "render_ui_tool" for t in tools)


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

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        mixin._setup_search_and_basic_tools(tools)

    assert any(getattr(t, "name", None) == "x_search_tool" for t in tools)

    registry = _register_eager_tools(tools)
    _assert_turn1_eager(registry, "x_search_tool")


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
