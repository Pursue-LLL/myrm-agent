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
    from myrm_agent_harness.agent.streaming.utils import normalize_tool_names

    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

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
    from myrm_agent_harness.agent.streaming.utils import normalize_tool_names

    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

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
    """Verify delivery_resolver is passed to create_cron_tools."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.model_cfg = MagicMock(model="test-model")
    mixin.chat_id = "chat-1"
    mixin.agent_id = "agent-1"
    mixin.enable_cron_eager = True
    tools: list[object] = []

    mock_manager = MagicMock()
    captured: dict[str, object] = {}

    def _capture_create_cron_tools(manager, user_id, **kwargs):
        captured["delivery_resolver"] = kwargs.get("delivery_resolver")
        captured["blueprint_catalog_provider"] = kwargs.get("blueprint_catalog_provider")
        captured["default_delivery"] = kwargs.get("default_delivery")
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
        await mixin._setup_cron_tools(tools, user_id="user-1")

    from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery

    assert captured.get("delivery_resolver") is resolve_cron_delivery
    assert captured.get("blueprint_catalog_provider") is not None
    assert len(tools) == 1


@pytest.mark.asyncio
async def test_browser_setup_injects_blocklist_from_agent_security_raw() -> None:
    """Browser tools setup runs before BaseAgent init; blocklist must not depend on self.agent."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.agent = None
    mixin.agent_id = "be4e86d3-6b36-4b3c-bed0-a1932103a7a4"
    mixin.approval_session_key = None
    mixin.channel_name = "web_chat"
    mixin.security_config_raw = {}
    mixin.agent_security_raw = {"networkBlocklist": ["integration-closure.test"]}
    mixin.declared_capabilities = ()
    mixin.declared_allowed_roots = ()
    mixin.auto_restore_domains = []
    mixin.browser_source = None
    mixin.dialog_policy = None
    mixin.session_recording = None
    tools: list[object] = []
    captured: dict[str, object] = {}

    mock_pool = MagicMock()
    mock_session = MagicMock()

    async def _fake_build_captcha_solver(_self: object) -> MagicMock:
        return MagicMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.pool.get_global_browser_pool",
            return_value=mock_pool,
        ),
        patch(
            "app.config.browser.get_browser_pool_config",
            return_value=MagicMock(),
        ),
        patch(
            "app.config.browser.get_browser_launch_options",
            return_value={},
        ),
        patch(
            "app.core.security.browser_vault.get_agent_session_vault",
            return_value=MagicMock(),
        ),
        patch(
            "app.config.deploy_mode.is_local_mode",
            return_value=True,
        ),
        patch(
            "myrm_agent_harness.toolkits.browser.BrowserSession",
            side_effect=lambda *args, **kwargs: captured.update(kwargs) or mock_session,
        ),
        patch(
            "myrm_agent_harness.toolkits.create_browser_tools",
            return_value=[MagicMock(name="browser_navigate_tool", spec=BaseTool)],
        ),
        patch.object(ToolSetupMixin, "_build_captcha_solver", _fake_build_captcha_solver),
    ):
        await mixin._setup_browser_tools(tools, "chat-blocklist-wiring")

    blocklist = captured.get("domain_blocklist")
    assert blocklist is not None
    assert not blocklist.is_empty
    assert blocklist.is_allowed("integration-closure.test")
    assert len(tools) == 1


@pytest.mark.asyncio
async def test_cron_tools_turn1_eager_when_enabled() -> None:
    """Verify cron tools load as Turn1 eager."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.model_cfg = MagicMock(model="test-model")
    mixin.chat_id = "chat-1"
    mixin.agent_id = "agent-1"
    mixin.enable_cron_eager = True
    tools: list[object] = []

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
        await mixin._setup_cron_tools(tools, user_id="user-1")

    assert len(tools) == 1
