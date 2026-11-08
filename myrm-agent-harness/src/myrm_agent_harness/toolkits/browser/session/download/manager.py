"""Download manager — file download detection, judging and processing.

[INPUT]
- patchright.async_api::Page, Download (POS: Patchright page and download objects)
- navigation.ssrf_guard::BrowserNavigationBlockedError (POS: the refusal a download address verifier raises)
- utils.page_health::abort_pending_navigation (POS: bounded browser and page health primitives)
- utils.timeout::is_timeout_error (POS: single source for unified timeout exception detection across browser toolkit)
- session.download.config::DownloadConfig (POS: where a download manager keeps files, how much, for how long, and which kinds)
- session.download.storage::DownloadStorage, sanitize_filename (POS: the disk side of the download domain: unique names, quota, and the browser's finished copy written below a trusted root without following a link)
- session.download.records::DownloadResult, DownloadRefusal, DownloadMark, DownloadActivity (POS: the shapes the download manager, its storage and the session-level download APIs exchange)
- session.download.errors::DownloadError (POS: the error of a download that is not kept)
- session.network::safe_preview (POS: credential-masked text cut to a limit)
- utils.url_utils::sanitize_url_for_error (POS: a URL as an error or log line may show it: scheme, host and path, no credentials, query or fragment)

[OUTPUT]
- DownloadManager: file download manager; admits, judges and saves every download, requested or page-started, or discards it

[POS]
Browser file download manager. Single responsibility: listen for, judge, process, and record file downloads; the disk
side (names, quota, the copy, and never writing through a link) is ``DownloadStorage``. It holds no URL policy: the
session hands it the verifier that judges the address a download came from, and the config hands it the policy that
says whether a page may save a file on its own. A download that is refused, cut short while it is judged, or not kept
is cancelled and deleted (the caller waits a bounded time for that; the cleanup carries on after the caller stops
waiting). A page-started download is admitted and judged at once, without waiting for a free slot, and one that is not
kept is remembered with its reason so the agent can be told. A slot (``max_concurrent_downloads``) bounds only the
saves in progress: a request still waiting for its page to start a download, and a download being judged, hold none.
A report of what happened after a mark waits only for the downloads the page started after it. Once a download is processed the browser keeps nothing of it: the saved copy is the only one left. A download_url
request takes the first download its page starts, one request at a time per page; every other download of that page
goes through the page path, and one the request claimed but never took goes there when the request ends, so no
download is kept without a verdict. A request that gives up stops the navigation it started (one bounded, best-effort
protocol command), so an answer still on its way does not land after the request has returned. Log lines name a
download's URL without its query, fragment or credentials.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.url_utils import sanitize_url_for_error

from ...navigation.ssrf_guard import BrowserNavigationBlockedError
from ...utils.page_health import abort_pending_navigation
from ...utils.timeout import is_timeout_error
from ..network import safe_preview
from .config import DownloadConfig
from .errors import DownloadError
from .records import DownloadActivity, DownloadMark, DownloadRefusal, DownloadResult
from .storage import DownloadStorage, sanitize_filename

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

# How many refused downloads are remembered to tell the agent; a page can start them without end.
_REFUSALS_KEPT = 5

# Why a page-started download was not kept, as the agent is told: no address in any of them. A file the page built
# itself has no address for download_url to request, so it is not pointed there.
_NOT_ADMITTED = "the permission policy does not let a page save files on its own; request the file with download_url"
_NOT_ADMITTED_UNADDRESSED = (
    "the permission policy does not let a page save files on its own; this file was built by the page itself, "
    "so there is no address to request with download_url"
)
_ADDRESS_REFUSED = "the address it came from is blocked by the network safety policy"
_NOT_PROCESSED = "it could not be processed"

_LOGGED_URL_LENGTH = 80
_LOGGED_REASON_LENGTH = 200
# A hostile page chooses the URL, so it is cut to this before it is masked: masking costs the event loop as long as
# the redactor takes on the text. Wider than the logged length, so a credential that starts inside the logged part
# is masked whole before the logged cut.
_MASKED_URL_LENGTH = 256


def _loggable_url(url: str) -> str:
    """A download URL as a log line may show it: scheme, host and path, with what looks like a credential masked."""
    return safe_preview(sanitize_url_for_error(url, max_length=_MASKED_URL_LENGTH), _LOGGED_URL_LENGTH)


def _loggable_reason(refusal: BrowserNavigationBlockedError, url: str, logged_url: str) -> str:
    """A refusal's reason as a log line may show it: the whole URL the guard quotes in it becomes ``logged_url``."""
    reason = str(refusal)
    if url:  # an empty URL would match between every two characters
        reason = reason.replace(url, logged_url)
    return safe_preview(reason, _LOGGED_REASON_LENGTH)


