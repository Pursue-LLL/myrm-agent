"""Resolve VideoGenerationConfig for async video tasks executed by the worker.

[INPUT]
- myrm_agent_harness.toolkits.tasks::Task (POS: queued job with payload snapshot)
- app.ai_agents.media_tools.media_persist::create_media_persist_callback (POS: media library hook)

[OUTPUT]
- resolve_video_generation_config(): rebuild VideoGenerationConfig from task payload

[POS]
Worker-side config resolver bridging harness task queue and server video executor.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig
from myrm_agent_harness.toolkits.tasks import Task
from pydantic import SecretStr

from app.ai_agents.media_tools.media_persist import create_media_persist_callback
from app.tasks.task_payload_crypto import open_task_payload_secrets

VideoGenerationConfigResolver = Callable[[Task], VideoGenerationConfig]

_DEFAULT_TIMEOUT_SECONDS = 300
_DEFAULT_POLL_INTERVAL_SECONDS = 3.0
_DEFAULT_MAX_POLL_ATTEMPTS = 120
_DEFAULT_MAX_RETRIES = 1
_DEFAULT_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024


def _coerce_str(value: object | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_int(value: object | None, default: int) -> int:
    return value if isinstance(value, int) else default


def _coerce_int_optional(value: object | None) -> int | None:
    return value if isinstance(value, int) else None


def _coerce_float(value: object | None, default: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _parse_gateway_config(value: object | None) -> ToolGatewayConfig | None:
    if not isinstance(value, dict):
        return None
    return ToolGatewayConfig.model_validate(value)


def _parse_api_key(value: object | None) -> SecretStr | None:
    api_key = _coerce_str(value)
    if api_key is None:
        return None
    return SecretStr(api_key)


def _build_video_config(
    payload: dict[str, object],
    *,
    include_fallbacks: bool,
    media_callback_chat_id: str | None,
) -> VideoGenerationConfig:
    fallback_configs: list[VideoGenerationConfig] = []
    if include_fallbacks:
        raw_fallbacks = payload.get("fallback_configs")
        if isinstance(raw_fallbacks, list):
            for item in raw_fallbacks:
                if not isinstance(item, dict):
                    continue
                fallback_payload = dict(item)
                fallback_configs.append(
                    _build_video_config(
                        fallback_payload,
                        include_fallbacks=False,
                        media_callback_chat_id=media_callback_chat_id,
                    )
                )

    model = _coerce_str(payload.get("model")) or "sora"
    callback = create_media_persist_callback(
        chat_id=media_callback_chat_id,
        model_name=model,
        source="video_generate",
    )

    return VideoGenerationConfig(
        provider=_coerce_str(payload.get("provider")) or "openai",
        model=model,
        api_key=_parse_api_key(payload.get("api_key")),
        base_url=_coerce_str(payload.get("base_url")),
        timeout_seconds=_coerce_int(payload.get("timeout_seconds"), _DEFAULT_TIMEOUT_SECONDS),
        poll_interval_seconds=_coerce_float(payload.get("poll_interval_seconds"), _DEFAULT_POLL_INTERVAL_SECONDS),
        max_poll_attempts=_coerce_int(payload.get("max_poll_attempts"), _DEFAULT_MAX_POLL_ATTEMPTS),
        max_retries=_coerce_int(payload.get("max_retries"), _DEFAULT_MAX_RETRIES),
        fallback_configs=fallback_configs,
        gateway_config=_parse_gateway_config(payload.get("gateway_config")),
        default_aspect_ratio=_coerce_str(payload.get("default_aspect_ratio")),
        default_resolution=_coerce_str(payload.get("default_resolution")),
        default_duration_seconds=_coerce_int_optional(payload.get("default_duration_seconds")),
        media_callback=callback,
        max_download_bytes=_coerce_int(payload.get("max_download_bytes"), _DEFAULT_MAX_DOWNLOAD_BYTES),
    )


def resolve_video_generation_config(task: Task) -> VideoGenerationConfig:
    """Build VideoGenerationConfig from task payload snapshot written at enqueue time."""
    payload = open_task_payload_secrets(dict(task.payload))
    chat_id = _coerce_str(payload.get("chat_id"))
    return _build_video_config(payload, include_fallbacks=True, media_callback_chat_id=chat_id)


__all__ = ["VideoGenerationConfigResolver", "resolve_video_generation_config"]
