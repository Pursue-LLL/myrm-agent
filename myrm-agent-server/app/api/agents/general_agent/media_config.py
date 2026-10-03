"""General Agent API — autonomous decision-making agent with streaming SSE."""

import asyncio
import logging

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from myrm_agent_harness.infra.tls_compat import create_httpx_client
from pydantic import BaseModel, SecretStr
from pydantic.alias_generators import to_camel

from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.services.agent.params.providers import (
    _find_provider_api_key,
    _resolve_image_api_key_provider,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class TestMediaConfigRequest(BaseModel):
    """Request to test media generation configuration connectivity."""

    media_type: str  # "image", "video", or "tts"
    provider: str = "openai"
    model: str = ""

    class Config:
        alias_generator = to_camel
        populate_by_name = True


_IMAGE_PROBE_ENDPOINTS: dict[str, tuple[str, str]] = {
    # provider id -> (models/auth endpoint, auth header template)
    "openai": ("https://api.openai.com/v1/models", "Authorization: Bearer {key}"),
    "gemini": (
        "https://generativelanguage.googleapis.com/v1beta/models",
        "x-goog-api-key: {key}",
    ),
    "together_ai": (
        "https://api.together.xyz/v1/models",
        "Authorization: Bearer {key}",
    ),
    "stability": (
        "https://api.stability.ai/v1/user/account",
        "Authorization: Bearer {key}",
    ),
    "xai": ("https://api.x.ai/v1/models", "Authorization: Bearer {key}"),
}

_TTS_LIGHT_PROBE_ENDPOINTS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1/models", "Authorization: Bearer {key}"),
    "elevenlabs": ("https://api.elevenlabs.io/v1/user", "xi-api-key: {key}"),
}


def _auth_header(template: str, api_key: str) -> dict[str, str]:
    name, _, value = template.partition(": ")
    return {name: value.format(key=api_key)}


