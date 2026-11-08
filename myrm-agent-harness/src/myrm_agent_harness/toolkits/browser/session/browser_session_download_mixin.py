"""File download APIs of BrowserSession.

[INPUT]
- session_host::SessionHost (POS: typed contract of the host attributes; provides the download manager, the navigator and the URL blocklist check)
- navigation.ssrf_guard::canonical_navigation_url (POS: the canonical spelling of a navigation URL, the host every check and Chromium read)
- session.download::DownloadError, DownloadMark, DownloadActivity, DownloadRefusal, DownloadResult (POS: the error of a download that is not kept, and the records a session's downloads are reported in)

[OUTPUT]
- BrowserSessionDownloadMixin: download_url (judged like a navigation to the same URL), _assert_download_final_url_allowed (the verifier the download manager judges every download with), list_downloads, download_refusals, download_mark / downloads_since (what a page-started download came to after a moment), take_unannounced_downloads (what no answer has carried yet), download_enabled

[POS]
Download API of BrowserSession over the optional DownloadManager. An explicit download is a request the browser
makes for the agent, so it is judged as a navigation to the same URL is: canonical spelling, URL blocklist and SSRF
policy before the request, the address the download finally came from afterwards, and the page the tab landed on
when the request ended on a page instead of a file. The address check is the navigator's, applied by the manager
to every download it saves, the ones a page starts itself included. The read-side accessors answer from the
manager and stay empty when download support is not configured. A download that is not kept is an error
(``DownloadError``) with the reason, never a silent ``None``. Listed after the interaction mixin and before
the network mixin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..navigation.ssrf_guard import canonical_navigation_url
from .download import DownloadActivity, DownloadError, DownloadMark
from .session_host import SessionHost

if TYPE_CHECKING:
    from .download import DownloadRefusal, DownloadResult

_NETWORK_URL_PREFIXES = ("http://", "https://")


class BrowserSessionDownloadMixin(SessionHost):
    async def download_url(self, url: str, timeout: float | None = None) -> DownloadResult:
        """Download a file from a URL.

        The URL is judged before the browser is asked for it and again, by the download manager, at the address
        the download finally came from. A request that ends on a page instead of a file leaves the tab there, so
        that page is judged too and a refused one is discarded.

        Args:
            url: Absolute http(s) URL to download
            timeout: Timeout in seconds (defaults to config)

        Returns:
            The saved download.

        Raises:
            BrowserNavigationBlockedError: the URL, the address the download came from or the page it ended on is refused.
            DownloadError: no download started or it was not kept; the reason says which.
            ToolError: the host is on the URL blocklist.
        """
        if self._download_manager is None:
            raise RuntimeError("Download support not enabled. Pass download_config to BrowserSession.")
        target = canonical_navigation_url(url)
        await self._ensure_components()
        self._assert_not_blocklisted(target)
        navigator = self._require_navigator()
        await navigator.admit_download(target)

        page = self._tab_controller.get_active_page()
        url_before = page.url
        try:
            return await self._download_manager.download_url(page, target, timeout)
        except DownloadError:
            if page.url != url_before and page.url.startswith(_NETWORK_URL_PREFIXES):
                await navigator.assert_landed_allowed(page.url, discard_document=True)
            raise

    async def _assert_download_final_url_allowed(self, url: str) -> None:
        """Judge the address a download came from, whichever page started it, with the navigator's policy."""
        await self._require_navigator().assert_landed_allowed(url)

    def list_downloads(self) -> list[DownloadResult]:
        """Get all download results."""
        if self._download_manager is None:
            return []
        return self._download_manager.downloads

    @property
    def download_refusals(self) -> tuple[DownloadRefusal, ...]:
        """The latest downloads a page started that were not kept, with the reason for each."""
        if self._download_manager is None:
            return ()
        return self._download_manager.refusals

    def download_mark(self) -> DownloadMark:
        """Where the downloads stand now; ``downloads_since`` reports what came after it."""
        if self._download_manager is None:
            return DownloadMark()
        return self._download_manager.mark()

    async def downloads_since(self, mark: DownloadMark) -> DownloadActivity:
        """What was saved or refused since ``mark``, once the downloads the page started after it have settled.

        The caller puts the report in its answer, so ``take_unannounced_downloads`` does not hand it over again.
        """
        if self._download_manager is None:
            return DownloadActivity()
        return await self._download_manager.activity_since(mark)

    def take_unannounced_downloads(self) -> DownloadActivity:
        """What the downloads a page started came to since no answer last carried it; handed over once.

        A download can settle after the action that started it was answered, so the next answer carries it.
        """
        if self._download_manager is None:
            return DownloadActivity()
        return self._download_manager.take_unannounced()

    @property
    def download_enabled(self) -> bool:
        """Whether download support is configured."""
        return self._download_manager is not None
