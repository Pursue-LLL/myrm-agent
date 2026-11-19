"""Image task executor implementation.

[INPUT]
- myrm_agent_harness.toolkits.llms.image::ImageGenerator, ImageGenerationError (POS: engine)
- myrm_agent_harness.toolkits.llms.media_inputs::resolve_media_inputs (POS: the single reference resolver)
- myrm_agent_harness.toolkits.tasks::Task (POS: async task entity)
- app.ai_agents.media_tools.input_policy::build_media_input_policy (POS: reference-resolution policy)
- app.tasks.image_config_resolver::ImageGenerationConfigResolver (POS: config resolver)
- app.tasks.payload_values (POS: typed payload reads)

[OUTPUT]
- ImageTaskExecutor: AsyncTaskExecutor implementation for image_generate tasks
- image_task_result(): the result shape of a finished image task

[POS]
Server task worker executor for async image generation: it resolves the task's reference images through the single
resolver and returns the stored ``media://`` reference; a task whose image was not stored fails instead of succeeding
without an artifact.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.image import ImageGenerationError, ImageGenerator
from myrm_agent_harness.toolkits.llms.media_inputs import resolve_media_inputs
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_IMAGE_GENERATE
from myrm_agent_harness.toolkits.tasks import Task

from app.ai_agents.media_tools.input_policy import build_media_input_policy
from app.tasks.image_config_resolver import ImageGenerationConfigResolver
from app.tasks.payload_values import optional_str, str_list


def image_task_result(reference: str, mime_type: str, *, prompt: str, model: str, latency_ms: float) -> dict[str, object]:
    """Result of a finished image task: the stored image's ``media://`` reference with what produced it."""
    return {
        "images": [{"url": reference, "mime_type": mime_type}],
        "prompt": prompt,
        "model": model,
        "latency_ms": round(latency_ms),
    }


class ImageTaskExecutor:
    """Executor for image generation tasks.

    Implements AsyncTaskExecutor protocol to execute "image_generate" tasks.
    """

    def __init__(self, config_resolver: ImageGenerationConfigResolver) -> None:
        self._config_resolver = config_resolver

    async def execute(self, task: Task) -> dict[str, object]:
        """Generate the task's image and return ``images``, ``prompt``, ``model`` and ``latency_ms``."""
        payload = task.payload
        prompt = optional_str(payload.get("prompt"))
        if prompt is None:
            raise ValueError("Image task payload is missing required field: prompt")

        generator = ImageGenerator(self._config_resolver(task))
        references = str_list(payload.get("reference_image_urls"))
        reference_images = (
            await resolve_media_inputs(
                references,
                "image",
                build_media_input_policy(str_list(payload.get("allowed_roots"))),
                field_name="reference_image_urls",
            )
            if references
            else []
        )

        result = await generator.generate(
            prompt,
            size=optional_str(payload.get("size")),
            quality=optional_str(payload.get("quality")),
            reference_images=reference_images,
        )
        if not result.persisted_ref:
            raise ImageGenerationError("The generated image was not stored in the media library")

        return image_task_result(
            result.persisted_ref,
            result.mime_type,
            prompt=result.revised_prompt or prompt,
            model=result.model,
            latency_ms=result.latency_ms,
        )

    def can_execute(self, task_type: str) -> bool:
        """Check if can execute task type."""
        return task_type == TASK_TYPE_IMAGE_GENERATE


__all__ = ["ImageTaskExecutor", "image_task_result"]
