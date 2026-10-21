"""Resolve ImageGenerationConfig for async image tasks executed by the worker.

[INPUT]
- myrm_agent_harness.toolkits.tasks::Task (POS: queued job with payload snapshot)
- app.ai_agents.media_tools.media_persist::create_media_persist_callback (POS: media library hook)

[OUTPUT]
- resolve_image_generation_config(): rebuild ImageGenerationConfig from task payload

[POS]
Worker-side config resolver bridging harness task queue and server image executor.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.core.config.gateway import ToolGatewayConfig
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import Task
from pydantic import SecretStr

from app.ai_agents.media_tools.media_persist import create_media_persist_callback
from app.tasks.task_payload_crypto import open_task_payload_secrets

ImageGenerationConfigResolver = Callable[[Task], ImageGenerationConfig]


def _coerce_str(value: object | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_str_list(value: object | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def resolve_image_generation_config(task: Task) -> ImageGenerationConfig:
    """Build ImageGenerationConfig from task payload snapshot written at enqueue time."""
    payload = open_task_payload_secrets(dict(task.payload))

    model = _coerce_str(payload.get("model")) or "dall-e-3"
    chat_id = _coerce_str(payload.get("chat_id"))

    gateway_raw = payload.get("gateway_config")
    gateway_config: ToolGatewayConfig | None = None
    if isinstance(gateway_raw, dict):
        gateway_config = ToolGatewayConfig.model_validate(gateway_raw)

    api_key_raw = payload.get("api_key")
    api_key: SecretStr | None = None
    if isinstance(api_key_raw, str) and api_key_raw.strip():
        api_key = SecretStr(api_key_raw.strip())

    timeout_raw = payload.get("timeout_seconds")
    timeout_seconds = int(timeout_raw) if isinstance(timeout_raw, int) else 120

    max_retries_raw = payload.get("max_retries")
    max_retries = int(max_retries_raw) if isinstance(max_retries_raw, int) else 1

    default_size = _coerce_str(payload.get("default_size")) or "1024x1024"
    default_quality = _coerce_str(payload.get("default_quality")) or "standard"

    return ImageGenerationConfig(
        model=model,
        api_key=api_key,
        fallback_models=_coerce_str_list(payload.get("fallback_models")),
        default_size=default_size,
        default_quality=default_quality,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        gateway_config=gateway_config,
        media_callback=create_media_persist_callback(
            chat_id=chat_id,
            model_name=model,
            source="generate",
        ),
    )


__all__ = ["ImageGenerationConfigResolver", "resolve_image_generation_config"]
