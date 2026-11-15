"""Unit tests for media tool gating in tool_setup: a tool is mounted only for a real selection with credentials."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from myrm_agent_harness.toolkits.llms.image import ImageGenerationConfig
from myrm_agent_harness.toolkits.llms.tts import TTSConfig
from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig

from app.ai_agents.agents import ImageGenerationParams, TTSParams, VideoGenerationParams
from app.ai_agents.general_agent.tool_setup import (
    ToolSetupMixin,
    _configured_media_api_key,
    _is_media_credential_configured,
    _media_gateway_configured,
    _video_generation_credential_configured,
)

_GATEWAY = {"use_gateway": True, "auth_token": "t", "gateway_url": "https://g"}


def _mixin(**attrs: object) -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.declared_allowed_roots = ()
    for name, value in attrs.items():
        setattr(mixin, name, value)
    return mixin


def _image_tools(**params: object) -> list[object]:
    tools: list[object] = []
    _mixin(image_generation_params=ImageGenerationParams(**params))._setup_image_generation_tools(tools)
    return tools


def _video_tools(**params: object) -> list[object]:
    tools: list[object] = []
    _mixin(video_generation_params=VideoGenerationParams(**params))._setup_video_generation_tools(tools)
    return tools


def _tts_tools(**params: object) -> list[object]:
    tools: list[object] = []
    _mixin(tts_params=TTSParams(**params))._setup_tts_tools(tools)
    return tools


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
    assert _is_media_credential_configured(None, _GATEWAY)
    assert not _is_media_credential_configured(None, None)


def test_video_generation_credential_from_primary_api_key() -> None:
    params = VideoGenerationParams(provider="volcengine", model="seedance-2-0", api_key="primary-key")
    assert _video_generation_credential_configured(params)


def test_video_generation_credential_from_fallback() -> None:
    params = VideoGenerationParams(
        provider="volcengine",
        model="seedance-2-0",
        api_key=None,
        fallback_providers=[{"provider": "gemini", "model": "veo-3.1-fast-generate-preview", "api_key": "fallback-key"}],
    )
    assert _video_generation_credential_configured(params)


def test_video_generation_credential_rejects_empty_fallbacks() -> None:
    params = VideoGenerationParams(provider="volcengine", model="seedance-2-0", api_key=None)
    assert not _video_generation_credential_configured(params)


# --- image ---


def test_image_tool_needs_params_a_selected_model_and_credentials() -> None:
    mixin = _mixin(image_generation_params=None)
    tools: list[object] = []
    mixin._setup_image_generation_tools(tools)

    assert tools == []
    assert _image_tools(api_key="img-key") == []  # nothing selected: no model is assumed
    assert _image_tools(model="gpt-image-2.6-sunburst", api_key=None) == []
    assert _image_tools(model="gpt-image-2.6-sunburst", api_key="   ") == []


@pytest.mark.parametrize("retired", ["dall-e-3", "dall-e-2", "not-a-model"])
def test_image_tool_is_absent_for_a_model_no_longer_in_the_catalog(retired: str) -> None:
    assert _image_tools(model=retired, api_key="img-key") == []


@pytest.mark.parametrize(
    "credentials",
    [{"api_key": "img-key"}, {"gateway_config": _GATEWAY}],
    ids=["api_key", "gateway_only"],
)
def test_image_tool_is_mounted_for_a_selected_model(credentials: dict[str, object]) -> None:
    tools = _image_tools(model="gpt-image-2.6-sunburst", **credentials)

    assert [getattr(tool, "name", None) for tool in tools] == ["image_tool"]


def test_image_fallbacks_outside_the_catalog_are_dropped_and_the_engine_persists_edits() -> None:
    captured: list[ImageGenerationConfig] = []

    def capture(config: ImageGenerationConfig, **_: object) -> object:
        captured.append(config)
        return object()

    with patch("app.ai_agents.media_tools.create_image_generation_tool", side_effect=capture):
        tools = _image_tools(
            model="gpt-image-2.6-sunburst", api_key="img-key", fallback_models=["dall-e-3", "gpt-image-2.6-flare"]
        )

    assert len(tools) == 1
    (config,) = captured
    assert config.fallback_models == ["gpt-image-2.6-flare"]
    assert config.media_callback is not None


def test_image_tool_load_failure_is_swallowed() -> None:
    with patch("app.ai_agents.media_tools.create_image_generation_tool", side_effect=RuntimeError("init failed")):
        assert _image_tools(model="gpt-image-2.6-sunburst", api_key="img-key") == []


# --- video ---


def test_video_tool_needs_params_a_selected_provider_model_and_credentials() -> None:
    mixin = _mixin(video_generation_params=None)
    tools: list[object] = []
    mixin._setup_video_generation_tools(tools)

    assert tools == []
    assert _video_tools(api_key="video-key") == []  # nothing selected: no provider is assumed
    assert _video_tools(provider="volcengine", api_key="video-key") == []
    assert _video_tools(provider="volcengine", model="seedance-2-0", api_key=None) == []


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", "sora"), ("openai", "sora-2"), ("volcengine", "sora"), ("kling", "kling-v2")],
)
def test_video_tool_is_absent_for_a_pair_the_registry_does_not_serve(provider: str, model: str) -> None:
    assert _video_tools(provider=provider, model=model, api_key="video-key") == []


def test_video_tool_is_mounted_for_a_selected_pair() -> None:
    tools = _video_tools(provider="volcengine", model="seedance-2-0", api_key="video-key")

    assert [getattr(tool, "name", None) for tool in tools] == ["video_tool"]


def test_video_tool_is_mounted_when_only_a_fallback_has_a_key() -> None:
    tools = _video_tools(
        provider="volcengine",
        model="seedance-2-0",
        fallback_providers=[{"provider": "gemini", "model": "veo-3.1-fast-generate-preview", "api_key": "fb-key"}],
    )

    assert [getattr(tool, "name", None) for tool in tools] == ["video_tool"]


def test_video_fallbacks_the_registry_does_not_serve_are_dropped() -> None:
    captured: list[VideoGenerationConfig] = []

    def capture(config: VideoGenerationConfig, **_: object) -> object:
        captured.append(config)
        return object()

    with patch("app.ai_agents.media_tools.create_video_generation_tool", side_effect=capture):
        tools = _video_tools(
            provider="volcengine",
            model="seedance-2-0",
            api_key="video-key",
            fallback_providers=[
                {"provider": "openai", "model": "sora-2", "api_key": "x"},
                {"provider": "gemini", "model": "veo-3.1-fast-generate-preview", "api_key": "fb-key"},
            ],
        )

    assert len(tools) == 1
    (config,) = captured
    assert [(fallback.provider, fallback.model) for fallback in config.fallback_configs] == [
        ("gemini", "veo-3.1-fast-generate-preview")
    ]


def test_video_tool_load_failure_is_swallowed() -> None:
    with patch("app.ai_agents.media_tools.create_video_generation_tool", side_effect=RuntimeError("init failed")):
        assert _video_tools(provider="volcengine", model="seedance-2-0", api_key="video-key") == []


# --- tts ---


def test_tts_tool_needs_params_a_full_selection_and_credentials() -> None:
    mixin = _mixin(tts_params=None)
    tools: list[object] = []
    mixin._setup_tts_tools(tools)

    assert tools == []
    assert _tts_tools(api_key="tts-key") == []  # nothing selected: no voice is assumed
    assert _tts_tools(provider="openai", model="gpt-4o-mini-tts", api_key="tts-key") == []
    assert _tts_tools(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key=None) == []


@pytest.mark.parametrize("provider", ["edge", "azure", ""])
def test_tts_tool_is_absent_for_a_provider_the_engine_does_not_call(provider: str) -> None:
    assert _tts_tools(provider=provider, model="m", voice="v", api_key="tts-key") == []


def test_tts_tool_is_mounted_for_a_full_selection() -> None:
    tools = _tts_tools(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key="tts-key")

    assert [getattr(tool, "name", None) for tool in tools] == ["tts_generate"]


def test_tts_engine_gets_the_selection_and_a_persist_callback() -> None:
    captured: list[TTSConfig] = []

    def capture(config: TTSConfig) -> object:
        captured.append(config)
        return object()

    with patch("app.ai_agents.media_tools.create_tts_tool", side_effect=capture):
        _tts_tools(provider="volcengine", model="seed-tts-2.0", voice="zh_female_vv", api_key="tts-key")

    (config,) = captured
    assert (config.provider, config.model, config.voice) == ("volcengine", "seed-tts-2.0", "zh_female_vv")
    assert config.media_callback is not None


def test_tts_tool_load_failure_is_swallowed() -> None:
    with patch("app.ai_agents.media_tools.create_tts_tool", side_effect=RuntimeError("tts init failed")):
        assert _tts_tools(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key="tts-key") == []
