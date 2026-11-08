"""Scripted pages and downloads for DownloadManager unit tests.

[INPUT]
- unittest.mock (POS: doubles of the patchright page and download objects)

[OUTPUT]
- DEFAULT_FINAL_URL: the address a scripted download comes from unless a test names another
- download_of: a download double that reports an address and a file name, and a finished file holding a body
- finished_file: a file holding a body, as the path the browser reports for a download it has finished
- download_named / REPORT_URL: a download double of a given file name and body from a fixed address
- storage_in: a download storage of a directory, confined to a root and with the quota and limits a test names
- requesting_page: a page whose download request ends in a download from a given address, and that download
- waiting_page: a page whose download request is still waiting for a download
- ExpectDownload / NeverDownloads: stand-ins for ``page.expect_download`` of a request that got, or never gets, its download
- kept_files: the names of the files a downloads directory holds

[POS]
Test support for the download manager's unit tests: the manager only talks to ``page.expect_download``,
``page.evaluate`` and the ``Download`` surface (``url``, ``page``, ``suggested_filename``, ``path``, ``failure``,
``cancel``, ``delete``), so these doubles script exactly that surface. The real-Chromium proof is
``test_download_url_integration`` and ``test_download_page_started_integration``.
"""

from __future__ import annotations

import asyncio
import atexit
import shutil
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.storage import DownloadStorage

DEFAULT_FINAL_URL = "http://127.0.0.1:9/secret.txt"
REPORT_URL = "https://files.example/report.pdf"

# Where the doubles' "browser" keeps the finished files it reports; removed when the interpreter exits.
_BROWSER_TEMP = Path(tempfile.mkdtemp(prefix="download-doubles-"))
atexit.register(shutil.rmtree, _BROWSER_TEMP, ignore_errors=True)


def finished_file(body: bytes) -> Path:
    """A file holding ``body``, as the path the browser reports for a download it has finished."""
    with tempfile.NamedTemporaryFile(dir=_BROWSER_TEMP, delete=False) as file:
        file.write(body)
    return Path(file.name)


def kept_files(directory: Path) -> list[str]:
    """The files a downloads directory holds: none before it exists; the file that makes it ignore itself is no download."""
    if not directory.exists():
        return []
    return sorted(entry.name for entry in directory.iterdir() if entry.name != ".gitignore")


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


def download_of(page: MagicMock, url: str, *, name: str = "secret.txt", body: bytes = b"payload") -> MagicMock:
    download = MagicMock()
    download.url = url
    download.page = page
    download.suggested_filename = name
    download.failure = AsyncMock(return_value=None)
    download.cancel = AsyncMock()
    download.delete = AsyncMock()

    async def path() -> Path:
        return finished_file(body)

    download.path = AsyncMock(side_effect=path)
    return download


def download_named(name: str = "report.pdf", body: bytes = b"data") -> MagicMock:
    """A download of ``body`` from ``REPORT_URL`` that the browser suggests saving as ``name``."""
    return download_of(MagicMock(), REPORT_URL, name=name, body=body)


def storage_in(
    directory: Path,
    *,
    root: Path | None = None,
    max_files: int = 200,
    max_total_mb: int = 1024,
    max_file_size_mb: int = 100,
    download_timeout_s: float = 5.0,
) -> DownloadStorage:
    """The storage of ``directory``, confined to ``root`` (the directory's parent unless given)."""
    return DownloadStorage(
        DownloadConfig(
            downloads_dir=directory,
            confined_to=root or directory.parent,
            max_files=max_files,
            max_total_mb=max_total_mb,
            max_file_size_mb=max_file_size_mb,
            download_timeout_s=download_timeout_s,
        )
    )


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