async def _probe_endpoint(
    url: str, headers: dict[str, str], timeout: float
) -> tuple[bool, str]:
    """Lightweight credential probe: any 2xx means the key is live.

    Uses the TLS-compat client factory so the probe exercises the same HTTP
    stack as real generation (custom CA bundles would otherwise diverge).
    """
    try:
        async with create_httpx_client(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code < 400:
            return True, "API key is valid"
        if resp.status_code in (401, 403):
            return False, "API key rejected (invalid or revoked)"
        return False, f"Provider returned HTTP {resp.status_code}"
    except httpx.TimeoutException:
        return False, "Connection timed out"
    except Exception as exc:
        logger.warning("Media credential probe failed for %s: %s", url, exc)
        return False, "Connection failed"


async def _probe_volcengine_tts(api_key: str, model: str) -> tuple[bool, str]:
    """Real-synthesis probe: OpenSpeech has no free auth endpoint, so verify a tiny utterance.

    Seed-Audio is generative and slow (120s budget); Doubao-TTS is a fast codec pipeline (20s).
    """
    from myrm_agent_harness.toolkits.llms.tts import AsyncTTSEngine, TTSConfig

    is_seed = "seed" in model.lower()
    probe_text = (
        "请用自然清晰的普通话朗读：「你好。」朗读完毕后自然结束。" if is_seed else "测"
    )
    effective_model = model or ("seed-audio-1.0" if is_seed else "doubao-tts")
    config = TTSConfig(
        provider="volcengine",
        model=effective_model,
        api_key=SecretStr(api_key),
    )
    try:
        result = await AsyncTTSEngine(config).generate(probe_text)
    except Exception as exc:
        return False, str(exc)
    if result.audio_bytes:
        return True, "Speech synthesis successful"
    return False, "Provider returned empty audio"


@router.post("/test-media-config")
@limiter.limit(settings.rate_limit.chat)
async def test_media_config(
    request: TestMediaConfigRequest,
    http_request: Request,
) -> JSONResponse:
    """Test media generation config by verifying API key and provider connectivity."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.utils.response_utils import error_response, success_response

    try:
        configs = await load_user_configs()
        providers_dict = configs.providers_dict
        voice_dict = configs.voice_dict
    except Exception as exc:
        logger.warning("Failed to load user configs for media provider status: %s", exc)
        providers_dict = {}
        voice_dict = {}

    if request.media_type == "image":
        key_provider = _resolve_image_api_key_provider(request.model or "dall-e-3")
        api_key = _find_provider_api_key(providers_dict, key_provider)
        if not api_key:
            return error_response(
                message=f"No API key found for provider '{key_provider}' in your settings"
            )
        probe = _IMAGE_PROBE_ENDPOINTS.get(key_provider)
        if not probe:
            # Unknown provider family: fall back to key-presence check.
            return success_response(data={"status": "ok", "message": "API key found"})
        url, header_template = probe
        ok, message = await _probe_endpoint(
            url, _auth_header(header_template, api_key), timeout=15.0
        )
        if ok:
            return success_response(data={"status": "ok", "message": message})
        return error_response(message=message)

    if request.media_type == "video":
        api_key = _find_provider_api_key(providers_dict, request.provider)
        if not api_key:
            return error_response(
                message=f"No API key found for provider '{request.provider}' in your settings"
            )
        try:
            from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig
            from myrm_agent_harness.toolkits.llms.video.providers import get_registry

            provider = get_registry().get(request.provider)
            if not provider:
                return error_response(
                    message=f"Provider '{request.provider}' not supported"
                )

            default_model = getattr(provider, "default_model", "sora")
            config = VideoGenerationConfig(
                provider=request.provider,
                model=request.model or default_model,
                api_key=SecretStr(api_key),
            )

            async with asyncio.timeout(15):
                healthy = await provider.health_check(config)

            if healthy:
                return success_response(
                    data={"status": "ok", "message": "Connection successful"}
                )
            return error_response(
                message="Health check failed — verify your API key and provider settings"
            )
        except TimeoutError:
            return error_response(message="Connection timed out")
        except Exception as e:
            logger.warning("Media config test failed: %s", e)
            return error_response(message="Connection test failed")

    if request.media_type == "tts":
        # Credential chain: voice settings first, then the provider table.
        voice_provider = (
            str(voice_dict.get("ttsProvider", "openai")) if voice_dict else "openai"
        )
        tts_provider = request.provider or voice_provider
        tts_api_key = ""
        if voice_dict:
            tts_api_key = str(voice_dict.get("ttsApiKey", "") or "").strip()
        if not tts_api_key:
            tts_api_key = _find_provider_api_key(providers_dict, tts_provider) or ""
        if not tts_api_key:
            return error_response(
                message=f"No API key found for TTS provider '{tts_provider}' in your settings"
            )

        tts_model = request.model
        if not tts_model and voice_dict:
            tts_model = str(voice_dict.get("ttsModel", "") or "")
            # OpenAI default from voice settings only applies to OpenAI probes.
            if tts_provider != "openai" and tts_model == "tts-1":
                tts_model = ""

        if tts_provider == "volcengine":
            is_seed = "seed" in tts_model.lower()
            timeout_budget = 130.0 if is_seed else 25.0
            try:
                async with asyncio.timeout(timeout_budget):
                    ok, message = await _probe_volcengine_tts(tts_api_key, tts_model)
            except TimeoutError:
                return error_response(message="Speech synthesis timed out")
            if ok:
                return success_response(data={"status": "ok", "message": message})
            return error_response(message=message)

        light_probe = _TTS_LIGHT_PROBE_ENDPOINTS.get(tts_provider)
        if not light_probe:
            return error_response(message=f"Unsupported TTS provider: {tts_provider}")
        url, header_template = light_probe
        ok, message = await _probe_endpoint(
            url, _auth_header(header_template, tts_api_key), timeout=15.0
        )
        if ok:
            return success_response(data={"status": "ok", "message": message})
        return error_response(message=message)

    return error_response(message=f"Unknown media type: {request.media_type}")


@router.get("/media-provider-status")
@limiter.limit(settings.rate_limit.chat)
async def media_provider_status(
    http_request: Request,
) -> JSONResponse:
    """Return availability status for all video providers (has API key + health check)."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.utils.response_utils import success_response

    configs = await load_user_configs()
    providers_dict = configs.providers_dict

    try:
        from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig
        from myrm_agent_harness.toolkits.llms.video.providers import get_registry

        registry = get_registry()
    except ImportError:
        return success_response(data={"providers": {}})

    provider_infos = registry.list_providers()

    async def _check_one(info: dict[str, object]) -> tuple[str, dict[str, object]]:
        pid = str(info["id"])
        api_key = _find_provider_api_key(providers_dict, pid)
        has_key = bool(api_key)
        healthy = False
        if api_key:
            provider = registry.get(pid)
            if provider:
                try:
                    config = VideoGenerationConfig(
                        provider=pid, api_key=SecretStr(api_key)
                    )
                    async with asyncio.timeout(10):
                        healthy = await provider.health_check(config)
                except Exception:
                    healthy = False
        return pid, {
            "name": info.get("name", pid),
            "hasApiKey": has_key,
            "healthy": healthy,
            "configured": has_key and healthy,
            "defaultModel": info.get("default_model", ""),
            "models": info.get("models", []),
        }

    checks = await asyncio.gather(*[_check_one(info) for info in provider_infos])
    return success_response(data={"providers": dict(checks)})
