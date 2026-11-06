"""File download APIs of BrowserSession.

[INPUT]
- session_host::SessionHost (POS: typed contract of the host attributes; provides the download manager and tab controller)
- session.download_manager::DownloadResult (POS: one saved download)

[OUTPUT]
- BrowserSessionDownloadMixin: download_url, check_and_download_pdf, list_downloads, last_download, download_enabled

[POS]
Download API of BrowserSession over the optional DownloadManager: an explicit download and the PDF auto-download act
on the active page; the read-side accessors answer from the manager and stay empty when download support is not
configured. Listed after the interaction mixin and before the network mixin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .session_host import SessionHost

if TYPE_CHECKING:
    from .download_manager import DownloadResult


class BrowserSessionDownloadMixin(SessionHost):
    async def download_url(self, url: str, timeout: float | None = None) -> DownloadResult | None:
        """Download a file from a URL.

        Args:
            url: URL to download
            timeout: Timeout in seconds (defaults to config)

        Returns:
            DownloadResult if successful, None otherwise
        """
        if self._download_manager is None:
            raise RuntimeError("Download support not enabled. Pass download_config to BrowserSession.")
        await self._ensure_components()
        page = self._tab_controller.get_active_page()
        return await self._download_manager.download_url(page, url, timeout)

    async def check_and_download_pdf(self) -> DownloadResult | None:
        """Check if current page is a PDF and auto-download it."""
        if self._download_manager is None:
            return None
        await self._ensure_components()
        page = self._tab_controller.get_active_page()
        return await self._download_manager.check_and_download_pdf(page)

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
