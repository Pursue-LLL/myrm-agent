"""[INPUT]
- app.ai_agents::ImageGenerationParams, TTSParams, VideoGenerationParams (POS: 媒体生成参数契约)
- app.core.media.selection::is_image_model_selected / is_video_selected / is_tts_selected (POS: 用户的选择是否指向引擎能运行的目录项)
- .model_config (POS: providerId 规范化与 API key 查找)

[OUTPUT]
- _extract_media_generation_params / _resolve_xai_oauth_api_key / _is_xai_provider

[POS]
参数转换媒体层：把请求中的 image / video / TTS 选择解析成 provider 可用的生成参数。没有选择、或选择已不在目录内时，对应参数为 None，绝不补默认模型。
"""

from __future__ import annotations

import logging

from app.ai_agents import ImageGenerationParams, TTSParams, VideoGenerationParams
from app.core.media.selection import is_image_model_selected, is_tts_selected, is_video_selected

from .model_config import _find_provider_api_key, _resolve_image_api_key_provider
from .model_config.providers import _parse_camel_dict

logger = logging.getLogger(__name__)

_XAI_PROVIDER_IDS = frozenset({"xai", "x_ai", "x-ai"})


def _resolve_xai_oauth_api_key() -> str | None:
    """Resolve xAI API key from session OAuth credentials (SuperGrok token reuse)."""
    try:
        from myrm_agent_harness.agent.security import user_credentials_ctx

        from app.services.agent.session_credential_assembler import XAI_ISSUER

        for cred in user_credentials_ctx.get():
            if cred.issuer == XAI_ISSUER and cred.token.strip():
                return cred.token
    except Exception:
        pass
    return None


def _is_xai_provider(provider_id: str) -> bool:
    return provider_id.replace("-", "_").lower() in _XAI_PROVIDER_IDS


def _provider_api_key(providers_dict: dict[str, object] | None, provider_id: str) -> str | None:
    """Key of ``provider_id`` from the configured providers, or the xAI session credential for xAI."""
    api_key = _find_provider_api_key(providers_dict, provider_id)
    if not api_key and _is_xai_provider(provider_id):
        api_key = _resolve_xai_oauth_api_key()
    return api_key


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _image_params(
    personal_settings_dict: dict[str, object] | None,
    providers_dict: dict[str, object] | None,
) -> ImageGenerationParams | None:
    raw = personal_settings_dict.get("imageGeneration") if personal_settings_dict else None
    if not isinstance(raw, dict):
        return None
    params = ImageGenerationParams.model_validate(_parse_camel_dict(raw, ImageGenerationParams))
    model = params.model
    if not is_image_model_selected(model):
        return None
    if not params.api_key:
        params.api_key = _provider_api_key(providers_dict, _resolve_image_api_key_provider(model))
    return params


def _video_params(
    personal_settings_dict: dict[str, object] | None,
    providers_dict: dict[str, object] | None,
) -> VideoGenerationParams | None:
    raw = personal_settings_dict.get("videoGeneration") if personal_settings_dict else None
    if not isinstance(raw, dict):
        return None
    params = VideoGenerationParams.model_validate(_parse_camel_dict(raw, VideoGenerationParams))
    provider = params.provider
    if provider is None or not is_video_selected(provider, params.model):
        return None
    if not params.api_key:
        params.api_key = _provider_api_key(providers_dict, provider)
    for fallback in params.fallback_providers:
        fallback_provider = fallback.get("provider")
        if fallback_provider and not fallback.get("api_key"):
            fallback_key = _provider_api_key(providers_dict, fallback_provider)
            if fallback_key:
                fallback["api_key"] = fallback_key
    return params


def _tts_params(
    voice_dict: dict[str, object] | None,
    providers_dict: dict[str, object] | None,
) -> TTSParams | None:
    if not voice_dict:
        return None
    provider = _text(voice_dict.get("ttsProvider"))
    model = _text(voice_dict.get("ttsModel"))
    voice = _text(voice_dict.get("ttsVoice"))
    if provider is None or not is_tts_selected(provider, model, voice):
        return None
    api_key = _text(voice_dict.get("ttsApiKey")) or _provider_api_key(providers_dict, provider)
    return TTSParams(provider=provider, model=model, voice=voice, api_key=api_key)


def _extract_media_generation_params(
    personal_settings_dict: dict[str, object] | None,
    providers_dict: dict[str, object] | None,
    enabled_builtin_tools: list[str],
    voice_dict: dict[str, object] | None = None,
) -> tuple[ImageGenerationParams | None, VideoGenerationParams | None, TTSParams | None]:
    """Image/video/tts generation params of the media tools the agent enables and the user has set up.

    A tool whose model, provider or voice the user has not picked (or no longer exists) comes back as ``None``.
    """
    return (
        _image_params(personal_settings_dict, providers_dict) if "image_generation" in enabled_builtin_tools else None,
        _video_params(personal_settings_dict, providers_dict) if "video_generation" in enabled_builtin_tools else None,
        _tts_params(voice_dict, providers_dict) if "tts" in enabled_builtin_tools else None,
    )
