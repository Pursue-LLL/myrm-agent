"""General Agent API — autonomous decision-making agent with streaming SSE."""
import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
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

    media_type: str  # "image" or "video"
    provider: str = "openai"
    model: str = ""

    class Config:
        alias_generator = to_camel
        populate_by_name = True

@router.post("/test-media-config")
@limiter.limit(settings.rate_limit.chat)
async def test_media_config(
    request: TestMediaConfigRequest,
    http_request: Request,
) -> JSONResponse:
    """Test media generation config by verifying API key and provider connectivity."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.utils.response_utils import error_response, success_response

    configs = await load_user_configs()
    providers_dict = configs.providers_dict

    if request.media_type == "image":
        key_provider = _resolve_image_api_key_provider(request.model or "dall-e-3")
        api_key = _find_provider_api_key(providers_dict, key_provider)
        if not api_key:
            return error_response(message=f"No API key found for provider '{key_provider}' in your settings")
        return success_response(data={"status": "ok", "message": "API key found"})

    if request.media_type == "video":
        api_key = _find_provider_api_key(providers_dict, request.provider)
        if not api_key:
            return error_response(message=f"No API key found for provider '{request.provider}' in your settings")
        try:
            from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig
            from myrm_agent_harness.toolkits.llms.video.providers import get_registry

            config = VideoGenerationConfig(
                provider=request.provider,
                model=request.model or "sora",
                api_key=api_key,
            )
            provider = get_registry().get(request.provider)
            if not provider:
                return error_response(message=f"Provider '{request.provider}' not supported")

            async with asyncio.timeout(15):
                healthy = await provider.health_check(config)

            if healthy:
                return success_response(data={"status": "ok", "message": "Connection successful"})
            return error_response(message="Health check failed — verify your API key and provider settings")
        except TimeoutError:
            return error_response(message="Connection timed out")
        except Exception as e:
            logger.warning("Media config test failed: %s", e)
            return error_response(message=f"Connection test failed: {e}")

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
        if has_key:
            provider = registry.get(pid)
            if provider:
                try:
                    config = VideoGenerationConfig(provider=pid, api_key=api_key)
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

