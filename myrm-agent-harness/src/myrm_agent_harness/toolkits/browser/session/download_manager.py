"""Download manager — file download detection, judging and processing.

[INPUT]
- patchright.async_api::Page, Download (POS: Patchright page and download objects)
- navigation.ssrf_guard::BrowserNavigationBlockedError (POS: the refusal a download address verifier raises)
- utils.page_health::abort_pending_navigation (POS: bounded browser and page health primitives)
- session.download_config::DownloadConfig (POS: where a download manager keeps files, how much, for how long, and which kinds)
- core.security.redact::redact_sensitive_text (POS: credential redaction for the text a log line quotes)
- utils.url_utils::sanitize_url_for_error (POS: scheme, host and path of a URL without its query and fragment)

[OUTPUT]
- DownloadManager: file download manager; judges every download, requested or page-started, before saving it
- DownloadResult: immutable download result

[POS]
Browser file download manager. Single responsibility: listen for, judge, process, and record file downloads.
Integrated into BrowserSession as an optional component. It holds no URL policy: the session hands it the
verifier that judges the address a download came from, and a download that is refused, cut short while it is
judged, or not kept is cancelled and deleted (the caller waits a bounded time for that; the cleanup carries on after
the caller stops waiting). A page-started download is judged at once, without waiting for a free slot. Once a
download is processed the browser keeps nothing of it: the saved copy is the only one left. While a download_url
request waits on a page it is the only processor of the page's downloads, and a request that gives up stops the
navigation it started (one bounded, best-effort protocol command), so an answer still on its way does not land
after the request has returned. Log lines name a download's URL without its query, fragment or credentials.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.utils.url_utils import sanitize_url_for_error

from ..navigation.ssrf_guard import BrowserNavigationBlockedError
from ..utils.page_health import abort_pending_navigation
from .download_config import DownloadConfig

if TYPE_CHECKING:
    from patchright.async_api import Download, Page

logger = logging.getLogger(__name__)

# The address travels as an argument, never spliced into the script, so it cannot be read as code.
_START_NAVIGATION_JS = "(target) => { window.location.href = target; }"

# Raises ``BrowserNavigationBlockedError`` for an address a download must not be saved from.
type AddressVerifier = Callable[[str], Awaitable[None]]

# The page produced these itself, so they name no network address to judge.
_UNADDRESSED_SCHEMES = ("blob:", "data:")

_DISCARD_TIMEOUT_S = 2.0

_LOGGED_URL_LENGTH = 80

_FILENAME_SANITIZE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _loggable_url(url: str) -> str:
    """A download URL as a log line may carry it: no query or fragment, credentials masked before the cut."""
    return sanitize_url_for_error(redact_sensitive_text(url), max_length=_LOGGED_URL_LENGTH)


@dataclass(frozen=True)
class DownloadResult:
    """Immutable download result."""

    url: str
    path: str
    file_name: str
    file_size: int
    file_type: str | None = None


class DownloadManager:
    """File download manager.

    Monitors page download events and processes files with safety checks. ``verify_final_url`` judges the
    address every download came from (the final one, after redirects) before any byte is kept.
    """

    def __init__(self, config: DownloadConfig | None = None, *, verify_final_url: AddressVerifier) -> None:
        self._config = config or DownloadConfig()
        self._verify_final_url = verify_final_url
        self._downloads: list[DownloadResult] = []
        self._downloaded_urls: set[str] = set()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_downloads)
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._attached_page_ids: set[int] = set()
        self._requesting_pages: dict[int, int] = {}

        self._config.downloads_dir.mkdir(parents=True, exist_ok=True)

    def attach(self, page: Page) -> None:
        """Attach download listener to a page (idempotent per page instance)."""
        page_id = id(page)
        if page_id in self._attached_page_ids:
            return
        self._attached_page_ids.add(page_id)
        page.on("download", lambda download: self._on_download(download))

    @property
    def downloads(self) -> list[DownloadResult]:
        """Get all download results."""
        return list(self._downloads)

    @property
    def last_download(self) -> DownloadResult | None:
        """Get the most recent download result."""
        return self._downloads[-1] if self._downloads else None

    async def download_url(self, page: Page, url: str, timeout: float | None = None) -> DownloadResult | None:
        """Actively download a file from a URL.

        While the request waits, the page's own download listener stands down, so this call alone decides what
        is saved. The address the download came from (the final one, after redirects) is judged before any byte
        is kept; a refusal discards the download and propagates. A request that gives up stops the navigation it
        started (one bounded, best-effort protocol command, also when the caller is cancelled again), so an
        answer still on its way does not land after the request has returned.

        Args:
            page: Page to initiate download from
            url: URL to download (admitted by the caller before it gets here)
            timeout: Download timeout in seconds (defaults to config)

        Returns:
            DownloadResult if successful, None otherwise

        Raises:
            BrowserNavigationBlockedError: the download came from an address the verifier refused.
        """
        if url in self._downloaded_urls:
            for result in reversed(self._downloads):
                if result.url == url and Path(result.path).exists():
                    return result

        effective_timeout = (timeout or self._config.download_timeout_s) * 1000

        try:
            async with self._semaphore:
                with self._owning_downloads_of(page):
                    download = await self._request_download(page, url, effective_timeout)
                    await self._judge(download)
                    return await self._process_download(download)
        except BrowserNavigationBlockedError:
            raise
        except Exception as e:
            logger.warning("Failed to download URL %s: %s", _loggable_url(url), e)
            return None

    @contextlib.contextmanager
    def _owning_downloads_of(self, page: Page) -> Iterator[None]:
        """Make the caller the only processor of the page's downloads for the duration of the block."""
        key = id(page)
        self._requesting_pages[key] = self._requesting_pages.get(key, 0) + 1
        try:
            yield
        finally:
            remaining = self._requesting_pages[key] - 1
            if remaining:
                self._requesting_pages[key] = remaining
            else:
                del self._requesting_pages[key]

    @staticmethod
    async def _request_download(page: Page, url: str, timeout_ms: float) -> Download:
        """Navigate the page to ``url`` and wait for the download that starts; giving up stops the navigation."""
        try:
            async with page.expect_download(timeout=timeout_ms) as download_info:
                await page.evaluate(_START_NAVIGATION_JS, url)
            return await download_info.value
        except BaseException:
            # Shielded: a second cancellation must not cut the stop short, or the navigation carries on and its
            # answer lands after nobody is waiting for it.
            await asyncio.shield(abort_pending_navigation(page))
            raise

    async def _judge(self, download: Download) -> None:
        """Raise unless the download's address may be saved.

        A refused, unjudgeable or unfinished judgement (the caller was cancelled while it ran) leaves the download
        undecided, and an undecided download is discarded first: the browser would otherwise keep it.
        """
        if download.url.startswith(_UNADDRESSED_SCHEMES):
            return
        try:
            await self._verify_final_url(download.url)
        except (Exception, asyncio.CancelledError):
            await self._discard(download)
            raise

    async def _discard(self, download: Download) -> None:
        """Cancel a download and delete the browser's copy of it, so a body nobody keeps does not outlive the decision.

        Cancelling stops a body still arriving and does nothing once it has finished; deleting removes a finished
        body (a copy saved elsewhere stays) and fails once the download was cancelled. The caller waits at most
        ``_DISCARD_TIMEOUT_S`` but the work carries on when the wait ends: cancelling a call to the browser aborts it
        there and leaves the body behind.
        """

        async def cancel_and_delete() -> None:
            with contextlib.suppress(Exception):
                await download.cancel()
            with contextlib.suppress(Exception):
                await download.delete()

        _, unfinished = await asyncio.wait({self._spawn(cancel_and_delete())}, timeout=_DISCARD_TIMEOUT_S)
        if unfinished:
            logger.warning(
                "Discarding a download is taking longer than %.0f s; it carries on in the background",
                _DISCARD_TIMEOUT_S,
            )

    async def cleanup(self) -> None:
        """Cancel pending tasks and clean up resources."""
        for task in list(self._pending_tasks):
            if not task.done():
                task.cancel()
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)
        self._pending_tasks.clear()

    def _on_download(self, download: Download) -> None:
        """Handle download event from page (sync callback → async task)."""
        if id(download.page) in self._requesting_pages:
            return  # the download_url call waiting on this page judges the download, then saves it
        self._spawn(self._handle_download_async(download))

    def _spawn(self, work: Coroutine[None, None, None]) -> asyncio.Task[None]:
        """Run ``work`` as a task held in ``_pending_tasks``: it is not collected midway, and cleanup cancels it."""
        task = asyncio.create_task(work)
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        return task

    async def _handle_download_async(self, download: Download) -> None:
        """Judge a download the page started itself, then process it."""
        try:
            await self._judge(download)  # needs no slot: a refusal must not queue behind downloads that are running
            async with self._semaphore:
                await self._process_download(download)
        except BrowserNavigationBlockedError as refusal:
            logger.warning(
                "Refused a download from %s: %s",
                _loggable_url(download.url),
                redact_sensitive_text(str(refusal))[:200],
            )
        except Exception as e:
            logger.warning("Download handler error: %s", e)

    async def _process_download(self, download: Download) -> DownloadResult | None:
        """Save a judged download and record it; the browser's own copy is released however that ends.

        The browser keeps every download it accepted in its temp dir until the context closes, also after
        ``save_as`` copied it, and keeps pulling a body after a save gave up. Discarding ends both.

        Args:
            download: Patchright Download object

        Returns:
            DownloadResult if successful, None otherwise
        """
        try:
            return await self._save_download(download)
        finally:
            await self._discard(download)

    async def _save_download(self, download: Download) -> DownloadResult | None:
        """Copy a download into the downloads directory under a unique, sanitized name; None when it is not kept."""
        url = download.url
        suggested = download.suggested_filename

        sanitized = self._sanitize_filename(suggested)
        ext = Path(sanitized).suffix.lower().lstrip(".")
        if ext and ext not in self._config.allowed_extensions:
            logger.info("Skipping download with disallowed extension: .%s", ext)
            return None

        unique_name = self._generate_unique_filename(sanitized)
        target_path = self._config.downloads_dir / unique_name

        try:
            await asyncio.wait_for(
                download.save_as(str(target_path)),
                timeout=self._config.download_timeout_s,
            )
        except TimeoutError:
            logger.warning("Download timed out: %s", _loggable_url(url))
            return None
        except Exception as e:
            failure = await download.failure()
            logger.warning(
                "Download failed for %s: %s (failure=%s)",
                _loggable_url(url),
                e,
                failure,
            )
            return None

        if not target_path.exists():
            logger.warning("Download file not found after save: %s", target_path)
            return None

        file_size = target_path.stat().st_size
        max_bytes = self._config.max_file_size_mb * 1024 * 1024
        if file_size > max_bytes:
            logger.warning(
                "Downloaded file exceeds size limit (%d MB > %d MB), removing: %s",
                file_size // (1024 * 1024),
                self._config.max_file_size_mb,
                unique_name,
            )
            target_path.unlink(missing_ok=True)
            return None

        result = DownloadResult(
            url=url,
            path=str(target_path),
            file_name=unique_name,
            file_size=file_size,
            file_type=ext or None,
        )
        self._downloads.append(result)
        self._downloaded_urls.add(url)

        logger.info("Downloaded: %s (%d bytes) → %s", unique_name, file_size, target_path)
        return result

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """Sanitize filename to prevent directory traversal and invalid characters."""
        name = Path(name).name
        name = _FILENAME_SANITIZE_RE.sub("_", name)
        return name.strip(". ") or "download"

    def _generate_unique_filename(self, name: str) -> str:
        """Generate unique filename using (1), (2), ... pattern."""
        if not (self._config.downloads_dir / name).exists():
            return name
        base, ext = os.path.splitext(name)
        counter = 1
        while (self._config.downloads_dir / f"{base} ({counter}){ext}").exists():
            counter += 1
        return f"{base} ({counter}){ext}"
