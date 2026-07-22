"""Video task executor implementation."""

from __future__ import annotations

from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_VIDEO_GENERATE
from myrm_agent_harness.toolkits.llms.video import VideoGenerator, get_registry
from myrm_agent_harness.toolkits.llms.video.video_engine import (
    _resolve_image_inputs,
    _resolve_video_inputs,
)
from myrm_agent_harness.toolkits.tasks import Task

from app.tasks.video_config_resolver import VideoGenerationConfigResolver


def _coerce_str(value: object | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_str_list(value: object | None) -> list[str] | None:
    if not isinstance(value, list):
        return None
    values = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return values if values else None


def _coerce_int(value: object | None) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _coerce_bool(value: object | None) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


class VideoTaskExecutor:
    """Executor for video generation tasks.

    Implements AsyncTaskExecutor protocol to execute "video_generate" tasks.
    """

    def __init__(self, config_resolver: VideoGenerationConfigResolver) -> None:
        self._config_resolver = config_resolver

    async def execute(self, task: Task) -> dict[str, object]:
        """Execute video generation task."""
        payload = task.payload
        prompt_raw = _coerce_str(payload.get("prompt"))
        if prompt_raw is None:
            msg = "Video task payload is missing required field: prompt"
            raise ValueError(msg)

        config = self._config_resolver(task)
        generator = VideoGenerator(config, get_registry())

        reference_images = _coerce_str_list(payload.get("reference_images"))
        reference_videos = _coerce_str_list(payload.get("reference_videos"))
        resolved_images = await _resolve_image_inputs(reference_images) if reference_images else None
        resolved_videos = await _resolve_video_inputs(reference_videos) if reference_videos else None

        extra_params_raw = payload.get("extra_params")
        extra_params = extra_params_raw if isinstance(extra_params_raw, dict) else None

        result = await generator.generate(
            prompt_raw,
            provider_id=_coerce_str(payload.get("provider_override")),
            model=_coerce_str(payload.get("model_override")),
            duration_seconds=_coerce_int(payload.get("duration_seconds")),
            aspect_ratio=_coerce_str(payload.get("aspect_ratio")),
            resolution=_coerce_str(payload.get("resolution")),
            enable_audio=_coerce_bool(payload.get("enable_audio")),
            reference_images=resolved_images,
            reference_videos=resolved_videos,
            extra_params=extra_params,
            cancellation_event=task.cancellation_event,
        )

        result_dict = result.to_dict()
        result_dict["prompt"] = prompt_raw
        return result_dict

    async def cancel(self, task: Task) -> bool:
        """Cancel video generation task."""
        if task.cancellation_event:
            task.cancellation_event.set()
            return True
        return False

    def can_execute(self, task_type: str) -> bool:
        """Check if can execute task type."""
        return task_type == TASK_TYPE_VIDEO_GENERATE


__all__ = ["VideoTaskExecutor"]
