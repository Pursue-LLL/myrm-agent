"""Scripted pages and downloads for DownloadManager unit tests.

[INPUT]
- unittest.mock (POS: doubles of the patchright page and download objects)

[OUTPUT]
- DEFAULT_FINAL_URL: the address a scripted download comes from unless a test names another
- download_of: a download double that reports an address and saves a fixed body
- requesting_page: a page whose download request ends in a download from a given address, and that download
- waiting_page: a page whose download request is still waiting for a download
- ExpectDownload / NeverDownloads: stand-ins for ``page.expect_download`` of a request that got, or never gets, its download

[POS]
Test support for the download manager's unit tests: the manager only talks to ``page.expect_download``,
``page.evaluate`` and the ``Download`` surface (``url``, ``page``, ``suggested_filename``, ``save_as``, ``failure``,
``cancel``, ``delete``), so these doubles script exactly that surface. The real-Chromium proof is
``test_download_url_integration`` and ``test_download_page_started_integration``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

DEFAULT_FINAL_URL = "http://127.0.0.1:9/secret.txt"


class ExpectDownload:
    """Stand-in for ``page.expect_download``: the scripted download is ready as soon as the block ends."""

    def __init__(self, download: MagicMock) -> None:
        self.value: asyncio.Future[MagicMock] = asyncio.get_running_loop().create_future()
        self.value.set_result(download)

    async def __aenter__(self) -> ExpectDownload:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class NeverDownloads(ExpectDownload):
    """Stand-in for ``page.expect_download`` of a request whose download never starts."""

    def __init__(self) -> None:
        self.value = asyncio.get_running_loop().create_future()


def download_of(page: MagicMock, url: str) -> MagicMock:
    download = MagicMock()
    download.url = url
    download.page = page
    download.suggested_filename = "secret.txt"
    download.failure = AsyncMock(return_value=None)
    download.cancel = AsyncMock()
    download.delete = AsyncMock()

    async def save_as(path: str) -> None:
        Path(path).write_bytes(b"payload")

    download.save_as = AsyncMock(side_effect=save_as)
    return download


def requesting_page(final_url: str = DEFAULT_FINAL_URL) -> tuple[MagicMock, MagicMock]:
    """A page whose download request ends in a download from ``final_url``, and that download."""
    page = MagicMock()
    page.evaluate = AsyncMock()
    download = download_of(page, final_url)
    page.expect_download = lambda **_kw: ExpectDownload(download)
    return page, download


def waiting_page() -> MagicMock:
    """A page whose download request is still waiting for a download."""
    page = MagicMock()
    page.evaluate = AsyncMock()
    page.expect_download = lambda **_kw: NeverDownloads()
    return page
