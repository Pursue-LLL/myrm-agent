"""[INPUT]
- myrm_agent_harness.toolkits.llms.image.image_engine::ImageGenerationTools (POS: sync generate/edit/list)
- myrm_agent_harness.toolkits.llms.image.async_image_engine::AsyncImageGenerationTools (POS: async generate enqueue)
- myrm_agent_harness.toolkits.llms.image.models::ImageGenerationConfig (POS: shared engine config)
- myrm_agent_harness.core.security.http.secure_fetch::secure_get (POS: SSRF-protected edit/mask URL fetch)
- app.ai_agents.media_tools.image_clamp::clamp_image_payload (POS: payload downsampling and format normalization)

[OUTPUT]
- create_image_generation_tool(): LangChain BaseTool adapter for image generation

[POS]
LangChain adapter: generate enqueues via TaskStore when async_config is provided;
edit/list stay on synchronous ImageGenerationTools.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

import httpx
from langchain_core.tools import BaseTool, tool
from myrm_agent_harness.toolkits.llms.image.image_engine import ImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ImageToolInput(BaseModel):
    action: Literal["generate", "edit", "list", "status"] = Field(
        default="generate",
        description="Action to perform: 'generate' (create new images from text prompt), 'edit' (modify an existing image via image_url and prompt), 'list' (discover available models and capabilities), 'status' (query progress and final URL of task_id).",
    )
    prompt: str = Field(
        default="",
        description="Detailed text description of the image to generate or modification instructions for edit (required for generate/edit).",
    )
    size: str | None = Field(
        default=None,
        description="Image dimensions or aspect ratio (e.g. '1024x1024', '1792x1024', '1024x1792', or '16:9').",
    )
    quality: str | None = Field(
        default=None,
        description="Image quality setting: 'standard' or 'hd'.",
    )
    style: str | None = Field(
        default=None,
        description="Visual rendering style for DALL-E 3: 'vivid' (hyper-real/dramatic) or 'natural' (realistic/photographic).",
    )
    n: int = Field(
        default=1,
        ge=1,
        le=4,
        description="Number of image variations to generate (1-4).",
    )
    reference_image_urls: list[str] | None = Field(
        default=None,
        description="Optional reference image URLs for visual style transfer or multi-image guided generation.",
    )
    image_url: str | None = Field(
        default=None,
        description="Source image URL to modify when action='edit' (HTTP/HTTPS URL).",
    )
    mask_url: str | None = Field(
        default=None,
        description="Optional mask image URL for inpainting when action='edit' (transparent areas will be regenerated).",
    )
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


async def _fetch_image_bytes(url: str, *, allow_private_networks: bool = False) -> tuple[bytes, str | None, int]:
    from app.ai_agents.media_tools.image_clamp import clamp_image_payload

    if allow_private_networks:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            return clamp_image_payload(response.content, content_type=content_type)

    from myrm_agent_harness.core.security.http.secure_fetch import secure_get

    response = await secure_get(url, timeout=30.0)
    response.raise_for_status()
    content_type = response.headers.get("content-type")
    return clamp_image_payload(response.content, content_type=content_type)


def create_image_generation_tool(
    engine: ImageGenerationTools,
    *,
    allow_private_networks: bool = False,
    async_config: ImageGenerationConfig | None = None,
    task_user_id: str = "default",
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> BaseTool:
    """Wrap ImageGenerationTools as ``image_tool``.

    When *async_config* is set, ``action=generate`` enqueues a background task and
    returns ``task_id`` JSON; edit/list remain synchronous on *engine*.
    """

    async def _enqueue_generate(
        prompt: str,
        *,
        size: str | None,
        quality: str | None,
        style: str | None,
        n: int,
        reference_image_urls: list[str] | None,
    ) -> str:
        if async_config is None:
            return await engine.generate_image(
                prompt,
                size=size,
                quality=quality,
                style=style,
                n=n,
                reference_image_urls=reference_image_urls,
            )
        try:
            from myrm_agent_harness.toolkits.llms.image.async_image_engine import (
                AsyncImageGenerationTools,
            )

            from app.lifecycle.task_worker import get_task_store
            from app.tasks.task_payload_crypto import seal_task_payload_secrets

            async_engine = AsyncImageGenerationTools(
                async_config,
                get_task_store(),
                allow_private_networks=allow_private_networks,
                payload_postprocessor=seal_task_payload_secrets,
            )
            return await async_engine.generate_image(
                prompt,
                size=size,
                quality=quality,
                style=style,
                n=n,
                reference_image_urls=reference_image_urls,
                user_id=task_user_id,
                agent_id=agent_id,
                chat_id=chat_id,
            )
        except RuntimeError as exc:
            logger.warning("Async image enqueue unavailable, using sync generate: %s", exc)
            return await engine.generate_image(
                prompt,
                size=size,
                quality=quality,
                style=style,
                n=n,
                reference_image_urls=reference_image_urls,
            )

    async def _status(task_id: str | None) -> str:
        if not task_id:
            return json.dumps(
                {"error": "task_id is required when action=status"},
                ensure_ascii=False,
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
            logger.warning("Task store unavailable for image status lookup: %s", exc)
            return json.dumps(
                {"error": "Task store unavailable", "task_id": task_id},
                ensure_ascii=False,
            )

    @tool("image_tool", args_schema=ImageToolInput)
    async def image_tool(
        action: Literal["generate", "edit", "list", "status"] = "generate",
        prompt: str = "",
        size: str | None = None,
        quality: str | None = None,
        style: str | None = None,
        n: int = 1,
        reference_image_urls: list[str] | None = None,
        image_url: str | None = None,
        mask_url: str | None = None,
        task_id: str | None = None,
    ) -> str:
        """Generate, edit, poll status of, or list image generation models.

        Workflow:
        1) To create new images, call with action='generate' and a descriptive prompt.
        2) To modify an existing image, call with action='edit', image_url='<URL>', and prompt describing changes.
        3) To inspect available providers/models, call with action='list'.
        4) To inspect progress and retrieve the final image URL, call with action='status' and task_id='<ID>'.
        """
        if action == "list":
            return engine.list_models()
        if action == "status":
            return await _status(task_id)
        if action == "edit":
            if not image_url or not image_url.strip():
                return json.dumps({"error": "image_url is required when action=edit"}, ensure_ascii=False)
            if not prompt.strip():
                return json.dumps({"error": "prompt is required when action=edit"}, ensure_ascii=False)
            try:
                image_bytes, image_mime, image_size = await _fetch_image_bytes(
                    image_url.strip(),
                    allow_private_networks=allow_private_networks,
                )
            except Exception as exc:
                logger.warning("Failed to fetch image_url: %s", exc)
                return json.dumps(
                    {"error": "Failed to fetch image_url"},
                    ensure_ascii=False,
                )
            mask_bytes = None
            if mask_url and mask_url.strip():
                try:
                    mask_bytes, _, _ = await _fetch_image_bytes(
                        mask_url.strip(),
                        allow_private_networks=allow_private_networks,
                    )
                except Exception as exc:
                    logger.warning("Failed to fetch mask_url: %s", exc)
                    return json.dumps(
                        {"error": "Failed to fetch mask_url"},
                        ensure_ascii=False,
                    )
            return await engine.edit_image(
                image_bytes,
                prompt,
                mask=mask_bytes,
                size=size,
                n=n,
                image_mime=image_mime,
                image_size_bytes=image_size,
            )
        if not prompt.strip():
            return '{"error": "prompt is required when action=generate"}'
        return await _enqueue_generate(
            prompt,
            size=size,
            quality=quality,
            style=style,
            n=n,
            reference_image_urls=reference_image_urls,
        )

    if async_config is not None:
        image_tool.description = (
            f"{engine.tool_description} "
            "Workflow: 1) Call action='generate' with prompt to start and receive task_id. "
            "2) Call action='status' with task_id to inspect progress and retrieve the final image URL upon completion. "
            "3) Call action='edit' with image_url and prompt to modify an existing image. "
            "4) Call action='list' to inspect available providers/models."
        )
    else:
        image_tool.description = engine.tool_description
    return image_tool
