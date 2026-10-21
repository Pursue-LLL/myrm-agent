from __future__ import annotations

import logging

from app.ai_agents import ImageGenerationParams, TTSParams, VideoGenerationParams

from .providers import _find_provider_api_key, _parse_camel_dict, _resolve_image_api_key_provider

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


def _extract_media_generation_params(
    personal_settings_dict: dict[str, object] | None,
    providers_dict: dict[str, object] | None,
    enabled_builtin_tools: list[str],
    voice_dict: dict[str, object] | None = None,
) -> tuple[ImageGenerationParams | None, VideoGenerationParams | None, TTSParams | None]:
    """Extract image/video/tts generation params from personalSettings and voice config when enabled by agent config."""
    image_params: ImageGenerationParams | None = None
    video_params: VideoGenerationParams | None = None
    tts_params: TTSParams | None = None

    if "image_generation" in enabled_builtin_tools:
        raw = personal_settings_dict.get("imageGeneration") if personal_settings_dict else None
        if isinstance(raw, dict):
            image_params = ImageGenerationParams.model_validate(_parse_camel_dict(raw, ImageGenerationParams))
        else:
            image_params = ImageGenerationParams()
        if not image_params.api_key:
            target_provider = _resolve_image_api_key_provider(image_params.model)
            image_params.api_key = _find_provider_api_key(providers_dict, target_provider)
            if not image_params.api_key and _is_xai_provider(target_provider):
                image_params.api_key = _resolve_xai_oauth_api_key()

    if "video_generation" in enabled_builtin_tools:
        raw = personal_settings_dict.get("videoGeneration") if personal_settings_dict else None
        if isinstance(raw, dict):
            video_params = VideoGenerationParams.model_validate(_parse_camel_dict(raw, VideoGenerationParams))
        else:
            video_params = VideoGenerationParams()
        if not video_params.api_key:
            video_params.api_key = _find_provider_api_key(providers_dict, video_params.provider)
            if not video_params.api_key and _is_xai_provider(video_params.provider):
                video_params.api_key = _resolve_xai_oauth_api_key()
        for fb in video_params.fallback_providers:
            if isinstance(fb, dict) and not fb.get("api_key"):
                fb_provider = fb.get("provider", "openai")
                fb_key = _find_provider_api_key(providers_dict, str(fb_provider))
                if not fb_key and _is_xai_provider(str(fb_provider)):
                    fb_key = _resolve_xai_oauth_api_key()
                if fb_key:
                    fb["api_key"] = fb_key

    if "tts" in enabled_builtin_tools:
        if voice_dict:
            tts_params = TTSParams(
                provider=str(voice_dict.get("ttsProvider", "openai")),
                model=str(voice_dict.get("ttsModel", "tts-1")),
                voice=str(voice_dict.get("ttsVoice", "alloy")),
                api_key=str(voice_dict.get("ttsApiKey", "")),
            )
        else:
            tts_params = TTSParams()
        if not tts_params.api_key:
            tts_params.api_key = _find_provider_api_key(providers_dict, tts_params.provider)
            if not tts_params.api_key and _is_xai_provider(tts_params.provider):
                tts_params.api_key = _resolve_xai_oauth_api_key()

    return image_params, video_params, tts_params
