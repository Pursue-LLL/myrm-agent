"""Image task executor implementation."""

from myrm_agent_harness.toolkits.llms.image import ImageGenerator
from myrm_agent_harness.toolkits.tasks import Task


class ImageTaskExecutor:
    """Executor for image generation tasks.

    Implements AsyncTaskExecutor protocol to execute "image_generate" tasks.
    """

    def __init__(self, generator: ImageGenerator):
        self._generator = generator

    async def execute(self, task: Task) -> dict[str, object]:
        """Execute image generation task.

        Args:
            task: Task with payload containing prompt, size, quality, etc.

        Returns:
            Result dict with images, model, latency_ms
        """
        payload = task.payload

        result = await self._generator.generate(
            prompt=payload["prompt"],
            size=payload.get("size"),
            quality=payload.get("quality"),
            style=payload.get("style"),
            n=payload.get("count", 1),
            reference_image_urls=payload.get("reference_image_urls"),
            cancellation_event=task.cancellation_event,
        )

        return {
            "images": [
                {
                    "url": img.url,
                    "width": img.width,
                    "height": img.height,
                    "mime_type": img.mime_type,
                }
                for img in result.images
            ],
            "prompt": result.prompt,
            "model": result.model,
            "provider": result.provider,
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
        return task_type == "image_generate"


__all__ = ["ImageTaskExecutor"]
