"""Media download exceptions.

[INPUT]
- (none)

[OUTPUT]
- MediaDownloadError: Base exception for media download failures.
- SizeExceededError: Raised when downloaded media exceeds size limit.
- ContentTypeError: Raised when content-type is not allowed.
- SSRFError: Raised when SSRF validation fails.
- ValidationError: Raised when image generation request validation fails.

[POS]
Media download exceptions.
"""

from __future__ import annotations


class MediaDownloadError(Exception):
    """Base exception for media download failures."""


class SizeExceededError(MediaDownloadError):
    """Raised when downloaded media exceeds size limit."""

    def __init__(self, downloaded_bytes: int, max_bytes: int, url: str):
        self.downloaded_bytes = downloaded_bytes
        self.max_bytes = max_bytes
        self.url = url
        super().__init__(f"Media size {downloaded_bytes} bytes exceeds limit {max_bytes} bytes: {url[:100]}")


class ContentTypeError(MediaDownloadError):
    """Raised when content-type is not allowed."""

    def __init__(self, content_type: str, allowed_types: frozenset[str], url: str):
        self.content_type = content_type
        self.allowed_types = allowed_types
        self.url = url
        super().__init__(f"Content-type '{content_type}' not in allowed types {allowed_types}: {url[:100]}")


class SSRFError(MediaDownloadError):
    """Raised when SSRF validation fails."""

    def __init__(self, reason: str, url: str):
        self.reason = reason
        self.url = url
        super().__init__(f"SSRF validation failed: {reason} (url={url[:100]})")


class ValidationError(MediaDownloadError):
    """Raised when custom validator fails."""

    def __init__(self, validator_name: str, reason: str, url: str):
        self.validator_name = validator_name
        self.reason = reason
        self.url = url
        super().__init__(f"{validator_name} validation failed: {reason} (url={url[:100]})")
