"""Resolve VideoGenerationConfig for async video tasks executed by the worker.

[INPUT]
- myrm_agent_harness.toolkits.tasks::Task (POS: queued job with payload snapshot)
- app.ai_agents.media_tools.media_persist::create_media_persist_callback (POS: media library hook)
- app.tasks.payload_values (POS: typed payload reads)
- app.tasks.task_payload_crypto::open_task_payload_secrets (POS: payload secret decryption)

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
from app.tasks.payload_values import optional_int, optional_str
from app.tasks.task_payload_crypto import open_task_payload_secrets

VideoGenerationConfigResolver = Callable[[Task], VideoGenerationConfig]

_DEFAULT_TIMEOUT_SECONDS = 300
_DEFAULT_POLL_INTERVAL_SECONDS = 3.0
_DEFAULT_MAX_POLL_ATTEMPTS = 120
_DEFAULT_MAX_RETRIES = 1
_DEFAULT_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024


def _int_or(value: object | None, default: int) -> int:
    parsed = optional_int(value)
    return default if parsed is None else parsed


def _float_or(value: object | None, default: float) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def _required_str(payload: dict[str, object], key: str) -> str:
    value = optional_str(payload.get(key))
    if value is None:
        raise ValueError(f"Video task payload is missing required field: {key}")
    return value


def _parse_gateway_config(value: object | None) -> ToolGatewayConfig | None:
    if not isinstance(value, dict):
        return None
    return ToolGatewayConfig.model_validate(value)


def _parse_api_key(value: object | None) -> SecretStr | None:
    api_key = optional_str(value)
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
                fallback_configs.append(
                    _build_video_config(
                        dict(item),
                        include_fallbacks=False,
                        media_callback_chat_id=media_callback_chat_id,
                    )
                )

    # A task runs the provider and model it was enqueued with; a snapshot that names neither is corrupt, not defaulted.
    provider = _required_str(payload, "provider")
    model = _required_str(payload, "model")

    return VideoGenerationConfig(
        provider=provider,
        model=model,
        api_key=_parse_api_key(payload.get("api_key")),
        base_url=optional_str(payload.get("base_url")),
        timeout_seconds=_int_or(payload.get("timeout_seconds"), _DEFAULT_TIMEOUT_SECONDS),
        poll_interval_seconds=_float_or(payload.get("poll_interval_seconds"), _DEFAULT_POLL_INTERVAL_SECONDS),
        max_poll_attempts=_int_or(payload.get("max_poll_attempts"), _DEFAULT_MAX_POLL_ATTEMPTS),
        max_retries=_int_or(payload.get("max_retries"), _DEFAULT_MAX_RETRIES),
        fallback_configs=fallback_configs,
        gateway_config=_parse_gateway_config(payload.get("gateway_config")),
        default_aspect_ratio=optional_str(payload.get("default_aspect_ratio")),
        default_resolution=optional_str(payload.get("default_resolution")),
        default_duration_seconds=optional_int(payload.get("default_duration_seconds")),
        media_callback=create_media_persist_callback(
            chat_id=media_callback_chat_id,
            model_name=model,
            source="video_generate",
        ),
        max_download_bytes=_int_or(payload.get("max_download_bytes"), _DEFAULT_MAX_DOWNLOAD_BYTES),
    )


def resolve_video_generation_config(task: Task) -> VideoGenerationConfig:
    """Build VideoGenerationConfig from task payload snapshot written at enqueue time."""
    payload = open_task_payload_secrets(dict(task.payload))
    return _build_video_config(
        payload,
        include_fallbacks=True,
        media_callback_chat_id=optional_str(payload.get("chat_id")),
    )


__all__ = ["VideoGenerationConfigResolver", "resolve_video_generation_config"]
