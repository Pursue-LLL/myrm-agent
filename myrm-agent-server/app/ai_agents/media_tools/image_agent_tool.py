"""[INPUT]
- myrm_agent_harness.toolkits.llms.image.image_engine::ImageGenerationTools (POS: sync generate/edit/list)
- myrm_agent_harness.toolkits.llms.image.async_image_engine::AsyncImageGenerationTools (POS: async generate enqueue)
- myrm_agent_harness.toolkits.llms.image.models::ImageGenerationConfig (POS: shared engine config)
- myrm_agent_harness.core.security.http.secure_fetch::secure_get (POS: SSRF-protected edit/mask URL fetch)

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
    action: Literal["generate", "edit", "list"] = Field(
        default="generate",
        description='Use "generate" to create images; "edit" to modify an image; "list" for models.',
    )
    prompt: str = Field(
        default="",
        description="Text description (required for generate/edit).",
    )
    size: str | None = Field(default=None, description='Dimensions e.g. "1024x1024" or "16:9".')
    quality: str | None = Field(default=None, description='"standard" or "hd".')
    style: str | None = Field(default=None, description='"vivid" or "natural" (DALL-E 3).')
    n: int = Field(default=1, ge=1, le=4, description="Number of images to generate.")
    reference_image_urls: list[str] | None = Field(
        default=None,
        description="Optional reference image URLs for style transfer or iterative edits.",
    )
    image_url: str | None = Field(
        default=None,
        description="Source image URL for action=edit (HTTP/HTTPS).",
    )
    mask_url: str | None = Field(
        default=None,
        description="Optional mask image URL for action=edit (transparent areas are edited).",
    )


async def _fetch_image_bytes(url: str, *, allow_private_networks: bool = False) -> tuple[bytes, str | None, int]:
    if allow_private_networks:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.get(url)
            response.raise_for_status()
            content_type = response.headers.get("content-type")
            return response.content, content_type, len(response.content)

    from myrm_agent_harness.core.security.http.secure_fetch import secure_get

    response = await secure_get(url, timeout=30.0)
    response.raise_for_status()
    content_type = response.headers.get("content-type")
    body = response.content
    return body, content_type, len(body)


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

    @tool("image_tool", args_schema=ImageToolInput)
    async def image_tool(
        action: Literal["generate", "edit", "list"] = "generate",
        prompt: str = "",
        size: str | None = None,
        quality: str | None = None,
        style: str | None = None,
        n: int = 1,
        reference_image_urls: list[str] | None = None,
        image_url: str | None = None,
        mask_url: str | None = None,
    ) -> str:
        """Generate, edit, or list image generation models."""
        if action == "list":
            return engine.list_models()
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
                return json.dumps(
                    {"error": f"Failed to fetch image_url: {type(exc).__name__}: {exc}"},
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
                    return json.dumps(
                        {"error": f"Failed to fetch mask_url: {type(exc).__name__}: {exc}"},
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

    image_tool.description = engine.tool_description
    return image_tool
