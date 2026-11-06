"""[INPUT]
- app.core.channel_bridge.config_loader::load_user_configs / load_user_configs (POS: User config loader for channel agent execution.)
- app.core.channel_bridge.config_parsers::build_vision_fallback_engine_from_providers / extract_vision_fallback_model_config / build_video_fallback_probe_engine_from_providers / extract_video_fallback_model_config (POS: channel_bridge 配置解析的唯一公开入口；调用方不需要知道实现位于哪个子模块。)
- myrm_agent_harness.toolkits.llms.vision.fallback_engine::VisionDescriptionError / VisionDescriptionError (POS: 视觉能力降级服务。在主模型缺乏视觉能力时，提供底层、无状态的图像转文本能力；封装并发解析与 image_compressor Reactive Resize 兜底。属于 Harness 框架层，供业务层与框架工具链调用，不依赖业务逻辑和数据)

[OUTPUT]
- VisionHealthResult: Result of a vision fallback chain health probe.
- vision_health_check: Probe the configured vision fallback chain with a tiny test image.
- video_health_check: Probe the configured video fallback chain with a tiny test image.

[POS]
配置 API 的域子模块；由 app/api/config/router.py 按原顺序挂载。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

_TINY_VISION_HEALTH_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


class VisionHealthResult(BaseModel):
    """Result of a vision fallback chain health probe."""

    configured: bool = Field(..., description="Whether visionFallbackModel is configured")
    healthy: bool = Field(..., description="Whether the vision model successfully analyzed a test image")
    latency_ms: int | None = Field(default=None, description="Vision probe latency in milliseconds")
    error: str | None = Field(default=None, description="Error message when unhealthy")
    model: str | None = Field(default=None, description="Configured primary LiteLLM model id")
    resolved_model: str | None = Field(
        default=None,
        description="LiteLLM model id that actually succeeded during the probe",
    )
    base_url: str | None = Field(default=None, description="Resolved API base URL when unhealthy")


@router.post("/vision-health", response_model=VisionHealthResult)
async def vision_health_check() -> VisionHealthResult:
    """Probe the configured vision fallback chain with a tiny test image."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        build_vision_fallback_engine_from_providers,
        extract_vision_fallback_model_config,
    )

    user_cfgs = await load_user_configs()
    model_cfg = extract_vision_fallback_model_config(user_cfgs.providers_dict)
    if model_cfg is None:
        return VisionHealthResult(
            configured=False,
            healthy=False,
            error="Vision fallback model is not configured",
        )

    try:
        engine = build_vision_fallback_engine_from_providers(user_cfgs.providers_dict)
        if engine is None:
            return VisionHealthResult(
                configured=False,
                healthy=False,
                error="Vision fallback model is not configured",
            )
        from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
            VisionDescriptionError,
        )

        start = time.monotonic()
        try:
            await engine.describe_image_b64(
                _TINY_VISION_HEALTH_PNG_B64,
                "image/png",
                prompt="Health check",
            )
        except VisionDescriptionError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            resolved_model = engine.last_success_model or model_cfg.model
            return VisionHealthResult(
                configured=True,
                healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                model=model_cfg.model,
                resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
                base_url=model_cfg.base_url,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        resolved_model = engine.last_success_model or model_cfg.model
        return VisionHealthResult(
            configured=True,
            healthy=True,
            latency_ms=latency_ms,
            model=model_cfg.model,
            resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
        )
    except Exception as exc:
        logger.warning("Vision fallback health check failed: %s", exc)
        return VisionHealthResult(
            configured=True,
            healthy=False,
            error=str(exc),
            model=model_cfg.model,
            base_url=model_cfg.base_url,
        )


VideoHealthResult = VisionHealthResult


@router.post("/video-health", response_model=VideoHealthResult)
async def video_health_check() -> VideoHealthResult:
    """Probe the configured video fallback chain with a tiny test image."""
    from myrm_agent_harness.toolkits.llms.vision.fallback_engine import (
        VisionDescriptionError,
    )

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import (
        build_video_fallback_probe_engine_from_providers,
        extract_video_fallback_model_config,
    )

    user_cfgs = await load_user_configs()
    model_cfg = extract_video_fallback_model_config(user_cfgs.providers_dict)
    if model_cfg is None:
        return VideoHealthResult(
            configured=False,
            healthy=False,
            error="Video fallback model is not configured",
        )

    try:
        engine = build_video_fallback_probe_engine_from_providers(user_cfgs.providers_dict)
        if engine is None:
            return VideoHealthResult(
                configured=False,
                healthy=False,
                error="Video fallback model is not configured",
            )

        start = time.monotonic()
        try:
            await engine.describe_image_b64(
                _TINY_VISION_HEALTH_PNG_B64,
                "image/png",
                prompt="Health check",
            )
        except VisionDescriptionError as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            resolved_model = engine.last_success_model or model_cfg.model
            return VideoHealthResult(
                configured=True,
                healthy=False,
                latency_ms=latency_ms,
                error=str(exc),
                model=model_cfg.model,
                resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
                base_url=model_cfg.base_url,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        resolved_model = engine.last_success_model or model_cfg.model
        return VideoHealthResult(
            configured=True,
            healthy=True,
            latency_ms=latency_ms,
            model=model_cfg.model,
            resolved_model=(resolved_model if resolved_model != model_cfg.model else None),
        )
    except Exception as exc:
        logger.warning("Video fallback health check failed: %s", exc)
        return VideoHealthResult(
            configured=True,
            healthy=False,
            error=str(exc),
            model=model_cfg.model,
            base_url=model_cfg.base_url,
        )
