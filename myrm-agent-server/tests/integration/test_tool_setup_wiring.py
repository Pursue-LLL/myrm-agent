"""Integration tests: tool_setup wiring for migration regression fixes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from app.ai_agents.agents import ImageGenerationParams, VideoGenerationParams


def test_local_browser_setup_method_removed() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    assert not hasattr(ToolSetupMixin, "_setup_local_browser_data_tool")


def test_image_generation_registers_basetool() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
    from myrm_agent_harness.agent.streaming.utils import normalize_tool_names

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key="test-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "image_tool"
    assert isinstance(tools[0], BaseTool)
    assert len(normalize_tool_names(tools)) == 1


def test_image_generation_skipped_without_api_key_or_gateway() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key=None)
    tools: list[object] = []

    mixin._setup_image_generation_tools(tools)

    assert tools == []


def test_image_generation_accepts_gateway_only() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = ImageGenerationParams(
        model="dall-e-3",
        api_key=None,
        gateway_config={
            "use_gateway": True,
            "auth_token": "gw-token",
            "gateway_url": "https://gateway.example.com",
        },
    )
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "image_tool"


def test_video_generation_skipped_without_api_key() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.video_generation_params = VideoGenerationParams(
        provider="openai",
        model="sora",
        api_key=None,
    )
    tools: list[object] = []

    mixin._setup_video_generation_tools(tools)

    assert tools == []


def test_video_generation_registers_basetool() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
    from myrm_agent_harness.agent.streaming.utils import normalize_tool_names

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.video_generation_params = VideoGenerationParams(
        provider="openai",
        model="sora",
        api_key="test-key",
    )
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_video_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "video_tool"
    assert isinstance(tools[0], BaseTool)
    assert len(normalize_tool_names(tools)) == 1


def test_video_generation_accepts_fallback_provider_key_only() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.video_generation_params = VideoGenerationParams(
        provider="openai",
        model="sora",
        api_key=None,
        fallback_providers=[{"provider": "openai", "model": "sora", "api_key": "fallback-only-key"}],
    )
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_video_generation_tools(tools)

    assert len(tools) == 1


@pytest.mark.asyncio
async def test_cron_tools_receive_delivery_resolver() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.model_cfg = MagicMock(model="test-model")
    mixin.chat_id = "chat-1"
    mixin.agent_id = "agent-1"
    mixin.enable_cron_eager = False
    tools: list[object] = []
    discoverable_tools: list[object] = []

    mock_manager = MagicMock()
    captured: dict[str, object] = {}

    def _capture_create_cron_tools(manager, user_id, **kwargs):
        captured["delivery_resolver"] = kwargs.get("delivery_resolver")
        return [MagicMock(name="cron_manage_tool", spec=BaseTool)]

    with (
        patch(
            "myrm_agent_harness.toolkits.create_cron_tools",
            side_effect=_capture_create_cron_tools,
        ),
        patch(
            "app.core.cron.adapters.setup.get_cron_manager",
            return_value=mock_manager,
        ),
        patch(
            "app.core.cron.blueprints.get_blueprints_for_tool_description",
            return_value="",
        ),
    ):
        await mixin._setup_cron_tools(tools, discoverable_tools, user_id="user-1")

    from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery

    assert captured.get("delivery_resolver") is resolve_cron_delivery
    assert len(discoverable_tools) == 1
    assert len(tools) == 0


@pytest.mark.asyncio
async def test_cron_tools_turn1_eager_when_enabled() -> None:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.model_cfg = MagicMock(model="test-model")
    mixin.chat_id = "chat-1"
    mixin.agent_id = "agent-1"
    mixin.enable_cron_eager = True
    tools: list[object] = []
    discoverable_tools: list[object] = []

    with (
        patch(
            "myrm_agent_harness.toolkits.create_cron_tools",
            return_value=[MagicMock(name="cron_manage_tool", spec=BaseTool)],
        ),
        patch(
            "app.core.cron.adapters.setup.get_cron_manager",
            return_value=MagicMock(),
        ),
        patch(
            "app.core.cron.blueprints.get_blueprints_for_tool_description",
            return_value="",
        ),
    ):
        await mixin._setup_cron_tools(tools, discoverable_tools, user_id="user-1")

    assert len(tools) == 1
    assert len(discoverable_tools) == 0
