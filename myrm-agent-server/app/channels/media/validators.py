"""Media download validators.

[INPUT]
- (none)

[OUTPUT]
- ValidationContext: Context object passed to validators during download.
- ValidatorProtocol: Protocol for media download validators.
- SSRFValidator: Validates URL against SSRF attacks.
- SizeLimitValidator: Validates downloaded size against limit.
- ContentTypeValidator: Validates content-type against allowed types.

[POS]
Media download validators.
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx
from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf

from .exceptions import ContentTypeError, SizeExceededError, SSRFError, ValidationError

logger = logging.getLogger(__name__)


class ValidationContext:
    """Context object passed to validators during download."""

    def __init__(
        self,
        url: str,
        http_client: httpx.AsyncClient,
        response: httpx.Response | None = None,
        downloaded_bytes: int = 0,
        data: bytes | None = None,
    ):
        self.url = url
        self.http_client = http_client
        self.response = response
        self.downloaded_bytes = downloaded_bytes
        self.data = data


class ValidatorProtocol(Protocol):
    """Protocol for media download validators.

    Validators can inspect the URL, HTTP response, or downloaded data
    and raise exceptions if validation fails.
    """

    async def validate(self, context: ValidationContext) -> None:
        """Validate the download.

        Args:
            context: Validation context with URL, response, and data.

        Raises:
            ValidationError: If validation fails.
        """
        ...


class SSRFValidator:
    """Validates URL against SSRF attacks."""

    async def validate(self, context: ValidationContext) -> None:
        """Validate URL for SSRF safety."""
        result = await async_validate_url_for_ssrf(context.url)
        if not result.safe:
            raise SSRFError(result.error or "SSRF validation failed", context.url)


class SizeLimitValidator:
    """Validates downloaded size against limit."""

    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes

    async def validate(self, context: ValidationContext) -> None:
        """Validate downloaded size."""
        if context.downloaded_bytes > self.max_bytes:
            raise SizeExceededError(
                context.downloaded_bytes,
                self.max_bytes,
                context.url,
            )


class ContentTypeValidator:
    """Validates content-type against allowed types."""

    def __init__(self, allowed_types: frozenset[str]):
        self.allowed_types = allowed_types

    async def validate(self, context: ValidationContext) -> None:
        """Validate content-type from HTTP response."""
        if context.response is None:
            return

        content_type = (context.response.headers.get("content-type") or "").split(";")[0].strip()

        if not content_type:
            raise ValidationError(
                "ContentTypeValidator",
                "Missing content-type header",
                context.url,
            )

        if content_type not in self.allowed_types:
            raise ContentTypeError(content_type, self.allowed_types, context.url)


class MagicBytesValidator:
    """Validates file type using magic bytes (file signatures)."""

    # Common file signatures (magic bytes)
    SIGNATURES: dict[str, list[bytes]] = {
        "image/png": [b"\x89PNG\r\n\x1a\n"],
        "image/jpeg": [b"\xff\xd8\xff"],
        "image/gif": [b"GIF87a", b"GIF89a"],
        "image/webp": [b"RIFF", b"WEBP"],  # WEBP follows RIFF format
        "video/mp4": [b"\x00\x00\x00\x18ftypmp4", b"\x00\x00\x00\x1cftypiso"],
        "application/pdf": [b"%PDF"],
    }

    def __init__(self, expected_types: frozenset[str] | None = None):
        self.expected_types = expected_types

    async def validate(self, context: ValidationContext) -> None:
        """Validate file type using magic bytes."""
        if context.data is None or len(context.data) < 12:
            return

        # Extract first 12 bytes for signature matching
        header = context.data[:12]

        # Try to match against known signatures
        detected_type: str | None = None
        for mime_type, signatures in self.SIGNATURES.items():
            for signature in signatures:
                if header.startswith(signature):
                    detected_type = mime_type
                    break
            if detected_type:
                break

        if detected_type is None:
            logger.warning(
                "MagicBytesValidator: Unknown file signature (url=%s, header=%s)",
                context.url[:100],
                header.hex(),
            )
            return

        if self.expected_types and detected_type not in self.expected_types:
            raise ValidationError(
                "MagicBytesValidator",
                f"File signature indicates '{detected_type}' but expected {self.expected_types}",
                context.url,
            )
