"""[INPUT]
- myrm_agent_harness.toolkits.llms.video.video_engine::VideoGenerationTools (POS: sync video engine)
- myrm_agent_harness.toolkits.llms.video.async_video_engine::AsyncVideoGenerationTools (POS: async enqueue adapter)
- myrm_agent_harness.toolkits.llms.video.models::ModerationBlockedError (POS: terminal moderation safety exception)
- app.ai_agents.media_tools.image_clamp::clamp_image_payload (POS: reference media downsampling and orientation normalization)

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
from myrm_agent_harness.toolkits.llms.video import (
    ModerationBlockedError,
    VideoGenerationConfig,
    VideoGenerationTools,
)
from myrm_agent_harness.toolkits.llms.video.async_video_engine import AsyncVideoGenerationTools

from app.ai_agents.media_tools.video_schema import _build_dynamic_video_input_schema

logger = logging.getLogger(__name__)


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

        # Sanitize parameters against target provider's capabilities if available
        target_provider_id = provider or getattr(getattr(engine, "_config", None), "provider", None)
        if target_provider_id and hasattr(engine, "_registry"):
            try:
                target_prov = engine._registry.get(target_provider_id)
                target_caps = getattr(target_prov, "capabilities", None)
                if target_caps:
                    if not target_caps.supports_audio and enable_audio:
                        logger.warning("Provider '%s' does not support audio; disabling enable_audio", target_provider_id)
                        enable_audio = False
                    if not target_caps.supports_aspect_ratio and aspect_ratio:
                        logger.warning("Provider '%s' does not support custom aspect_ratio; dropping aspect_ratio", target_provider_id)
                        aspect_ratio = None
            except Exception as cap_err:
                logger.debug("Failed capability probe for '%s': %s", target_provider_id, cap_err)

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

    # Dynamic Schema Diet: trim unsupported parameters according to current provider capabilities
    active_capabilities = None
    try:
        active_provider = engine._registry.get(engine._config.provider)
        if active_provider:
            active_capabilities = active_provider.capabilities
    except Exception:
        pass

    dynamic_args_schema = _build_dynamic_video_input_schema(active_capabilities)

    @tool("video_tool", args_schema=dynamic_args_schema)
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
        try:
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
        except ModerationBlockedError as m_exc:
            reason = getattr(m_exc, "violation_reason", None) or "Content moderation or safety policy violation"
            logger.warning("Video generation blocked by content moderation: %s (%s)", m_exc, reason)
            return json.dumps(
                {
                    "error": str(m_exc),
                    "code": "MODERATION_BLOCKED",
                    "reason": reason,
                    "retryable": False,
                    "tip": "The prompt was rejected by the provider safety filter. Do NOT retry with the same prompt; adjust the wording to comply with content policies.",
                },
                ensure_ascii=False,
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
