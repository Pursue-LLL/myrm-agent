"""[INPUT]
- myrm_agent_harness.toolkits.llms.video.video_engine::VideoGenerationTools (POS: provider listing)
- myrm_agent_harness.toolkits.llms.video.async_video_engine::AsyncVideoGenerationTools (POS: video task enqueue)
- myrm_agent_harness.toolkits.llms.video::VideoGenerationConfig, get_registry (POS: engine config and provider registry)
- app.ai_agents.media_tools.task_results (POS: shared error, started-tasks and status results)
- app.ai_agents.media_tools.video_schema::build_video_input_schema (POS: provider-pruned tool input model)
- app.tasks.task_payload_crypto::seal_task_payload_secrets (POS: payload secret sealing)

[OUTPUT]
- create_video_generation_tool(): LangChain BaseTool adapter for video generation

[POS]
LangChain adapter of the video engine. ``generate`` enqueues one background task and answers with the task list;
``status`` and ``list`` read the queue and the provider catalog. Reference files are resolved by the worker through
the single input resolver, so a bad reference fails the task with its name in the message instead of generating
something else.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal

from langchain_core.tools import BaseTool, tool
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_VIDEO_GENERATE
from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig, VideoGenerationTools, get_registry
from myrm_agent_harness.toolkits.llms.video.async_video_engine import AsyncVideoGenerationTools

from app.ai_agents.media_tools.task_results import (
    media_task_status_result,
    media_task_store,
    started_tasks_result,
    tool_error,
)
from app.ai_agents.media_tools.video_schema import build_video_input_schema
from app.tasks.task_payload_crypto import seal_task_payload_secrets

logger = logging.getLogger(__name__)

_TOOL_DESCRIPTION = (
    "Generate videos. Generation is a background task whose result appears in the chat by itself, "
    "so never repeat its media:// address in your reply. "
    "action='generate': a clip from a text prompt, optionally steered by reference_images (image-to-video) or "
    "reference_videos (video-to-video, where the provider supports it). "
    "action='status': state and result of a task_id, which is also how to get the media:// address of an earlier video. "
    "action='list': the available providers and models and what they support."
)


def create_video_generation_tool(
    config: VideoGenerationConfig,
    *,
    allowed_roots: Sequence[str] = (),
    task_user_id: str = "default",
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> BaseTool:
    """Build ``video_tool`` for the provider and model in ``config``.

    ``allowed_roots`` are the workspace folders the agent's file references may point into.
    """
    lister = VideoGenerationTools(config)
    active_provider = get_registry().get(config.provider)
    input_schema = build_video_input_schema(active_provider.capabilities if active_provider else None)

    async def _generate(
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
        negative_prompt: str | None,
        seed: int | None,
    ) -> str:
        if not prompt or not prompt.strip():
            return tool_error("prompt is required when action=generate")
        try:
            task_store = media_task_store()
        except RuntimeError as exc:
            logger.warning("Task store unavailable for video generation: %s", exc)
            return tool_error("Task store unavailable")

        extra_params: dict[str, object] = {}
        if negative_prompt:
            extra_params["negative_prompt"] = negative_prompt
        if seed is not None:
            extra_params["seed"] = seed

        enqueuer = AsyncVideoGenerationTools(config, task_store, payload_postprocessor=seal_task_payload_secrets)
        task_id = await enqueuer.generate_video(
            prompt,
            provider=provider,
            model=model,
            duration_seconds=duration_seconds,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_audio=enable_audio,
            reference_images=reference_images or None,
            reference_videos=reference_videos or None,
            extra_params=extra_params or None,
            allowed_roots=allowed_roots,
            user_id=task_user_id,
            agent_id=agent_id,
            chat_id=chat_id,
        )
        return started_tasks_result(
            TASK_TYPE_VIDEO_GENERATE,
            [task_id],
            message="Generation started; the video appears in the chat when it is ready.",
        )

    @tool("video_tool", args_schema=input_schema)
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
        task_id: str | None = None,
    ) -> str:
        """Generate, poll the status of, or list videos."""
        if action == "list":
            return lister.list_providers()
        if action == "status":
            return await media_task_status_result(task_id)
        return await _generate(
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
        )

    video_tool.description = _TOOL_DESCRIPTION
    return video_tool
