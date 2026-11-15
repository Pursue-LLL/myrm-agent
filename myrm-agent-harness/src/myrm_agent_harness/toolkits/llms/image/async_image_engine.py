"""Async image generation tools that return task_id instead of blocking.

[INPUT]
- models::ImageGenerationConfig (POS: Data types)
- tasks::SQLiteTaskStore, Task, TaskStatus (POS: generic async job queue)
- media_task_types::TASK_TYPE_IMAGE_GENERATE (POS: media async job type SSOT)

[OUTPUT]
- AsyncImageGenerationTools: Non-blocking enqueue; optional PayloadPostprocessor runs before TaskStore persist
- PayloadPostprocessor: Callable hook for server-side secret sealing (harness stays crypto-agnostic)

[POS]
Async version of image generation that creates tasks instead of blocking.
One task produces one image: the caller enqueues once per image it wants. Returns the task id
immediately, allowing the user to continue the conversation while the image generates in background.
Frontend monitors task status via SSE and renders placeholder -> real image.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Sequence

from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_IMAGE_GENERATE
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, Task, TaskStatus

from .models import ImageGenerationConfig

logger = logging.getLogger(__name__)

PayloadPostprocessor = Callable[[dict[str, object]], dict[str, object]]


class AsyncImageGenerationTools:
    """Async image generation for non-blocking Agent integration.

    Creates a Task in the TaskStore; a worker executes it in the background.
    """

    def __init__(
        self,
        config: ImageGenerationConfig,
        task_store: SQLiteTaskStore,
        *,
        payload_postprocessor: PayloadPostprocessor | None = None,
    ) -> None:
        self._config = config
        self._task_store = task_store
        self._payload_postprocessor = payload_postprocessor

    def _execution_config_payload(self) -> dict[str, object]:
        """Serialize non-callback execution fields for the worker snapshot."""
        cfg = self._config
        gateway_raw = cfg.gateway_config.model_dump(by_alias=False) if cfg.gateway_config else None
        api_key: str | None = None
        if cfg.api_key is not None:
            api_key = cfg.api_key.get_secret_value()
        return {
            "model": cfg.model,
            "fallback_models": list(cfg.fallback_models),
            "default_size": cfg.default_size,
            "timeout_seconds": cfg.timeout_seconds,
            "max_retries": cfg.max_retries,
            "gateway_config": gateway_raw,
            "api_key": api_key,
        }

    async def generate_image(
        self,
        prompt: str,
        *,
        size: str | None = None,
        quality: str | None = None,
        reference_image_urls: list[str] | None = None,
        allowed_roots: Sequence[str] | None = None,
        user_id: str = "local",
        agent_id: str | None = None,
        chat_id: str | None = None,
    ) -> str:
        """Enqueue one image generation task.

        Args:
            prompt: Text description of the desired image.
            size: Image dimensions as WIDTHxHEIGHT.
            quality: Provider quality value; not sent when ``None``.
            reference_image_urls: Optional references (resolved by the worker, not here).
            allowed_roots: Folders the worker may read file references from, snapshotted at enqueue time.
            user_id: User who owns this task (for multi-tenant isolation).
            agent_id: Agent that enqueued the task (opaque metadata for server resolver).
            chat_id: Chat session id recorded on the stored media.

        Returns:
            The id of the created task.
        """
        task_id = f"img-{uuid.uuid4().hex[:8]}"
        payload: dict[str, object] = {
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "reference_image_urls": reference_image_urls,
            **self._execution_config_payload(),
        }
        if allowed_roots:
            payload["allowed_roots"] = list(allowed_roots)
        if agent_id:
            payload["agent_id"] = agent_id
        if chat_id:
            payload["chat_id"] = chat_id
        if self._payload_postprocessor is not None:
            payload = self._payload_postprocessor(payload)
        task = Task(
            task_id=task_id,
            task_type=TASK_TYPE_IMAGE_GENERATE,
            user_id=user_id,
            status=TaskStatus.PENDING,
            payload=payload,
            priority=5,
            timeout=300,
        )

        await self._task_store.create_task(task)

        logger.info("Created image generation task: %s", task_id)
        return task_id


__all__ = ["AsyncImageGenerationTools", "PayloadPostprocessor"]
