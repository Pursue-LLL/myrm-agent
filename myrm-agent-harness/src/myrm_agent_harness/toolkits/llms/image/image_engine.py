"""Synchronous image editing and model listing for Agent integration.

[INPUT]
- generator::ImageGenerator (POS: Core generation/editing engine)
- models::{ImageGenerationConfig, ImageGenerationError, ImageResult} (POS: Data types)
- types::get_profile, list_profiles (POS: Model capability lookup)
- validator::ImageValidator, ValidationError (POS: Pre-call validation that rejects invalid image generation requests before they reach the remote API.)

[OUTPUT]
- ImageGenerationTools: LangChain-compatible tool provider for Agent integration

[POS]
Tool wrapper that exposes ImageGenerator's synchronous actions to Agent use:
  - edit: Image editing with optional mask (one image, answered in the call)
  - list: Discover available models and their capabilities
Text-to-image generation is asynchronous and lives in ``async_image_engine``; this wrapper never generates.
Pre-validates every edit through the 3-layer ImageValidator.
"""

from __future__ import annotations

import asyncio
import json
import logging

from .generator import ImageGenerator
from .models import (
    ImageGenerationConfig,
    ImageGenerationError,
    ImageResult,
)
from .types import (
    get_profile,
    list_profiles,
)
from .validator import (
    ImageValidator,
    ValidationError,
)

logger = logging.getLogger(__name__)


class ImageGenerationTools:
    """Image editing and model listing for Agent integration.

    Wraps ImageGenerator and provides callable interfaces
    that return structured results for downstream consumption.
    Supports two actions: edit, list.
    """

    def __init__(self, config: ImageGenerationConfig) -> None:
        self._generator = ImageGenerator(config)
        self._config = config
        self._validator = ImageValidator()

    @property
    def generator(self) -> ImageGenerator:
        """Access the underlying generator (for metrics export)."""
        return self._generator

    async def edit_image(
        self,
        image: bytes,
        prompt: str,
        *,
        mask: bytes | None = None,
        size: str | None = None,
        image_mime: str | None = None,
        image_size_bytes: int | None = None,
        cancellation_event: asyncio.Event | None = None,
    ) -> str:
        """Edit an image based on a text prompt.

        Args:
            image: Source image data (PNG, < 4MB).
            prompt: Text description of the desired edit.
            mask: Optional mask image (transparent areas indicate edit regions).
            size: Output image dimensions.
            image_mime: MIME type of the input image (for validation).
            image_size_bytes: Size of input image in bytes (for validation).
            cancellation_event: Set to cancel editing.

        Returns:
            JSON string with the edited image reference and metadata.
        """
        profile = get_profile(self._config.model)
        try:
            self._validator.validate_edit(
                prompt,
                profile=profile,
                image_mime=image_mime,
                image_size_bytes=image_size_bytes,
                size=size,
            )
        except ValidationError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

        try:
            result = await self._generator.edit(
                image,
                prompt,
                mask=mask,
                size=size,
                cancellation_event=cancellation_event,
            )
            return _format_result(result, prompt)
        except ImageGenerationError as e:
            logger.error("Image editing failed: %s", e)
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            logger.error("Unexpected error in image editing: %s", e)
            return json.dumps(
                {"error": f"Unexpected error: {type(e).__name__}"},
                ensure_ascii=False,
            )

    def list_models(self) -> str:
        """List all registered image generation models and their capabilities.

        Returns:
            JSON string with model profiles.
        """
        profiles = list_profiles()
        return json.dumps(
            {
                "models": [p.to_dict() for p in profiles],
                "active_model": self._config.model,
                "fallback_models": self._config.fallback_models,
            },
            ensure_ascii=False,
        )


def _format_result(result: ImageResult, prompt: str) -> str:
    """Format an edit result as the same shape an async generation task returns."""
    output: dict[str, object] = {"model": result.model, "prompt": result.revised_prompt or prompt}
    reference = result.persisted_ref or result.url
    if reference:
        output["images"] = [{"url": reference, "mime_type": result.mime_type}]
    elif result.b64_json:
        output["image_data"] = f"[base64 image, {len(result.b64_json)} chars]"
    output["latency_ms"] = round(result.latency_ms)
    if result.attempts:
        output["failover_attempts"] = [{"model": a.model, "error": a.error} for a in result.attempts]
    return json.dumps(output, ensure_ascii=False)
