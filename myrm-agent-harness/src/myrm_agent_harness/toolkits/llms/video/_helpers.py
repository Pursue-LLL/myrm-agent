"""Internal helpers for video generation — validation, retryability, truncation.

[OUTPUT]
- is_retryable: Decide whether an exception is retryable based on type name
- safe_truncate: Truncate long error messages with indicator
- validate_video_content: Magic-bytes validation to reject non-video responses

[POS]
Used by generator.py for retry logic, error formatting, and content validation.
"""

from __future__ import annotations

from myrm_agent_harness.utils.mime_types import is_video_content

from .models import VideoGenerationError

_ERROR_MSG_MAX_LEN = 500

_NON_RETRYABLE_NAMES = frozenset(
    {
        "AuthenticationError",
        "BadRequestError",
        "ModerationBlockedError",
        "NotFoundError",
        "ValueError",
    }
)


def is_retryable(exc: Exception) -> bool:
    """True if the exception type is NOT in the known non-retryable set."""
    return type(exc).__name__ not in _NON_RETRYABLE_NAMES


def safe_truncate(msg: str, max_len: int = _ERROR_MSG_MAX_LEN) -> str:
    """Truncate message to max_len, appending '... [truncated]' if shortened."""
    if len(msg) <= max_len:
        return msg
    return msg[:max_len] + "... [truncated]"


def validate_video_content(
    data: bytes,
    provider_id: str,
    model_id: str,
) -> None:
    """Validate video data via magic bytes to catch non-video responses."""
    if not is_video_content(data):
        head_hex = data[:16].hex(" ")
        raise VideoGenerationError(
            f"Invalid video content from {provider_id}/{model_id}: {len(data)} bytes, "
            f"unrecognized format (header: {head_hex})"
        )
