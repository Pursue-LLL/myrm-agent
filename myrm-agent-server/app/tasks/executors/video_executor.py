"""Video task executor implementation.

[INPUT]
- myrm_agent_harness.toolkits.llms.video::VideoGenerator, VideoGenerationError (POS: engine)
- myrm_agent_harness.toolkits.llms.media_inputs::resolve_media_inputs (POS: the single reference resolver)
- myrm_agent_harness.toolkits.tasks::Task (POS: async task entity)
- app.ai_agents.media_tools.input_policy::build_media_input_policy (POS: reference-resolution policy)
- app.tasks.video_config_resolver::VideoGenerationConfigResolver (POS: config resolver)
- app.tasks.payload_values (POS: typed payload reads)

[OUTPUT]
- VideoTaskExecutor: AsyncTaskExecutor implementation for video_generate tasks

[POS]
Server task worker executor for async video generation: it resolves reference images and videos through the single
resolver, hands public video URLs to providers that can fetch them, and returns stored ``media://`` references.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.media_inputs import resolve_media_inputs
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_VIDEO_GENERATE
from myrm_agent_harness.toolkits.llms.video import VideoGenerator, get_registry
from myrm_agent_harness.toolkits.tasks import Task

from app.ai_agents.media_tools.input_policy import build_media_input_policy
from app.tasks.payload_values import optional_bool, optional_int, optional_str, str_list
from app.tasks.video_config_resolver import VideoGenerationConfigResolver

# Providers that can fetch a source video themselves (xAI extend/edit, fal continuation) read its public URLs here
# instead of re-uploading the bytes.
_SOURCE_URLS_PARAM = "_video_source_urls"


class VideoTaskExecutor:
    """Executor for video generation tasks.

    Implements AsyncTaskExecutor protocol to execute "video_generate" tasks.
    """

    def __init__(self, config_resolver: VideoGenerationConfigResolver) -> None:
        self._config_resolver = config_resolver

    async def execute(self, task: Task) -> dict[str, object]:
        """Execute video generation task."""
        payload = task.payload
        prompt = optional_str(payload.get("prompt"))
        if prompt is None:
            raise ValueError("Video task payload is missing required field: prompt")

        generator = VideoGenerator(self._config_resolver(task), get_registry())
        policy = build_media_input_policy(str_list(payload.get("allowed_roots")))
        image_refs = str_list(payload.get("reference_images"))
        video_refs = str_list(payload.get("reference_videos"))
        reference_images = (
            await resolve_media_inputs(image_refs, "image", policy, field_name="reference_images") if image_refs else None
        )
        reference_videos = (
            await resolve_media_inputs(video_refs, "video", policy, field_name="reference_videos") if video_refs else None
        )

        extra_params_raw = payload.get("extra_params")
        extra_params = dict(extra_params_raw) if isinstance(extra_params_raw, dict) else {}
        if source_urls := [ref for ref in video_refs if ref.startswith(("http://", "https://"))]:
            extra_params[_SOURCE_URLS_PARAM] = source_urls

        result = await generator.generate(
            prompt,
            provider_id=optional_str(payload.get("provider_override")),
            model=optional_str(payload.get("model_override")),
            duration_seconds=optional_int(payload.get("duration_seconds")),
            aspect_ratio=optional_str(payload.get("aspect_ratio")),
            resolution=optional_str(payload.get("resolution")),
            enable_audio=optional_bool(payload.get("enable_audio")),
            reference_images=reference_images,
            reference_videos=reference_videos,
            extra_params=extra_params or None,
        )

        result_dict = result.to_dict()
        result_dict["prompt"] = prompt
        return result_dict

    def can_execute(self, task_type: str) -> bool:
        """Check if can execute task type."""
        return task_type == TASK_TYPE_VIDEO_GENERATE


__all__ = ["VideoTaskExecutor"]
