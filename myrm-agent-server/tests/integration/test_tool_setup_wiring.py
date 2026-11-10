"""Integration tests: tool_setup wiring for migration regression fixes."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.tools import BaseTool

from app.ai_agents.agents import ImageGenerationParams, VideoGenerationParams

if TYPE_CHECKING:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin


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
        "app.ai_agents.general_agent.tool_setup.common._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    tool = tools[0]
    assert isinstance(tool, BaseTool)
    assert tool.name == "image_tool"
    assert len(normalize_tool_names([tool])) == 1


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
        "app.ai_agents.general_agent.tool_setup.common._get_artifact_push_fn",
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
        "app.ai_agents.general_agent.tool_setup.common._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_video_generation_tools(tools)

    assert len(tools) == 1
    tool = tools[0]
    assert isinstance(tool, BaseTool)
    assert tool.name == "video_tool"
    assert len(normalize_tool_names([tool])) == 1


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
        "app.ai_agents.general_agent.tool_setup.common._get_artifact_push_fn",
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

    def _capture_create_cron_tools(manager: object, **kwargs: object) -> list[BaseTool]:
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
        await mixin._setup_cron_tools(tools)

    from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery

    assert captured.get("delivery_resolver") is resolve_cron_delivery
    assert captured.get("blueprint_catalog_provider") is not None
    assert len(tools) == 1


def _browser_mixin(*, agent_security_raw: dict[str, object], allowed_roots: tuple[str, ...] = ()) -> ToolSetupMixin:
    """A tool-setup host as it is before BaseAgent init (``agent`` is still None)."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.agent = None
    mixin.agent_id = "be4e86d3-6b36-4b3c-bed0-a1932103a7a4"
    mixin.approval_session_key = None
    mixin.channel_name = "web_chat"
    mixin.security_config_raw = {}
    mixin.agent_security_raw = agent_security_raw
    mixin.declared_capabilities = ()
    mixin.declared_allowed_roots = allowed_roots
    # Optional host attributes: the browser setup reads them with ``getattr`` and a default, so the mixin declares none.
    for name, value in (
        ("auto_restore_domains", []),
        ("browser_source", None),
        ("dialog_policy", None),
        ("session_recording", None),
    ):
        setattr(mixin, name, value)
    return mixin


async def _browser_session_kwargs(mixin: ToolSetupMixin, chat_id: str, tools: list[object]) -> dict[str, object]:
    """Run the browser tool setup into ``tools`` with the browser itself replaced; the arguments the session got."""
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    captured: dict[str, object] = {}
    mock_session = MagicMock()

    async def _fake_build_captcha_solver(_self: object) -> MagicMock:
        return MagicMock()

    with (
        patch(
            "myrm_agent_harness.toolkits.browser.pool.get_global_browser_pool",
            return_value=MagicMock(),
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
        await mixin._setup_browser_tools(tools, chat_id)
    return captured


@pytest.mark.asyncio
async def test_browser_setup_injects_blocklist_from_agent_security_raw() -> None:
    """Browser tools setup runs before BaseAgent init; blocklist must not depend on self.agent."""
    from myrm_agent_harness.toolkits.browser import DomainAllowlist

    mixin = _browser_mixin(agent_security_raw={"networkBlocklist": ["integration-closure.test"]})
    tools: list[object] = []

    captured = await _browser_session_kwargs(mixin, "chat-blocklist-wiring", tools)

    blocklist = captured.get("domain_blocklist")
    assert isinstance(blocklist, DomainAllowlist)
    assert not blocklist.is_empty
    assert blocklist.is_allowed("integration-closure.test")
    assert captured.get("extension_bridge") is not None
    assert len(tools) == 1


@pytest.mark.asyncio
async def test_browser_setup_gives_the_session_download_support_in_the_chat_workspace(tmp_path: Path) -> None:
    """A chat's browser saves downloads under the workspace the agent works in, judged by the chat's own policy."""
    from myrm_agent_harness.toolkits.browser.session.download import DownloadConfig

    mixin = _browser_mixin(agent_security_raw={}, allowed_roots=(str(tmp_path),))

    captured = await _browser_session_kwargs(mixin, "chat-download-wiring", [])

    download_config = captured.get("download_config")
    assert isinstance(download_config, DownloadConfig)
    assert download_config.downloads_dir == tmp_path.resolve() / ".agent" / "downloads"
    assert download_config.confined_to == tmp_path.resolve()
    assert download_config.admit_page_started is not None
    assert not download_config.downloads_dir.exists()


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
        await mixin._setup_cron_tools(tools)

    assert len(tools) == 1


def test_memory_search_tool_description_excludes_web_corpus() -> None:
    """memory_search_tool description must not advertise a web corpus."""
    from unittest.mock import AsyncMock

    from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools import (
        create_memory_tools,
    )
    from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
        MemorySearchPolicy,
    )
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    config = MemoryConfig(
        embedding_model="test-model",
        collection_prefix="integration_test",
        bm25_top_k=50,
        bm25_max_corpus_size=5000,
    )
    vector = AsyncMock()
    vector.count = AsyncMock(return_value=0)
    vector.scroll = AsyncMock(return_value=([], None))
    vector.search = AsyncMock(return_value=[])
    embedding = AsyncMock()
    embedding.embed = AsyncMock(return_value=[0.1] * 768)
    embedding.dimension = 768

    manager = MemoryManager(config, user_id="test_user", vector=vector, embedding=embedding)
    policy = MemorySearchPolicy(
        allow_wiki=True,
        allow_sessions=True,
    )
    tools = create_memory_tools(manager, search_policy=policy)
    search_tool = next(t for t in tools if t.name == "memory_search_tool")

    assert "corpus=web" not in search_tool.description
    assert "web corpus" not in search_tool.description
    assert "wiki:" in search_tool.description
    assert "sessions:" in search_tool.description
