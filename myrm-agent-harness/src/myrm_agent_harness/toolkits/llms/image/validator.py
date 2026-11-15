"""Three-layer image edit request validator.

[INPUT]
- types::ModelProfile, editable_model_names (POS: Model capability lookup)

[OUTPUT]
- ImageValidator: Stateless request validator
- ValidationError: Raised when validation fails

[POS]
Pre-call validation that rejects invalid image edit requests
before they reach the remote API.  Three defence layers:
  L1 Prompt   — empty/length/control-char checks
  L2 Capability — request params vs ModelProfile constraints
  L3 Input    — MIME allowlist + file size limit for edit images

Reference inputs are bounded by ``_media_shared.input_resolver`` and provider result downloads by
``models._download_url`` (SSRF-protected through ``core.security.http.secure_fetch.secure_get``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .types import editable_model_names

if TYPE_CHECKING:
    from .types import ModelProfile

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

ALLOWED_MIME_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
    }
)

MAX_INPUT_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


class ValidationError(Exception):
    """Raised when image generation request validation fails."""


class ImageValidator:
    """Stateless three-layer image generation request validator."""

    def validate_edit(
        self,
        prompt: str,
        *,
        profile: ModelProfile | None,
        image_mime: str | None = None,
        image_size_bytes: int | None = None,
        size: str | None = None,
    ) -> None:
        """Validate an edit request.  Raises ``ValidationError``."""
        self._l1_prompt(prompt, profile)
        if profile:
            self._l2_capability(profile, size=size)
        self._l3_input(image_mime, image_size_bytes)

    @staticmethod
    def _l1_prompt(prompt: str, profile: ModelProfile | None) -> None:
        if not prompt or not prompt.strip():
            raise ValidationError("Prompt must not be empty")

        max_len = profile.max_prompt_length if profile else 4000
        if len(prompt) > max_len:
            raise ValidationError(f"Prompt length {len(prompt)} exceeds maximum {max_len}")

        if _CONTROL_CHAR_RE.search(prompt):
            raise ValidationError("Prompt contains invalid control characters")

    @staticmethod
    def _l2_capability(profile: ModelProfile, *, size: str | None) -> None:
        if not profile.supports_edit:
            raise ValidationError(
                f"Model {profile.name} does not support image editing. Models that edit images: "
                f"{', '.join(editable_model_names())}"
            )
        if (
            size
            and profile.allowed_sizes
            and size not in profile.allowed_sizes
            and (not profile.allowed_aspect_ratios or size not in profile.allowed_aspect_ratios)
        ):
            raise ValidationError(
                f"Size '{size}' not supported by {profile.name}. "
                f"Allowed sizes: {sorted(profile.allowed_sizes)}"
                + (f", aspect ratios: {sorted(profile.allowed_aspect_ratios)}" if profile.allowed_aspect_ratios else "")
            )

    @staticmethod
    def _l3_input(
        mime_type: str | None,
        size_bytes: int | None,
    ) -> None:
        if mime_type and mime_type not in ALLOWED_MIME_TYPES:
            raise ValidationError(f"MIME type '{mime_type}' not allowed. Accepted: {sorted(ALLOWED_MIME_TYPES)}")
        if size_bytes is not None and size_bytes > MAX_INPUT_IMAGE_BYTES:
            max_mb = MAX_INPUT_IMAGE_BYTES / (1024 * 1024)
            actual_mb = size_bytes / (1024 * 1024)
            raise ValidationError(f"Input image {actual_mb:.1f}MB exceeds limit of {max_mb:.0f}MB")
