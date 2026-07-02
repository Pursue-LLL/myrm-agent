"""Integration: enabled_builtin_tools + provider key → image_tool in tools list."""

from __future__ import annotations

from app.ai_agents.agents import ImageGenerationParams, TTSParams, VideoGenerationParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
from app.core.types import ModelConfig
from app.services.agent.params.media import _extract_media_generation_params


def _tool_names(items: list[object]) -> set[str]:
    return {name for tool in items if (name := getattr(tool, "name", None))}


def test_image_generation_chain_from_enabled_builtin_tools() -> None:
    """media.py params extraction + tool_setup must produce image_tool (ADM eager mount)."""
    enabled = ["image_generation"]
    providers_dict = {
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "apiKeys": [{"key": "sk-test-image", "isActive": True}],
            }
        ]
    }

    image_params, video_params, tts_params = _extract_media_generation_params(
        None,
        providers_dict,
        enabled,
        None,
    )

    assert image_params is not None
    assert image_params.api_key == "sk-test-image"
    assert video_params is None
    assert tts_params is None

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = image_params
    tools: list[object] = []

    mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "image_tool"


def test_adm_media_tools_mount_eager_not_deferred_with_credentials() -> None:
    """ADM: image/video/tts must land in Turn1 tools, never deferred_tools (no mock)."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        image_generation_params=ImageGenerationParams(model="dall-e-3", api_key="sk-image"),
        video_generation_params=VideoGenerationParams(provider="openai", model="sora", api_key="sk-video"),
        tts_params=TTSParams(api_key="sk-tts"),
    )

    tools: list[object] = []
    deferred_tools: list[object] = []
    agent._setup_search_and_basic_tools(tools, deferred_tools)

    eager = _tool_names(tools)
    deferred = _tool_names(deferred_tools)

    assert {"image_tool", "video_tool", "tts_generate"}.issubset(eager)
    assert not {"image_tool", "video_tool", "tts_generate"} & deferred


def test_adm_media_tools_absent_without_credentials() -> None:
    """No API key/gateway → media tools must not appear in tools or deferred (no mock)."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        image_generation_params=ImageGenerationParams(model="dall-e-3", api_key=None),
        video_generation_params=VideoGenerationParams(provider="openai", model="sora", api_key=None),
        tts_params=TTSParams(api_key=None),
    )

    tools: list[object] = []
    deferred_tools: list[object] = []
    agent._setup_search_and_basic_tools(tools, deferred_tools)

    all_names = _tool_names(tools) | _tool_names(deferred_tools)
    assert "image_tool" not in all_names
    assert "video_tool" not in all_names
    assert "tts_generate" not in all_names
