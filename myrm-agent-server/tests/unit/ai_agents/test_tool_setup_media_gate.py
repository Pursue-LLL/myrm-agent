"""Unit tests for media credential gating in tool_setup."""

from __future__ import annotations

from unittest.mock import patch

from app.ai_agents.agents import ImageGenerationParams, TTSParams, VideoGenerationParams
from app.ai_agents.general_agent.tool_setup import (
    ToolSetupMixin,
    _configured_media_api_key,
    _is_media_credential_configured,
    _media_gateway_configured,
    _video_generation_credential_configured,
)


def test_configured_media_api_key() -> None:
    assert _configured_media_api_key("  key  ") is True
    assert _configured_media_api_key("") is False
    assert _configured_media_api_key(None) is False


def test_media_gateway_configured_snake_case() -> None:
    assert _media_gateway_configured(
        {
            "use_gateway": True,
            "auth_token": "token",
            "gateway_url": "https://gateway.example.com",
        }
    )


def test_media_gateway_configured_camel_case() -> None:
    assert _media_gateway_configured(
        {
            "useGateway": True,
            "authToken": "token",
            "gatewayUrl": "https://gateway.example.com",
        }
    )


def test_media_gateway_rejects_incomplete_config() -> None:
    assert not _media_gateway_configured(None)
    assert not _media_gateway_configured({"use_gateway": False, "auth_token": "t", "gateway_url": "https://g"})
    assert not _media_gateway_configured({"use_gateway": True, "auth_token": "", "gateway_url": "https://g"})


def test_is_media_credential_configured_api_key_or_gateway() -> None:
    assert _is_media_credential_configured("key", None)
    assert _is_media_credential_configured(
        None,
        {"use_gateway": True, "auth_token": "t", "gateway_url": "https://g"},
    )
    assert not _is_media_credential_configured(None, None)


def test_video_generation_credential_from_primary_api_key() -> None:
    params = VideoGenerationParams(provider="openai", model="sora", api_key="primary-key")
    assert _video_generation_credential_configured(params)


def test_video_generation_credential_from_fallback() -> None:
    params = VideoGenerationParams(
        provider="openai",
        model="sora",
        api_key=None,
        fallback_providers=[{"provider": "openai", "model": "sora", "api_key": "fallback-key"}],
    )
    assert _video_generation_credential_configured(params)


def test_video_generation_credential_rejects_empty_fallbacks() -> None:
    params = VideoGenerationParams(provider="openai", model="sora", api_key=None)
    assert not _video_generation_credential_configured(params)


def test_tts_tools_skipped_without_credentials() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.tts_params = TTSParams(api_key=None)
    tools: list[object] = []

    mixin._setup_tts_tools(tools)

    assert tools == []


def test_tts_tools_registered_with_api_key() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.tts_params = TTSParams(api_key="tts-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_tts_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "tts_generate"


def test_image_tools_skipped_without_credentials() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key=None)
    tools: list[object] = []

    mixin._setup_image_generation_tools(tools)

    assert tools == []


def test_image_tools_skipped_when_params_unset() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.image_generation_params = None
    tools: list[object] = []

    mixin._setup_image_generation_tools(tools)

    assert tools == []


def test_image_tools_registered_with_api_key() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key="img-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_image_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "image_tool"


def test_video_tools_skipped_without_credentials() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.video_generation_params = VideoGenerationParams(api_key=None)
    tools: list[object] = []

    mixin._setup_video_generation_tools(tools)

    assert tools == []


def test_video_tools_registered_with_api_key() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.video_generation_params = VideoGenerationParams(api_key="video-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_video_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "video_tool"


def test_tts_tools_skipped_when_params_unset() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.tts_params = None
    tools: list[object] = []

    mixin._setup_tts_tools(tools)

    assert tools == []


def test_video_tools_skipped_when_params_unset() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.video_generation_params = None
    tools: list[object] = []

    mixin._setup_video_generation_tools(tools)

    assert tools == []


def test_video_tools_registered_with_fallback_providers() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.video_generation_params = VideoGenerationParams(
        api_key="video-key",
        fallback_providers=[{"provider": "openai", "model": "sora-2", "api_key": "fb-key"}],
    )
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ):
        mixin._setup_video_generation_tools(tools)

    assert len(tools) == 1
    assert getattr(tools[0], "name", None) == "video_tool"


def test_image_tools_load_failure_is_swallowed() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.image_generation_params = ImageGenerationParams(model="dall-e-3", api_key="img-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ), patch(
        "myrm_agent_harness.toolkits.llms.image.ImageGenerationTools",
        side_effect=RuntimeError("engine init failed"),
    ):
        mixin._setup_image_generation_tools(tools)

    assert tools == []


def test_video_tools_load_failure_is_swallowed() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.video_generation_params = VideoGenerationParams(api_key="video-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ), patch(
        "myrm_agent_harness.toolkits.llms.video.VideoGenerationTools",
        side_effect=RuntimeError("engine init failed"),
    ):
        mixin._setup_video_generation_tools(tools)

    assert tools == []


def test_tts_tools_load_failure_is_swallowed() -> None:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.tts_params = TTSParams(api_key="tts-key")
    tools: list[object] = []

    with patch(
        "app.ai_agents.general_agent.tool_setup._get_artifact_push_fn",
        return_value=None,
    ), patch(
        "app.ai_agents.media_tools.tts_agent_tool.create_tts_tool",
        side_effect=RuntimeError("tts init failed"),
    ):
        mixin._setup_tts_tools(tools)

    assert tools == []
