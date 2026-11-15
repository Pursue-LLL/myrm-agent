"""Integration: the user's media selection + a provider key → the media tools in the tools list; no selection → none."""

from __future__ import annotations

from app.ai_agents.agents import ImageGenerationParams, TTSParams, VideoGenerationParams
from app.ai_agents.general_agent.agent import GeneralAgent
from app.ai_agents.general_agent.tool_setup import ToolSetupMixin
from app.core.types import ModelConfig
from app.services.agent.params.media import _extract_media_generation_params

_IMAGE_MODEL = "gpt-image-2.6-sunburst"
_VIDEO = {"provider": "volcengine", "model": "seedance-2-0"}
_TTS = {"ttsProvider": "openai", "ttsModel": "gpt-4o-mini-tts", "ttsVoice": "alloy"}


def _tool_names(items: list[object]) -> set[str]:
    return {name for tool in items if (name := getattr(tool, "name", None))}


def _providers(*provider_ids: str, key: str = "sk-test") -> dict[str, object]:
    return {
        "providers": [
            {"id": provider_id, "isEnabled": True, "apiKeys": [{"key": key, "isActive": True}]} for provider_id in provider_ids
        ]
    }


def _mixin() -> ToolSetupMixin:
    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.chat_id = None
    mixin.declared_allowed_roots = ()
    return mixin


def test_image_generation_chain_from_enabled_builtin_tools() -> None:
    """media.py params extraction + tool_setup must produce image_tool (ADM eager mount)."""
    image_params, video_params, tts_params = _extract_media_generation_params(
        {"imageGeneration": {"model": _IMAGE_MODEL}},
        _providers("openai", key="sk-test-image"),
        ["image_generation"],
        None,
    )

    assert image_params is not None
    assert image_params.model == _IMAGE_MODEL
    assert image_params.api_key == "sk-test-image"
    assert video_params is None
    assert tts_params is None

    mixin = _mixin()
    mixin.image_generation_params = image_params
    tools: list[object] = []

    mixin._setup_image_generation_tools(tools)

    assert _tool_names(tools) == {"image_tool"}


def test_a_provider_key_alone_selects_nothing() -> None:
    """Credentials without a pick must not produce a tool: no model, provider or voice is ever assumed."""
    providers = _providers("openai", "volcengine", key="sk-only")

    image_params, video_params, tts_params = _extract_media_generation_params(
        {"imageGeneration": {}, "videoGeneration": {}},
        providers,
        ["image_generation", "video_generation", "tts"],
        {"ttsApiKey": "sk-only"},
    )

    assert (image_params, video_params, tts_params) == (None, None, None)


def test_a_stored_pick_that_left_the_catalog_selects_nothing() -> None:
    """A retired model saved in settings is treated as unselected until the user picks again."""
    image_params, video_params, tts_params = _extract_media_generation_params(
        {
            "imageGeneration": {"model": "dall-e-3", "apiKey": "sk-x"},
            "videoGeneration": {"provider": "openai", "model": "sora", "apiKey": "sk-x"},
        },
        _providers("openai"),
        ["image_generation", "video_generation", "tts"],
        {"ttsProvider": "edge", "ttsModel": "m", "ttsVoice": "v", "ttsApiKey": "sk-x"},
    )

    assert (image_params, video_params, tts_params) == (None, None, None)


def test_an_incomplete_tts_pick_selects_nothing() -> None:
    for incomplete in (
        {"ttsProvider": "openai", "ttsModel": "gpt-4o-mini-tts"},
        {"ttsProvider": "openai", "ttsVoice": "alloy"},
        {"ttsModel": "gpt-4o-mini-tts", "ttsVoice": "alloy"},
    ):
        _, _, tts_params = _extract_media_generation_params(None, _providers("openai"), ["tts"], incomplete)

        assert tts_params is None


