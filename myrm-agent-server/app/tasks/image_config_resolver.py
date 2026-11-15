"""Resolve ImageGenerationConfig for async image tasks executed by the worker.

[INPUT]
- myrm_agent_harness.toolkits.tasks::Task (POS: queued job with payload snapshot)
- app.ai_agents.media_tools.media_persist::create_media_persist_callback (POS: media library hook)
- app.tasks.payload_values (POS: typed payload reads)
- app.tasks.task_payload_crypto::open_task_payload_secrets (POS: payload secret decryption)

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
from app.tasks.payload_values import optional_int, optional_str, str_list
from app.tasks.task_payload_crypto import open_task_payload_secrets

ImageGenerationConfigResolver = Callable[[Task], ImageGenerationConfig]

_DEFAULT_TIMEOUT_SECONDS = 120
_DEFAULT_MAX_RETRIES = 1
_DEFAULT_SIZE = "1024x1024"


def resolve_image_generation_config(task: Task) -> ImageGenerationConfig:
    """Build ImageGenerationConfig from task payload snapshot written at enqueue time."""
    payload = open_task_payload_secrets(dict(task.payload))

    model = optional_str(payload.get("model"))
    if model is None:
        raise ValueError("Image task payload is missing required field: model")

    gateway_raw = payload.get("gateway_config")
    gateway_config = ToolGatewayConfig.model_validate(gateway_raw) if isinstance(gateway_raw, dict) else None

    api_key_raw = optional_str(payload.get("api_key"))
    timeout_seconds = optional_int(payload.get("timeout_seconds"))
    max_retries = optional_int(payload.get("max_retries"))

    return ImageGenerationConfig(
        model=model,
        api_key=SecretStr(api_key_raw) if api_key_raw else None,
        fallback_models=str_list(payload.get("fallback_models")),
        default_size=optional_str(payload.get("default_size")) or _DEFAULT_SIZE,
        timeout_seconds=_DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds,
        max_retries=_DEFAULT_MAX_RETRIES if max_retries is None else max_retries,
        gateway_config=gateway_config,
        media_callback=create_media_persist_callback(
            chat_id=optional_str(payload.get("chat_id")),
            model_name=model,
            source="generate",
        ),
    )


__all__ = ["ImageGenerationConfigResolver", "resolve_image_generation_config"]
