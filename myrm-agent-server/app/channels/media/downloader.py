"""Core media downloader with streaming, retry, cache, and metrics.

[INPUT]
- (none)

[OUTPUT]
- MediaDownloadResult: Result of a media download operation.
- MediaDownloader: Async media downloader with streaming, validation, retry,...

[POS]
Core media downloader with streaming, retry, cache, and metrics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from .cache import CacheBackendProtocol, LRUMemoryCache, url_to_cache_key
from .config import MediaDownloadConfig
from .exceptions import MediaDownloadError
from .progress import ProgressCallback
from .retry import RetryPolicy, retry_with_policy
from .validators import (
    ContentTypeValidator,
    MagicBytesValidator,
    SizeLimitValidator,
    SSRFValidator,
    ValidationContext,
    ValidatorProtocol,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaDownloadResult:
    """Result of a media download operation.

    Attributes:
        success: Whether download succeeded.
        data: Downloaded data bytes (None if failed).
        content_type: Content-Type from response headers (None if failed).
        error: Exception if failed (None if succeeded).
        url: The URL that was downloaded.
        size_bytes: Size of downloaded data in bytes.
        cached: Whether result was served from cache.
        duration_seconds: Time taken for download (excluding cache hit).
    """

    success: bool
    data: bytes | None
    content_type: str | None
    error: Exception | None
    url: str
    size_bytes: int
    cached: bool = False
    duration_seconds: float = 0.0


class MediaDownloader:
    """Async media downloader with streaming, validation, retry, cache, and metrics.

    Features:
    - Streaming download with size limit validation
    - SSRF, content-type, and magic bytes validation
    - Automatic retry with exponential backoff
    - Optional LRU memory cache
    - Progress callbacks for UI updates
    - Batch concurrent downloads with limit
    - Metrics/telemetry integration

    Example:
        ```python
        downloader = MediaDownloader()

        # Simple download
        result = await downloader.download("https://example.com/image.png")
        if result.success:
            print(f"Downloaded {result.size_bytes} bytes")

        # With config
        config = MediaDownloadConfig(max_size_bytes=50 * 1024 * 1024)  # 50MB
        result = await downloader.download(url, config=config)

        # With progress callback
        async def on_progress(downloaded, total):
            if total:
                print(f"Progress: {downloaded / total * 100:.1f}%")

        result = await downloader.download(url, progress_callback=on_progress)

        # Batch download
        urls = ["url1", "url2", "url3"]
        results = await downloader.download_many(urls, max_concurrent=5)
        ```
    """

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        cache: CacheBackendProtocol | None = None,
        enable_default_cache: bool = True,
    ):
        """Initialize MediaDownloader.

        Args:
            http_client: Optional httpx client. If None, creates a default client.
            cache: Optional cache backend. If None and enable_default_cache=True,
                uses LRUMemoryCache.
            enable_default_cache: Whether to enable default LRU cache. Default: True.
        """
        self._http: httpx.AsyncClient | None = http_client
        self._owns_http = http_client is None

        if cache is not None:
            self._cache: CacheBackendProtocol | None = cache
        elif enable_default_cache:
            self._cache = LRUMemoryCache()
        else:
            self._cache = None

    async def __aenter__(self) -> MediaDownloader:
        """Async context manager entry."""
        if self._http is None:
            self._http = httpx.AsyncClient()
        return self

    async def __aexit__(self, *_: object) -> None:
        """Async context manager exit."""
        if self._owns_http and self._http is not None:
            await self._http.aclose()

    async def download(
        self,
        url: str,
        *,
        config: MediaDownloadConfig | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> MediaDownloadResult:
        """Download a single media file.

        Args:
            url: The URL to download.
            config: Optional download configuration. Uses defaults if None.
            progress_callback: Optional progress callback for UI updates.

        Returns:
            MediaDownloadResult with download status and data.
        """
        config = config or MediaDownloadConfig()
        start_time = time.time()

        # Check cache first
        if self._cache is not None:
            cache_key = url_to_cache_key(url)
            cached = await self._cache.get(cache_key)
            if cached:
                data, content_type = cached
                logger.debug("Cache hit for url=%s (size=%d bytes)", url[:100], len(data))
                return MediaDownloadResult(
                    success=True,
                    data=data,
                    content_type=content_type,
                    error=None,
                    url=url,
                    size_bytes=len(data),
                    cached=True,
                    duration_seconds=time.time() - start_time,
                )

        # Download with retry
        try:
            if config.enable_retry:
                retry_policy = RetryPolicy(max_retries=config.max_retries)
                result = await retry_with_policy(
                    self._download_impl,
                    url,
                    config,
                    progress_callback,
                    policy=retry_policy,
                )
            else:
                result = await self._download_impl(url, config, progress_callback)

            # Cache successful download
            if result.success and self._cache is not None and result.data:
                cache_key = url_to_cache_key(url)
                await self._cache.set(cache_key, result.data, result.content_type or "")

            return result

        except Exception as exc:
            duration = time.time() - start_time
            logger.warning(
                "Download failed for url=%s after %.2fs: %s",
                url[:100],
                duration,
                exc,
            )
            return MediaDownloadResult(
                success=False,
                data=None,
                content_type=None,
                error=exc,
                url=url,
                size_bytes=0,
                cached=False,
                duration_seconds=duration,
            )

    async def _download_impl(
        self,
        url: str,
        config: MediaDownloadConfig,
        progress_callback: ProgressCallback | None,
    ) -> MediaDownloadResult:
        """Internal download implementation with streaming and validation."""
        if self._http is None:
            raise RuntimeError("HTTP client not initialized (use async context manager)")

        start_time = time.time()

        # Build validators
        validators: list[ValidatorProtocol] = []

        if config.validate_ssrf:
            validators.append(SSRFValidator())

        if config.max_size_bytes:
            validators.append(SizeLimitValidator(config.max_size_bytes))

        if config.allowed_content_types:
            validators.append(ContentTypeValidator(config.allowed_content_types))
            validators.append(MagicBytesValidator(config.allowed_content_types))

        # Validate URL (SSRF) and resolve pinned request target
        url_context = ValidationContext(url=url, http_client=self._http)
        for validator in validators:
            if isinstance(validator, SSRFValidator):
                await validator.validate(url_context)

        # Prepare HTTP request
        headers = dict(config.headers or {})
        request_url = url
        stream_headers = headers

        # If proxy is configured, create a temporary client with proxy
        # (httpx.stream() doesn't accept proxies parameter)
        http_client = self._http
        temp_client = None
        if config.proxy:
            temp_client = httpx.AsyncClient(proxy=config.proxy)
            http_client = temp_client

        if config.validate_ssrf:
            from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError, async_pin_url
            from myrm_agent_harness.core.security.http.secure_fetch import (
                SecureHttpTarget,
                resolve_secure_http_target,
            )

            try:
                if config.follow_redirects:
                    target = await resolve_secure_http_target(
                        http_client,
                        url,
                        headers=stream_headers,
                    )
                else:
                    pinned_url, pin_headers = await async_pin_url(url)
                    target = SecureHttpTarget(
                        logical_url=url,
                        request_url=pinned_url,
                        headers={**stream_headers, **pin_headers},
                        method="GET",
                    )
            except SSRFSecurityError as exc:
                from .exceptions import SSRFError

                raise SSRFError(str(exc), url) from exc

            request_url = target.request_url
            stream_headers = target.headers

        try:
            # Start streaming download (redirects resolved above when validate_ssrf=True)
            async with http_client.stream(
                "GET",
                request_url,
                headers=stream_headers,
                timeout=config.timeout_seconds,
                follow_redirects=False,
            ) as response:
                # Check HTTP status
                if response.status_code >= 400:
                    raise MediaDownloadError(f"HTTP {response.status_code}: {url[:100]}")

                # Validate response headers (content-type)
                total_bytes = int(response.headers.get("content-length", 0)) or None
                content_type = (response.headers.get("content-type") or "").split(";")[0].strip()

                response_context = ValidationContext(
                    url=url,
                    http_client=self._http,
                    response=response,
                )

                for validator in validators:
                    if isinstance(validator, ContentTypeValidator):
                        await validator.validate(response_context)

                # Notify progress start
                if progress_callback:
                    await progress_callback.on_start(url, total_bytes)

                # Stream download with size validation
                chunks: list[bytes] = []
                downloaded_bytes = 0

                async for chunk in response.aiter_bytes(config.chunk_size_bytes):
                    chunks.append(chunk)
                    downloaded_bytes += len(chunk)

                    # Validate size limit during streaming
                    size_context = ValidationContext(
                        url=url,
                        http_client=self._http,
                        downloaded_bytes=downloaded_bytes,
                    )

                    for validator in validators:
                        if isinstance(validator, SizeLimitValidator):
                            await validator.validate(size_context)

                    # Notify progress
                    if progress_callback:
                        await progress_callback.on_progress(downloaded_bytes, total_bytes)

                # Combine chunks
                data = b"".join(chunks)

                # Validate final data (magic bytes)
                data_context = ValidationContext(
                    url=url,
                    http_client=self._http,
                    response=response,
                    downloaded_bytes=len(data),
                    data=data,
                )

                for validator in validators:
                    if isinstance(validator, MagicBytesValidator):
                        await validator.validate(data_context)

                # Notify complete
                if progress_callback:
                    await progress_callback.on_complete(url, len(data), content_type)

                duration = time.time() - start_time
                logger.debug(
                    "Downloaded %d bytes from %s in %.2fs",
                    len(data),
                    url[:100],
                    duration,
                )

                return MediaDownloadResult(
                    success=True,
                    data=data,
                    content_type=content_type or "application/octet-stream",
                    error=None,
                    url=url,
                    size_bytes=len(data),
                    cached=False,
                    duration_seconds=duration,
                )
        finally:
            # Clean up temporary HTTP client
            if temp_client:
                await temp_client.aclose()

    async def download_many(
        self,
        urls: list[str],
        *,
        config: MediaDownloadConfig | None = None,
        max_concurrent: int = 5,
    ) -> list[MediaDownloadResult]:
        """Download multiple URLs concurrently with concurrency limit.

        Args:
            urls: List of URLs to download.
            config: Optional download configuration for all URLs.
            max_concurrent: Maximum number of concurrent downloads. Default: 5.

        Returns:
            List of MediaDownloadResult in same order as input URLs.
        """
        import asyncio

        results: list[MediaDownloadResult | None] = [None] * len(urls)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def download_with_semaphore(index: int, url: str) -> None:
            async with semaphore:
                results[index] = await self.download(url, config=config)

        tasks = [download_with_semaphore(i, url) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)

        return [r for r in results if r is not None]
