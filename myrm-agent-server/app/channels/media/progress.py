"""Progress callback protocol for media downloads.

[INPUT]
- (none)

[OUTPUT]
- ProgressCallback: Protocol for progress callbacks during media download.
- SimpleProgressCallback: Simple progress callback that only tracks progress percen...
- LoggingProgressCallback: Production-ready logging progress callback.

[POS]
Progress callback protocol for media downloads.
"""

from __future__ import annotations

from typing import Protocol


class ProgressCallback(Protocol):
    """Protocol for progress callbacks during media download.

    Provides complete lifecycle hooks: start, progress, complete, and error.
    All methods are async to allow for async operations (e.g., UI updates via websocket).
    """

    async def on_start(self, url: str, total_bytes: int | None) -> None:
        """Called when download starts.

        Args:
            url: The URL being downloaded.
            total_bytes: Total size in bytes if known from Content-Length header, else None.
        """
        ...

    async def on_progress(self, downloaded_bytes: int, total_bytes: int | None) -> None:
        """Called periodically as download progresses.

        Args:
            downloaded_bytes: Number of bytes downloaded so far.
            total_bytes: Total size in bytes if known, else None.
        """
        ...

    async def on_complete(self, url: str, size_bytes: int, content_type: str) -> None:
        """Called when download completes successfully.

        Args:
            url: The URL that was downloaded.
            size_bytes: Final size in bytes.
            content_type: Content-Type from response headers.
        """
        ...

    async def on_error(self, url: str, error: Exception) -> None:
        """Called when download fails.

        Args:
            url: The URL that failed.
            error: The exception that caused the failure.
        """
        ...


class SimpleProgressCallback:
    """Simple progress callback that only tracks progress percentage.

    Example:
        ```python
        async def on_progress(downloaded, total):
            if total:
                print(f"Progress: {downloaded / total * 100:.1f}%")

        callback = SimpleProgressCallback(on_progress)
        downloader = MediaDownloader()
        await downloader.download(url, progress_callback=callback)
        ```
    """

    def __init__(
        self,
        progress_func: callable[[int, int | None], None] | None = None,
    ):
        self.progress_func = progress_func

    async def on_start(self, url: str, total_bytes: int | None) -> None:
        """No-op."""
        pass

    async def on_progress(self, downloaded_bytes: int, total_bytes: int | None) -> None:
        """Call progress function if provided."""
        if self.progress_func:
            await self.progress_func(downloaded_bytes, total_bytes)

    async def on_complete(self, url: str, size_bytes: int, content_type: str) -> None:
        """No-op."""
        pass

    async def on_error(self, url: str, error: Exception) -> None:
        """No-op."""
        pass


class LoggingProgressCallback:
    """Production-ready logging progress callback.

    Logs download lifecycle events (start, progress milestones, complete, error) using Python logging.
    Ideal for server applications, background tasks, and debugging.

    Features:
    - Logs only at key milestones (25%, 50%, 75%, 100%) to avoid log spam
    - Uses INFO level for normal flow, WARNING for errors
    - Includes URL, size, content-type, and error details
    - Configurable logger name for namespace isolation

    Example:
        ```python
        from app.channels.media import (
            MediaDownloader,
            LoggingProgressCallback,
        )

        # Use default logger (app.channels.media.progress)
        callback = LoggingProgressCallback()

        # Or use custom logger name
        callback = LoggingProgressCallback(logger_name="my_app.downloads")

        downloader = MediaDownloader()
        result = await downloader.download(
            "https://example.com/large-file.mp4",
            progress_callback=callback,
        )
        ```

    Log output:
        INFO  my_app.downloads  Download started: url=https://example.com/file.mp4 total_size=10.5MB
        INFO  my_app.downloads  Download progress: 25% (2.6MB/10.5MB)
        INFO  my_app.downloads  Download progress: 50% (5.2MB/10.5MB)
        INFO  my_app.downloads  Download progress: 75% (7.9MB/10.5MB)
        INFO  my_app.downloads  Download completed: url=https://example.com/file.mp4 size=10.5MB content_type=video/mp4
    """

    _PROGRESS_MILESTONES = [0.25, 0.5, 0.75]  # Log at 25%, 50%, 75%

    def __init__(self, logger_name: str | None = None):
        """Initialize logging progress callback.

        Args:
            logger_name: Custom logger name. Defaults to this module's logger.
        """
        import logging

        self._logger = logging.getLogger(logger_name or __name__)
        self._last_milestone = 0.0

    async def on_start(self, url: str, total_bytes: int | None) -> None:
        """Log download start."""
        if total_bytes:
            size_mb = total_bytes / (1024 * 1024)
            self._logger.info("Download started: url=%s total_size=%.1fMB", url, size_mb)
        else:
            self._logger.info("Download started: url=%s total_size=unknown", url)
        self._last_milestone = 0.0

    async def on_progress(self, downloaded_bytes: int, total_bytes: int | None) -> None:
        """Log download progress at key milestones (25%, 50%, 75%)."""
        if not total_bytes:
            return  # Skip if total size unknown

        progress = downloaded_bytes / total_bytes

        # Check if we've crossed a milestone
        for milestone in self._PROGRESS_MILESTONES:
            if self._last_milestone < milestone <= progress:
                size_mb = total_bytes / (1024 * 1024)
                downloaded_mb = downloaded_bytes / (1024 * 1024)
                self._logger.info(
                    "Download progress: %d%% (%.1fMB/%.1fMB)", int(milestone * 100), downloaded_mb, size_mb
                )
                self._last_milestone = milestone
                break

    async def on_complete(self, url: str, size_bytes: int, content_type: str) -> None:
        """Log download completion."""
        size_mb = size_bytes / (1024 * 1024)
        self._logger.info("Download completed: url=%s size=%.1fMB content_type=%s", url, size_mb, content_type)

    async def on_error(self, url: str, error: Exception) -> None:
        """Log download error."""
        self._logger.warning("Download failed: url=%s error=%s: %s", url, type(error).__name__, error)
