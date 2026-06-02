"""Media download configuration.

[INPUT]
- (none)

[OUTPUT]
- MediaDownloadConfig: Configuration for media downloads.

[POS]
Media download configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default allowed content types (common media types for IM platforms)
# Includes images, videos, audio, and documents that are typically safe
DEFAULT_ALLOWED_CONTENT_TYPES = frozenset(
    {
        # Images
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        # Videos
        "video/mp4",
        "video/webm",
        "video/quicktime",  # .mov
        # Audio
        "audio/mpeg",  # .mp3
        "audio/ogg",
        "audio/wav",
        # Documents
        "application/pdf",
        "text/plain",
    }
)


@dataclass(frozen=True)
class MediaDownloadConfig:
    """Configuration for media downloads.

    This is an immutable configuration object that controls all aspects
    of media downloading behavior.

    Args:
        max_size_bytes: Maximum file size in bytes. Download aborts if exceeded.
            Default: 10MB. Set to None for no limit.
        allowed_content_types: Set of allowed MIME types (e.g., {"image/png"}).
            Default: DEFAULT_ALLOWED_CONTENT_TYPES (common safe media types).
            Set to None to disable content-type validation and magic bytes checking.
        timeout_seconds: Request timeout in seconds. Default: 30.0.
        follow_redirects: Whether to follow HTTP redirects. Default: True.
        enable_retry: Whether to enable automatic retry on failure. Default: True.
        max_retries: Maximum number of retry attempts. Default: 3.
        chunk_size_bytes: Chunk size for streaming download. Default: 8192.
        validate_ssrf: Whether to validate URL against SSRF attacks. Default: True.
        proxy: HTTP proxy URL (e.g., "http://proxy.example.com:8080"). Default: None.
        headers: Custom HTTP headers to include in requests. Default: None.

    Security notes:
        - MagicBytes validation is automatically enabled when allowed_content_types is set
        - Default allowed_content_types provides defense-in-depth against MIME type spoofing
        - To disable, explicitly set allowed_content_types=None
    """

    max_size_bytes: int | None = 10 * 1024 * 1024  # 10MB
    allowed_content_types: frozenset[str] | None = DEFAULT_ALLOWED_CONTENT_TYPES
    timeout_seconds: float = 30.0
    follow_redirects: bool = True
    enable_retry: bool = True
    max_retries: int = 3
    chunk_size_bytes: int = 8192
    validate_ssrf: bool = True
    proxy: str | None = None
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        """Validate configuration."""
        if self.max_size_bytes is not None and self.max_size_bytes <= 0:
            raise ValueError(f"max_size_bytes must be > 0, got {self.max_size_bytes}")
        if self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {self.timeout_seconds}")
        if self.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {self.max_retries}")
        if self.chunk_size_bytes <= 0:
            raise ValueError(f"chunk_size_bytes must be > 0, got {self.chunk_size_bytes}")
