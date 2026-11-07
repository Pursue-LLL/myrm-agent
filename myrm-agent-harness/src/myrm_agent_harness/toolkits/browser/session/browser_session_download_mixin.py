"""File download APIs of BrowserSession.

[INPUT]
- session_host::SessionHost (POS: typed contract of the host attributes; provides the download manager, the navigator and the URL blocklist check)
- navigation.ssrf_guard::canonical_navigation_url (POS: the canonical spelling of a navigation URL, the host every check and Chromium read)
- session.download_manager::DownloadResult (POS: one saved download)

[OUTPUT]
- BrowserSessionDownloadMixin: download_url (judged like a navigation to the same URL), list_downloads, last_download, download_enabled

[POS]
Download API of BrowserSession over the optional DownloadManager. An explicit download is a request the browser
makes for the agent, so it is judged as a navigation to the same URL is: canonical spelling, URL blocklist and SSRF
policy before the request, the address the download finally came from afterwards, and the page the tab landed on
when the request ended on a page instead of a file. The read-side accessors answer from the manager and stay
empty when download support is not configured. Listed after the interaction mixin and before the network mixin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..navigation.ssrf_guard import canonical_navigation_url
from .session_host import SessionHost

if TYPE_CHECKING:
    from .download_manager import DownloadResult

_NETWORK_URL_PREFIXES = ("http://", "https://")


class BrowserSessionDownloadMixin(SessionHost):
    async def download_url(self, url: str, timeout: float | None = None) -> DownloadResult | None:
        """Download a file from a URL.

        The URL is judged before the browser is asked for it and again at the address the download finally came
        from. A request that ends on a page instead of a file leaves the tab there, so that page is judged too and
        a refused one is discarded.

        Args:
            url: Absolute http(s) URL to download
            timeout: Timeout in seconds (defaults to config)

        Returns:
            DownloadResult if successful, None otherwise

        Raises:
            BrowserNavigationBlockedError: the URL, the address the download came from or the page it ended on is refused.
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
        result = await self._download_manager.download_url(
            page, target, timeout, verify_final_url=navigator.assert_landed_allowed
        )
        if result is None and page.url != url_before and page.url.startswith(_NETWORK_URL_PREFIXES):
            await navigator.assert_landed_allowed(page.url, discard_document=True)
        return result

    def list_downloads(self) -> list[DownloadResult]:
        """Get all download results."""
        if self._download_manager is None:
            return []
        return self._download_manager.downloads

    @property
    def last_download(self) -> DownloadResult | None:
        """Get the most recent download result, or None."""
        if self._download_manager is None:
            return None
        return self._download_manager.last_download

    @property
    def download_enabled(self) -> bool:
        """Whether download support is configured."""
        return self._download_manager is not None
