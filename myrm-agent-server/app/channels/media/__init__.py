"""Media download system with streaming, validation, retry, and cache.

This module provides a complete media download system with:
- Streaming download with size limit validation
- SSRF, content-type, and magic bytes validation
- Automatic retry with exponential backoff
- Optional LRU memory cache
- Progress callbacks for UI updates
- Batch concurrent downloads
- Metrics/telemetry integration

Example:
    ```python
    from app.channels.media import (
        MediaDownloader,
        MediaDownloadConfig,
    )

    # Simple download
    async with MediaDownloader() as downloader:
        result = await downloader.download("https://example.com/image.png")
        if result.success:
            print(f"Downloaded {result.size_bytes} bytes")

    # With config
    config = MediaDownloadConfig(max_size_bytes=50 * 1024 * 1024)
    async with MediaDownloader() as downloader:
        result = await downloader.download(url, config=config)
    ```
"""

from .cache import CacheBackendProtocol, LRUMemoryCache, url_to_cache_key
from .config import DEFAULT_ALLOWED_CONTENT_TYPES, MediaDownloadConfig
from .downloader import MediaDownloader, MediaDownloadResult
from .exceptions import (
    ContentTypeError,
    MediaDownloadError,
    SizeExceededError,
    SSRFError,
    ValidationError,
)
from .progress import LoggingProgressCallback, ProgressCallback, SimpleProgressCallback
from .retry import RetryPolicy, retry_with_policy
from .sticker_vision import StickerVisionService, describe_sticker_inbound
from .validators import (
    ContentTypeValidator,
    MagicBytesValidator,
    SizeLimitValidator,
    SSRFValidator,
    ValidationContext,
    ValidatorProtocol,
)
from .video_enrichment import enrich_video_inbound, has_video_attachment

__all__ = [
    # Core
    "MediaDownloader",
    "MediaDownloadConfig",
    "MediaDownloadResult",
    "DEFAULT_ALLOWED_CONTENT_TYPES",
    # Exceptions
    "MediaDownloadError",
    "SizeExceededError",
    "ContentTypeError",
    "SSRFError",
    "ValidationError",
    # Validators
    "ValidatorProtocol",
    "ValidationContext",
    "SSRFValidator",
    "SizeLimitValidator",
    "ContentTypeValidator",
    "MagicBytesValidator",
    # Cache
    "CacheBackendProtocol",
    "LRUMemoryCache",
    "url_to_cache_key",
    # Progress
    "ProgressCallback",
    "SimpleProgressCallback",
    "LoggingProgressCallback",
    # Retry
    "RetryPolicy",
    "retry_with_policy",
    # Sticker Vision
    "StickerVisionService",
    "describe_sticker_inbound",
    # Video Enrichment
    "enrich_video_inbound",
    "has_video_attachment",
]
