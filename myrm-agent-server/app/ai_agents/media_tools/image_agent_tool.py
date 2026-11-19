"""[INPUT]
- myrm_agent_harness.toolkits.llms.image.image_engine::ImageGenerationTools (POS: edit one image / list models)
- myrm_agent_harness.toolkits.llms.image.async_image_engine::AsyncImageGenerationTools (POS: one-task-per-image enqueue)
- myrm_agent_harness.toolkits.llms.image.models::ImageGenerationConfig (POS: shared engine config)
- myrm_agent_harness.toolkits.llms.media_inputs::resolve_media_inputs (POS: the single reference resolver)
- myrm_agent_harness.utils.mime_types::sniff_image_mime (POS: image container detection)
- app.ai_agents.media_tools.input_policy::build_media_input_policy (POS: reference-resolution policy)
- app.ai_agents.media_tools.task_results (POS: shared error, started-tasks and status results)
- app.tasks.task_payload_crypto::seal_task_payload_secrets (POS: payload secret sealing)

[OUTPUT]
- create_image_generation_tool(): LangChain BaseTool adapter for image generation

[POS]
LangChain adapter of the image engines. ``generate`` enqueues one background task per image (``n`` tasks) and answers
with the task list; ``edit`` answers in the call; ``status`` and ``list`` read the queue and the model catalog. Every
failure is an explicit error result, and a parameter that belongs to another action is refused instead of dropped.
``quality`` is sent on the OpenAI-compatible wire only (``openai_chat``, ``azure_openai``), for generation and edit
alike; Gemini, Stability and MiniMax requests do not carry it.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from typing import Literal

from langchain_core.tools import BaseTool, tool
from myrm_agent_harness.toolkits.llms.image.async_image_engine import AsyncImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.image_engine import ImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.llms.media_inputs import MediaInputError, resolve_media_inputs
from myrm_agent_harness.toolkits.llms.media_task_types import TASK_TYPE_IMAGE_GENERATE
from myrm_agent_harness.utils.mime_types import sniff_image_mime
from pydantic import BaseModel, Field

from app.ai_agents.media_tools.input_policy import build_media_input_policy
from app.ai_agents.media_tools.task_results import (
    media_task_status_result,
    media_task_store,
    started_tasks_result,
    tool_error,
)
from app.tasks.task_payload_crypto import seal_task_payload_secrets

logger = logging.getLogger(__name__)

_TOOL_DESCRIPTION = (
    "Generate or edit images. Each generated image is a background task whose result appears in the chat by itself, "
    "so never repeat its media:// address in your reply. "
    "action='generate': new images from a text prompt; reference_image_urls steer the style or content. "
    "action='edit': change one existing image as the prompt says (optional mask_url); answers in the call and needs a "
    "model that edits images. "
    "action='status': state and result of a task_id, which is also how to get the media:// address of an earlier image. "
    "action='list': the available models and what they support."
)


class ImageToolInput(BaseModel):
    action: Literal["generate", "edit", "list", "status"] = Field(
        default="generate",
        description="Action to perform: 'generate', 'edit', 'list' or 'status'.",
    )
    prompt: str = Field(
        default="",
        description="Detailed description of the image to generate, or the changes to make for edit (required for generate and edit).",
    )
    size: str | None = Field(
        default=None,
        description=(
            "Image size as WIDTHxHEIGHT, both sides divisible by 16 and aspect ratio at most 3:1 "
            "(e.g. '1536x1024', '2048x1152'). Never pass aspect ratios such as '16:9'."
        ),
    )
    quality: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Rendering quality; omit it to let the model decide.",
    )
    n: int = Field(
        default=1,
        ge=1,
        le=4,
        description="How many images to generate (1-4); each one is its own task. Not for edit.",
    )
    reference_image_urls: list[str] | None = Field(
        default=None,
        description="Reference images for generate: media:// references from earlier results, workspace file paths or http(s) URLs.",
    )
    image_url: str | None = Field(
        default=None,
        description="Image to modify when action='edit': a media:// reference, workspace file path or http(s) URL.",
    )
    mask_url: str | None = Field(
        default=None,
        description="Optional mask for action='edit', same forms as image_url; transparent areas are regenerated.",
    )
    task_id: str | None = Field(
        default=None,
        description="Task ID from an earlier generate result (required when action='status').",
    )


# The action that owns each parameter of a single action (prompt, size, quality and n are shared and not listed).
_PARAMETER_OWNER = {
    "reference_image_urls": "generate",
    "image_url": "edit",
    "mask_url": "edit",
    "task_id": "status",
}


def _passed(value: str | Sequence[str] | None) -> bool:
    """Whether the model gave a value; an empty string or list means the same as leaving the parameter out."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return any(item.strip() for item in value)


