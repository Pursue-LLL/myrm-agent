"""Image task executor implementation.

[INPUT]
- myrm_agent_harness.toolkits.llms.image::ImageGenerator (POS: engine)
- myrm_agent_harness.toolkits.tasks::Task (POS: async task entity)
- app.tasks.image_config_resolver::ImageGenerationConfigResolver (POS: config resolver)

[OUTPUT]
- ImageTaskExecutor: AsyncTaskExecutor implementation for image_generate tasks

[POS]
Server task worker executor for async image generation with persisted media consumption.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.image import ImageGenerator
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_IMAGE_GENERATE
from myrm_agent_harness.toolkits.tasks import Task

from app.tasks.image_config_resolver import ImageGenerationConfigResolver


class ImageTaskExecutor:
    """Executor for image generation tasks.

    Implements AsyncTaskExecutor protocol to execute "image_generate" tasks.
    """

    def __init__(self, config_resolver: ImageGenerationConfigResolver) -> None:
        self._config_resolver = config_resolver

    async def execute(self, task: Task) -> dict[str, object]:
        """Execute image generation task.

        Args:
            task: Task with payload containing prompt, size, quality, etc.

        Returns:
            Result dict with images, model, latency_ms
        """
        payload = task.payload
        config = self._config_resolver(task)
        generator = ImageGenerator(config)

        allow_private = payload.get("allow_private_networks") is True

        result = await generator.generate(
            prompt=str(payload["prompt"]),
            size=payload.get("size") if isinstance(payload.get("size"), str) else None,
            quality=payload.get("quality") if isinstance(payload.get("quality"), str) else None,
            style=payload.get("style") if isinstance(payload.get("style"), str) else None,
            n=int(payload.get("count", 1)) if isinstance(payload.get("count"), int) else 1,
            reference_image_urls=payload.get("reference_image_urls")
            if isinstance(payload.get("reference_image_urls"), list)
            else None,
            cancellation_event=task.cancellation_event,
            allow_private_networks=allow_private,
        )

        final_url = result.persisted_url or result.url
        images: list[dict[str, object]] = []
        if final_url:
            images.append(
                {
                    "url": final_url,
                    "mime_type": result.mime_type,
                }
            )

        return {
            "images": images,
            "prompt": result.revised_prompt or str(payload.get("prompt", "")),
            "model": result.model,
            "latency_ms": result.latency_ms,
        }

    async def cancel(self, task: Task) -> bool:
        """Cancel image generation task."""
        if task.cancellation_event:
            task.cancellation_event.set()
            return True
        return False

    def can_execute(self, task_type: str) -> bool:
        """Check if can execute task type."""
        return task_type == TASK_TYPE_IMAGE_GENERATE


__all__ = ["ImageTaskExecutor"]