def test_adm_media_tools_mount_eager_not_deferred_with_credentials() -> None:
    """ADM: image/video/tts must land in Turn1 tools list (no mock)."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        image_generation_params=ImageGenerationParams(model=_IMAGE_MODEL, api_key="sk-image"),
        video_generation_params=VideoGenerationParams(**_VIDEO, api_key="sk-video"),
        tts_params=TTSParams(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key="sk-tts"),
    )

    tools: list[object] = []
    agent._setup_search_and_basic_tools(tools)

    assert {"image_tool", "video_tool", "tts_generate"} <= _tool_names(tools)


def test_adm_media_tools_absent_without_credentials() -> None:
    """A selection without API key/gateway must not mount a media tool."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        image_generation_params=ImageGenerationParams(model=_IMAGE_MODEL, api_key=None),
        video_generation_params=VideoGenerationParams(**_VIDEO, api_key=None),
        tts_params=TTSParams(provider="openai", model="gpt-4o-mini-tts", voice="alloy", api_key=None),
    )

    tools: list[object] = []
    agent._setup_search_and_basic_tools(tools)

    assert not {"image_tool", "video_tool", "tts_generate"} & _tool_names(tools)


def test_adm_media_tools_absent_without_a_selection() -> None:
    """Default params (nothing selected) mount nothing, even with a key present."""
    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        image_generation_params=ImageGenerationParams(api_key="sk-image"),
        video_generation_params=VideoGenerationParams(api_key="sk-video"),
        tts_params=TTSParams(api_key="sk-tts"),
    )

    tools: list[object] = []
    agent._setup_search_and_basic_tools(tools)

    assert not {"image_tool", "video_tool", "tts_generate"} & _tool_names(tools)


def test_image_gateway_only_chain_mounts_image_tool() -> None:
    """Gateway-only credentials must mount image_tool (backend ADM path)."""
    personal_settings = {
        "imageGeneration": {
            "model": _IMAGE_MODEL,
            "gatewayConfig": {
                "useGateway": True,
                "authToken": "gw-token",
                "gatewayUrl": "https://gateway.example.com",
            },
        }
    }
    image_params, _, _ = _extract_media_generation_params(personal_settings, None, ["image_generation"], None)
    assert image_params is not None

    mixin = _mixin()
    mixin.image_generation_params = image_params
    tools: list[object] = []
    mixin._setup_image_generation_tools(tools)

    assert _tool_names(tools) == {"image_tool"}


def test_video_fallback_only_chain_mounts_video_tool() -> None:
    """A key that exists only for a fallback provider must still mount video_tool."""
    _, video_params, _ = _extract_media_generation_params(
        {
            "videoGeneration": {
                **_VIDEO,
                "fallbackProviders": [{"provider": "gemini", "model": "veo-3.1-fast-generate-preview"}],
            }
        },
        _providers("gemini", key="sk-fallback-only"),
        ["video_generation"],
        None,
    )
    assert video_params is not None
    assert video_params.api_key is None
    assert video_params.fallback_providers[0]["api_key"] == "sk-fallback-only"

    mixin = _mixin()
    mixin.video_generation_params = video_params
    tools: list[object] = []
    mixin._setup_video_generation_tools(tools)

    assert _tool_names(tools) == {"video_tool"}


def test_tts_chain_from_voice_config_mounts_tts_generate() -> None:
    """TTS enabled + a full voice pick + key must mount tts_generate."""
    _, _, tts_params = _extract_media_generation_params(None, None, ["tts"], {**_TTS, "ttsApiKey": "sk-tts-voice"})
    assert tts_params is not None
    assert (tts_params.provider, tts_params.model, tts_params.voice) == ("openai", "gpt-4o-mini-tts", "alloy")
    assert tts_params.api_key == "sk-tts-voice"

    mixin = _mixin()
    mixin.tts_params = tts_params
    tools: list[object] = []
    mixin._setup_tts_tools(tools)

    assert _tool_names(tools) == {"tts_generate"}


def test_media_extraction_skipped_when_tool_not_enabled() -> None:
    """enabled_builtin_tools without media flags must not produce params."""
    image_params, video_params, tts_params = _extract_media_generation_params(
        {
            "imageGeneration": {"model": _IMAGE_MODEL, "apiKey": "sk-x"},
            "videoGeneration": {**_VIDEO, "apiKey": "sk-x"},
        },
        _providers("openai", key="sk-x"),
        ["web_search", "memory"],
        {**_TTS, "ttsApiKey": "sk-tts"},
    )
    assert image_params is None
    assert video_params is None
    assert tts_params is None