def _foreign_parameter(action: str, **given: str | Sequence[str] | None) -> str | None:
    """The error for the first parameter the model passed although another action owns it, or ``None``.

    Acting on the call anyway would drop the parameter silently and return an image that differs from what was asked.
    """
    for name, value in given.items():
        owner = _PARAMETER_OWNER[name]
        if owner != action and _passed(value):
            return f"{name} is a parameter of action={owner}, not of action={action}; use that action or leave it out"
    return None


def create_image_generation_tool(
    config: ImageGenerationConfig,
    *,
    allowed_roots: Sequence[str] = (),
    task_user_id: str = "default",
    agent_id: str | None = None,
    chat_id: str | None = None,
) -> BaseTool:
    """Build ``image_tool`` for the image model in ``config``.

    ``allowed_roots`` are the workspace folders the agent's file references may point into.
    """
    editor = ImageGenerationTools(config)
    policy = build_media_input_policy(allowed_roots)

    async def _generate(
        prompt: str,
        *,
        size: str | None,
        quality: str | None,
        n: int,
        reference_image_urls: list[str] | None,
    ) -> str:
        if not prompt.strip():
            return tool_error("prompt is required when action=generate")
        try:
            task_store = media_task_store()
        except RuntimeError as exc:
            logger.warning("Task store unavailable for image generation: %s", exc)
            return tool_error("Task store unavailable")

        enqueuer = AsyncImageGenerationTools(config, task_store, payload_postprocessor=seal_task_payload_secrets)
        references = [ref.strip() for ref in reference_image_urls or [] if ref.strip()]
        task_ids = [
            await enqueuer.generate_image(
                prompt,
                size=size,
                quality=quality,
                reference_image_urls=references or None,
                allowed_roots=allowed_roots,
                user_id=task_user_id,
                agent_id=agent_id,
                chat_id=chat_id,
            )
            for _ in range(n)
        ]
        return started_tasks_result(
            TASK_TYPE_IMAGE_GENERATE,
            task_ids,
            message="Generation started; each image appears in the chat when it is ready.",
        )

    async def _edit(
        prompt: str,
        *,
        size: str | None,
        quality: str | None,
        n: int,
        image_url: str | None,
        mask_url: str | None,
    ) -> str:
        if not image_url or not image_url.strip():
            return tool_error("image_url is required when action=edit")
        if not prompt.strip():
            return tool_error("prompt is required when action=edit")
        if n > 1:
            return tool_error("edit returns one image per call; call it again for another variation, or use action=generate")
        try:
            (image,) = await resolve_media_inputs([image_url], "image", policy, field_name="image_url")
            mask: bytes | None = None
            if mask_url and mask_url.strip():
                # A mask carries its meaning in its transparency, which the downsizing hook would flatten.
                (mask,) = await resolve_media_inputs([mask_url], "image", replace(policy, image_hook=None), field_name="mask_url")
        except MediaInputError as exc:
            return tool_error(str(exc))
        return await editor.edit_image(
            image,
            prompt,
            mask=mask,
            size=size,
            quality=quality,
            image_mime=sniff_image_mime(image),
            image_size_bytes=len(image),
        )

    @tool("image_tool", args_schema=ImageToolInput)
    async def image_tool(
        action: Literal["generate", "edit", "list", "status"] = "generate",
        prompt: str = "",
        size: str | None = None,
        quality: Literal["low", "medium", "high"] | None = None,
        n: int = 1,
        reference_image_urls: list[str] | None = None,
        image_url: str | None = None,
        mask_url: str | None = None,
        task_id: str | None = None,
    ) -> str:
        """Generate, edit, poll the status of, or list images."""
        if action == "list":
            return editor.list_models()
        if action == "status":
            return await media_task_status_result(task_id)
        foreign = _foreign_parameter(
            action,
            reference_image_urls=reference_image_urls,
            image_url=image_url,
            mask_url=mask_url,
            task_id=task_id,
        )
        if foreign:
            return tool_error(foreign)
        if action == "edit":
            return await _edit(prompt, size=size, quality=quality, n=n, image_url=image_url, mask_url=mask_url)
        return await _generate(
            prompt,
            size=size,
            quality=quality,
            n=n,
            reference_image_urls=reference_image_urls,
        )

    image_tool.description = _TOOL_DESCRIPTION
    return image_tool
