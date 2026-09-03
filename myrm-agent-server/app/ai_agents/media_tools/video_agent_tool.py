"""[INPUT]
- myrm_agent_harness.toolkits.llms.video.video_engine::VideoGenerationTools (POS: sync video engine)
- myrm_agent_harness.toolkits.llms.video.async_video_engine::AsyncVideoGenerationTools (POS: async enqueue adapter)

[OUTPUT]
- create_video_generation_tool(): LangChain BaseTool adapter for video generation

[POS]
LangChain adapter for harness video tools (product layer). Generate action enqueues
through TaskStore when async_config is provided; list/status stay compatible.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from langchain_core.tools import BaseTool, tool
from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig, VideoGenerationTools
from myrm_agent_harness.toolkits.llms.video.async_video_engine import AsyncVideoGenerationTools
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class VideoToolInput(BaseModel):
    action: Literal["generate", "status", "list"] = Field(
        default="generate",
        description="Action to perform: 'generate' (submit async video creation task), 'status' (query progress of task_id), 'list' (discover supported video models and providers).",
    )
    prompt: str | None = Field(
        default=None,
        description="Detailed text prompt describing the video scene, motion, subject, and lighting (required for generate).",
    )
    provider: str | None = Field(
        default=None, description="Optional provider override (e.g. 'kling', 'luma', 'runway', 'minimax')."
    )
    model: str | None = Field(default=None, description="Optional model override.")
    duration_seconds: int | None = Field(default=None, description="Target clip duration in seconds (e.g. 5 or 10).")
    aspect_ratio: str | None = Field(default=None, description="Aspect ratio (e.g. '16:9', '9:16', '1:1').")
    resolution: str | None = Field(default=None, description="Video resolution: '720p', '1080p', or '4k'.")
    enable_audio: bool | None = Field(
        default=None, description="Whether to synthesize an audio/sound effects track when supported."
    )
    reference_images: list[str] | None = Field(
        default=None,
        description="Optional image URLs or local paths for image-to-video (I2V) generation.",
    )
    reference_videos: list[str] | None = Field(
        default=None,
        description="Optional video URLs or local paths for video-to-video (V2V) transformation.",
    )
    negative_prompt: str | None = Field(
        default=None,
        description="Negative prompt specifying elements to avoid (e.g. 'distorted faces, blurry, watermark, extra limbs').",
    )
    seed: int | None = Field(
        default=None,
        description="Random seed for reproducible video generation across multiple storyboard scenes.",
    )
    force: bool = Field(default=False, description="Force enqueue a new generation even if an existing session task is active.")
    task_id: str | None = Field(
        default=None,
        description="Task ID returned from a previous action='generate' call (required when action='status').",
    )


def _serialize_task(task: object) -> dict[str, object]:
    """Serialize a queue task for status output."""
    from myrm_agent_harness.toolkits.tasks import Task

    if not isinstance(task, Task):
        return {}

    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "result": task.result,
        "error": {
            "error_type": task.error.error_type,
            "message": task.error.message,
            "recoverable": task.error.recoverable.value,
        }
        if task.error
        else None,
        "priority": task.priority,
        "progress": task.progress,
        "progress_message": task.progress_message,
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def _clamp_reference_sources(sources: list[str] | None) -> list[str] | None:
    """Auto-clamp local reference image paths to prevent oversize / orientation faults."""
    if not sources:
        return None
    import tempfile
    from pathlib import Path

    from app.ai_agents.media_tools.image_clamp import clamp_image_payload

    sanitized: list[str] = []
    for src in sources:
        try:
            p = Path(src).expanduser().resolve()
            if p.is_file():
                raw = p.read_bytes()
                clamped, _, _ = clamp_image_payload(raw)
                if len(clamped) != len(raw) or clamped is not raw:
                    tf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    tf.write(clamped)
                    tf.close()
                    sanitized.append(tf.name)
                    continue
        except Exception:
            pass
        sanitized.append(src)
    return sanitized


def create_video_generation_tool(
    engine: VideoGenerationTools,
    *,
    async_config: VideoGenerationConfig | None = None,
    task_user_id: str = "default",
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> BaseTool:
    """Wrap VideoGenerationTools as ``video_tool``.

    When *async_config* is set, ``action=generate`` enqueues to TaskStore and
    returns ``task_id`` JSON immediately.
    """

    async def _enqueue_generate(
        prompt: str | None,
        *,
        provider: str | None,
        model: str | None,
        duration_seconds: int | None,
        aspect_ratio: str | None,
        resolution: str | None,
        enable_audio: bool | None,
        reference_images: list[str] | None,
        reference_videos: list[str] | None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        force: bool,
    ) -> str:
        extra_params: dict[str, object] = {}
        if negative_prompt:
            extra_params["negative_prompt"] = negative_prompt
        if seed is not None:
            extra_params["seed"] = seed

        safe_reference_images = _clamp_reference_sources(reference_images)

        if async_config is None:
            kwargs: dict[str, object] = {
                "prompt": prompt,
                "provider": provider,
                "model": model,
                "duration_seconds": duration_seconds,
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "enable_audio": enable_audio,
                "reference_images": safe_reference_images,
                "reference_videos": reference_videos,
                "force": force,
            }
            if extra_params:
                kwargs["extra_params"] = extra_params
            return await engine.execute("generate", **kwargs)
        try:
            from app.lifecycle.task_worker import get_task_store
            from app.tasks.task_payload_crypto import seal_task_payload_secrets

            async_engine = AsyncVideoGenerationTools(
                async_config,
                get_task_store(),
                payload_postprocessor=seal_task_payload_secrets,
            )
            return await async_engine.generate_video(
                prompt or "",
                provider=provider,
                model=model,
                duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                enable_audio=enable_audio,
                reference_images=safe_reference_images,
                reference_videos=reference_videos,
                extra_params=extra_params or None,
                force=force,
                user_id=task_user_id,
                agent_id=agent_id,
                chat_id=chat_id,
            )
        except RuntimeError as exc:
            logger.warning("Async video enqueue unavailable, using sync generate: %s", exc)
            return await engine.execute(
                "generate",
                prompt=prompt,
                provider=provider,
                model=model,
                duration_seconds=duration_seconds,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                enable_audio=enable_audio,
                reference_images=reference_images,
                reference_videos=reference_videos,
                extra_params=extra_params or None,
                force=force,
            )

    async def _status(task_id: str | None) -> str:
        if not task_id:
            return await engine.execute(
                "status",
                prompt=None,
                provider=None,
                model=None,
                duration_seconds=None,
                aspect_ratio=None,
                resolution=None,
                enable_audio=None,
                reference_images=None,
                reference_videos=None,
                force=False,
            )
        try:
            from app.lifecycle.task_worker import get_task_store

            task = await get_task_store().get_task(task_id)
            if task is None:
                return json.dumps(
                    {"error": "Task not found", "task_id": task_id},
                    ensure_ascii=False,
                )
            return json.dumps(_serialize_task(task), ensure_ascii=False)
        except RuntimeError as exc:
            logger.warning("Task store unavailable for video status lookup: %s", exc)
            return await engine.execute(
                "status",
                prompt=None,
                provider=None,
                model=None,
                duration_seconds=None,
                aspect_ratio=None,
                resolution=None,
                enable_audio=None,
                reference_images=None,
                reference_videos=None,
                force=False,
            )

    @tool("video_tool", args_schema=VideoToolInput)
    async def video_tool(
        action: Literal["generate", "status", "list"] = "generate",
        prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        duration_seconds: int | None = None,
        aspect_ratio: str | None = None,
        resolution: str | None = None,
        enable_audio: bool | None = None,
        reference_images: list[str] | None = None,
        reference_videos: list[str] | None = None,
        negative_prompt: str | None = None,
        seed: int | None = None,
        force: bool = False,
        task_id: str | None = None,
    ) -> str:
        """Generate, poll status of, or list video generation models.

        Workflow:
        1) Call action='generate' with prompt (and optional reference_images for I2V). This returns a task JSON with task_id.
        2) Call action='status' with task_id to inspect progress and retrieve the final video URL upon completion.
        3) Call action='list' to view available video models and providers.
        """
        if action == "list":
            return await engine.execute(
                "list",
                prompt=None,
                provider=None,
                model=None,
                duration_seconds=None,
                aspect_ratio=None,
                resolution=None,
                enable_audio=None,
                reference_images=None,
                reference_videos=None,
                force=False,
            )
        if action == "status":
            return await _status(task_id)
        if not prompt or not prompt.strip():
            return '{"error": "prompt is required when action=generate"}'
        return await _enqueue_generate(
            prompt,
            provider=provider,
            model=model,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_audio=enable_audio,
            reference_images=reference_images,
            reference_videos=reference_videos,
            negative_prompt=negative_prompt,
            seed=seed,
            force=force,
        )

    if async_config is not None:
        video_tool.description = (
            f"{engine.tool_description} "
            "Workflow: 1) Call action='generate' with prompt (and optional reference_images for I2V) to start and receive task_id. "
            "2) Call action='status' with task_id to inspect progress until completed and retrieve the final video URL. "
            "3) Call action='list' to view available video models and providers."
        )
    else:
        video_tool.description = engine.tool_description
    return video_tool