@dataclass(eq=False)
class _DownloadRequest:
    """A ``download_url`` call waiting for the first download its page starts."""

    page_key: int
    claimed: Download | None = None  # the download the page listener left to this request
    taken: Download | None = None  # the download the request itself received, and judges


class DownloadManager:
    """File download manager.

    Monitors page download events and processes files with safety checks. ``verify_final_url`` judges the
    address every download came from (the final one, after redirects) before any byte is kept.
    """

    def __init__(self, config: DownloadConfig, *, verify_final_url: AddressVerifier) -> None:
        self._config = config
        self._verify_final_url = verify_final_url
        self._storage = DownloadStorage(config)
        self._downloads: list[DownloadResult] = []
        self._refusals: deque[DownloadRefusal] = deque(maxlen=_REFUSALS_KEPT)
        self._refused_total = 0
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_downloads)
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self._page_started_total = 0
        self._page_started_in_flight: dict[int, asyncio.Task[None]] = {}  # by the order the page started them in
        self._attached_page_ids: set[int] = set()
        self._requests: list[_DownloadRequest] = []
        self._page_locks: dict[int, asyncio.Lock] = {}

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
    def refusals(self) -> tuple[DownloadRefusal, ...]:
        """The latest page-started downloads that were not kept, oldest first."""
        return tuple(self._refusals)

    def mark(self) -> DownloadMark:
        """Where the downloads stand now; ``activity_since`` reports what comes after it."""
        return DownloadMark(saved=len(self._downloads), refused=self._refused_total, started=self._page_started_total)

    async def activity_since(self, mark: DownloadMark) -> DownloadActivity:
        """What was saved or refused since ``mark``, once the downloads the page started after it have settled.

        The wait is bounded by ``download_timeout_s``, as a save is: a verdict still pending would otherwise read as
        no download at all. A download started before the mark is none of this action's business, and a slow one
        would hold up every action that follows it.
        """
        awaited = [task for number, task in self._page_started_in_flight.items() if number >= mark.started]
        if awaited:
            await asyncio.wait(awaited, timeout=self._config.download_timeout_s)
        refused_since = self._refused_total - mark.refused
        return DownloadActivity(
            saved=tuple(self._downloads[mark.saved :]),
            refused=tuple(self._refusals)[-refused_since:] if refused_since else (),
        )

    async def download_url(self, page: Page, url: str, timeout: float | None = None) -> DownloadResult:
        """Actively download a file from a URL.

        While the request waits it takes the first download its page starts; every other download of the page
        goes through the page path as usual. The address the download came from (the final one, after redirects)
        is judged before any byte is kept; a refusal discards the download and propagates. A request that gives up
        stops the navigation it started (one bounded, best-effort protocol command, also when the caller is
        cancelled again), so an answer still on its way does not land after the request has returned.

        Args:
            page: Page to initiate download from
            url: URL to download (admitted by the caller before it gets here)
            timeout: Download timeout in seconds (defaults to config)

        Returns:
            The saved download.

        Raises:
            BrowserNavigationBlockedError: the download came from an address the verifier refused.
            DownloadError: no download started or it was not kept; the reason says which.
        """
        timeout_s = timeout or self._config.download_timeout_s

        try:
            download = await self._take_download(page, url, timeout_s)
            await self._judge(download)
            return await self._process_download(download)
        except BrowserNavigationBlockedError:
            raise
        except DownloadError as failure:
            self._log_not_saved(url, failure)
            raise
        except Exception as e:
            logger.warning(
                "Failed to download URL %s: %s", _loggable_url(url), safe_preview(str(e), _LOGGED_REASON_LENGTH)
            )
            if is_timeout_error(e):
                raise DownloadError(
                    f"no download started within {timeout_s:g} s (the address may open a page instead of a file)"
                ) from e
            raise DownloadError("the browser could not complete the download") from e

    async def _take_download(self, page: Page, url: str, timeout_s: float) -> Download:
        """Navigate ``page`` to ``url`` and take the first download it starts.

        One request at a time per page: the browser reports the page's first download to every request that
        waits on it, so two requests started together would take the same one and leave the other's file to the
        page path. The lock is held until the request has its download, not while that is saved.
        """
        async with self._page_locks.setdefault(id(page), asyncio.Lock()):
            with self._waiting_for_a_download(page) as request:
                download = await self._request_download(page, url, timeout_s * 1000)
                request.taken = download
                return download

    @contextlib.contextmanager
    def _waiting_for_a_download(self, page: Page) -> Iterator[_DownloadRequest]:
        """Let a request take the first download ``page`` starts.

        A download the request claimed but never took (it ended first) goes to the page path.
        """
        request = _DownloadRequest(page_key=id(page))
        self._requests.append(request)
        try:
            yield request
        finally:
            self._requests.remove(request)
            if request.claimed is not None and request.claimed is not request.taken:
                self._spawn_page_download(request.claimed)

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
        """Handle download event from page (sync callback → async task).

        The first download of a page a request waits on is left to that request: the browser reports the same
        download to the request, which judges and saves it. Every other download takes the page path.
        """
        waiting = next((r for r in self._requests if r.page_key == id(download.page) and r.claimed is None), None)
        if waiting is not None:
            waiting.claimed = download
            return
        self._spawn_page_download(download)

    def _spawn_page_download(self, download: Download) -> None:
        """Handle a download the page started itself; its number lets ``activity_since`` skip earlier ones."""
        number = self._page_started_total
        self._page_started_total += 1
        task = self._spawn(self._handle_download_async(download))
        self._page_started_in_flight[number] = task
        task.add_done_callback(lambda _done: self._page_started_in_flight.pop(number, None))

    def _spawn(self, work: Coroutine[None, None, None]) -> asyncio.Task[None]:
        """Run ``work`` as a task held in ``_pending_tasks``: it is not collected midway, and cleanup cancels it."""
        task = asyncio.create_task(work)
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)
        return task

    def _admitted(self, download: Download) -> bool:
        """Whether the policy lets a page save a file on its own; a policy that cannot answer refuses."""
        admit = self._config.admit_page_started
        if admit is None:
            return True
        # A download the page built itself names no address, so the policy judges the page that built it.
        address = download.page.url if download.url.startswith(_UNADDRESSED_SCHEMES) else download.url
        try:
            return admit(address)
        except Exception as e:
            logger.warning(
                "The policy for downloads a page starts failed (%s); the download is refused", type(e).__name__
            )
            return False

    async def _handle_download_async(self, download: Download) -> None:
        """Admit, judge and process a download the page started itself; one that is not kept is noted."""
        try:
            if not self._admitted(download):
                await self._discard(download)
                logger.warning(
                    "Refused a download from %s: the permission policy does not admit downloads a page starts",
                    _loggable_url(download.url),
                )
                self._note_refusal(
                    download,
                    _NOT_ADMITTED_UNADDRESSED if download.url.startswith(_UNADDRESSED_SCHEMES) else _NOT_ADMITTED,
                )
                return
            await self._judge(download)
            await self._process_download(download)
        except BrowserNavigationBlockedError as refusal:
            logged_url = _loggable_url(download.url)
            logger.warning(
                "Refused a download from %s: %s", logged_url, _loggable_reason(refusal, download.url, logged_url)
            )
            self._note_refusal(download, _ADDRESS_REFUSED)
        except DownloadError as failure:
            self._log_not_saved(download.url, failure)
            self._note_refusal(download, failure.reason)
        except Exception as e:
            logger.warning("Download handler error: %s", e)
            self._note_refusal(download, _NOT_PROCESSED)

    def _note_refusal(self, download: Download, reason: str) -> None:
        self._refusals.append(DownloadRefusal(file_name=sanitize_filename(download.suggested_filename), reason=reason))
        self._refused_total += 1

    @staticmethod
    def _log_not_saved(url: str, failure: DownloadError) -> None:
        detail = f" ({safe_preview(failure.detail, _LOGGED_REASON_LENGTH)})" if failure.detail else ""
        logger.warning("Download from %s not saved: %s%s", _loggable_url(url), failure.reason, detail)

    async def _process_download(self, download: Download) -> DownloadResult:
        """Save a judged download and record it; the browser's own copy is released however that ends.

        The browser keeps every download it accepted in its temp dir until the context closes, also after the
        storage copied it, and keeps pulling a body after a save gave up. Discarding ends both. Only the save holds
        a slot: judging and discarding need none, so a refusal never queues behind downloads that are running.

        Raises:
            DownloadError: the download is not kept (see ``DownloadStorage.save``).
        """
        try:
            async with self._semaphore:
                result = await self._storage.save(download)
            self._downloads.append(result)
            logger.info("Downloaded: %s (%d bytes) → %s", result.file_name, result.file_size, result.path)
            return result
        finally:
            await self._discard(download)
