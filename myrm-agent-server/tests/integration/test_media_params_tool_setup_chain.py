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
    """ADM: image/video/tts must land in Turn1 tools, never discoverable_tools (no mock)."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        image_generation_params=ImageGenerationParams(model="dall-e-3", api_key="sk-image"),
        video_generation_params=VideoGenerationParams(provider="openai", model="sora", api_key="sk-video"),
        tts_params=TTSParams(api_key="sk-tts"),
    )

    tools: list[object] = []
    discoverable_tools: list[object] = []
    agent._setup_search_and_basic_tools(tools, discoverable_tools)

    eager = _tool_names(tools)
    deferred = _tool_names(discoverable_tools)

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
    discoverable_tools: list[object] = []
    agent._setup_search_and_basic_tools(tools, discoverable_tools)

    all_names = _tool_names(tools) | _tool_names(discoverable_tools)
    assert "image_tool" not in all_names
    assert "video_tool" not in all_names
    assert "tts_generate" not in all_names


def test_image_gateway_only_chain_mounts_image_tool() -> None:
    """Gateway-only credentials must mount image_tool (backend ADM path)."""
    enabled = ["image_generation"]
    personal_settings = {
        "imageGeneration": {
            "model": "dall-e-3",
            "gatewayConfig": {
                "useGateway": True,
                "authToken": "gw-token",
                "gatewayUrl": "https://gateway.example.com",
            },
        }
    }
    image_params, _, _ = _extract_media_generation_params(personal_settings, None, enabled, None)
    assert image_params is not None

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = image_params
    tools: list[object] = []
    mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "image_tool"


def test_video_fallback_only_chain_mounts_video_tool() -> None:
    """Video with fallback-only API key must still mount video_tool."""
    enabled = ["video_generation"]
    providers_dict = {
        "providers": [
            {
                "id": "openai",
                "isEnabled": True,
                "apiKeys": [{"key": "sk-fallback-only", "isActive": True}],
            }
        ]
    }
    _, video_params, _ = _extract_media_generation_params(
        {"videoGeneration": {"provider": "openai", "model": "sora", "fallbackProviders": [{"provider": "openai", "model": "sora"}]}},
        providers_dict,
        enabled,
        None,
    )
    assert video_params is not None
    assert video_params.api_key == "sk-fallback-only"

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.video_generation_params = video_params
    tools: list[object] = []
    mixin._setup_video_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "video_tool"


def test_tts_chain_from_voice_config_mounts_tts_generate() -> None:
    """TTS enabled + voice config api key must mount tts_generate."""
    enabled = ["tts"]
    voice_dict = {
        "ttsProvider": "openai",
        "ttsModel": "tts-1",
        "ttsVoice": "alloy",
        "ttsApiKey": "sk-tts-voice",
    }
    _, _, tts_params = _extract_media_generation_params(None, None, enabled, voice_dict)
    assert tts_params is not None
    assert tts_params.api_key == "sk-tts-voice"

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.tts_params = tts_params
    tools: list[object] = []
    mixin._setup_tts_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "tts_generate"


def test_media_extraction_skipped_when_tool_not_enabled() -> None:
    """enabled_builtin_tools without media flags must not produce params."""
    image_params, video_params, tts_params = _extract_media_generation_params(
        {"imageGeneration": {"model": "dall-e-3", "apiKey": "sk-x"}},
        {"providers": [{"id": "openai", "isEnabled": True, "apiKeys": [{"key": "sk-x", "isActive": True}]}]},
        ["web_search", "memory"],
        {"ttsApiKey": "sk-tts"},
    )
    assert image_params is None
    assert video_params is None
    assert tts_params is None
