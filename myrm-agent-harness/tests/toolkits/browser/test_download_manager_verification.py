"""DownloadManager.download_url judges where a download came from before it keeps a byte.

The context's request filter is never handed a redirect hop, so the address a download finally came from is the only
place its origin can be judged. These tests pin the manager's side of that: the address is judged before anything is
saved, a refusal cancels the download, and the page's own listener stands down while the request waits so it cannot
save what the verifier refuses. The real-Chromium proof is ``test_download_url_integration``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session.download_manager import (
    _START_NAVIGATION_JS,
    DownloadConfig,
    DownloadManager,
)

_FINAL_URL = "http://127.0.0.1:9/secret.txt"
_REQUEST_URL = "https://public.example/go"


class _ExpectDownload:
    """Stand-in for ``page.expect_download``: the scripted download is ready as soon as the block ends."""

    def __init__(self, download: MagicMock) -> None:
        self.value: asyncio.Future[MagicMock] = asyncio.get_running_loop().create_future()
        self.value.set_result(download)

    async def __aenter__(self) -> _ExpectDownload:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _download(page: MagicMock, url: str) -> MagicMock:
    download = MagicMock()
    download.url = url
    download.page = page
    download.suggested_filename = "secret.txt"
    download.failure = AsyncMock(return_value=None)
    download.cancel = AsyncMock()

    async def save_as(path: str) -> None:
        Path(path).write_bytes(b"payload")

    download.save_as = AsyncMock(side_effect=save_as)
    return download


def _requesting_page(final_url: str = _FINAL_URL) -> tuple[MagicMock, MagicMock]:
    """A page whose download request ends in a download from ``final_url``, and that download."""
    page = MagicMock()
    page.evaluate = AsyncMock()
    download = _download(page, final_url)
    page.expect_download = lambda **_kw: _ExpectDownload(download)
    return page, download


async def _let_listener_tasks_finish(manager: DownloadManager) -> None:
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


@pytest.fixture
def manager(downloads_dir: Path) -> DownloadManager:
    return DownloadManager(DownloadConfig(downloads_dir=downloads_dir, download_timeout_s=5.0))


class TestFinalAddressVerification:
    @pytest.mark.asyncio
    async def test_the_url_reaches_the_page_as_an_argument_never_as_script_text(self, manager: DownloadManager) -> None:
        page, _ = _requesting_page("https://example.com/a.txt")
        url = "https://example.com/a'b\"c.txt?x=1"

        await manager.download_url(page, url)

        page.evaluate.assert_awaited_once_with(_START_NAVIGATION_JS, url)
        assert url not in _START_NAVIGATION_JS

    @pytest.mark.asyncio
    async def test_the_final_address_is_judged_before_anything_is_saved(self, manager: DownloadManager) -> None:
        page, download = _requesting_page("https://cdn.example/a.txt")
        saves_at_verification: list[int] = []

        async def verify(_url: str) -> None:
            saves_at_verification.append(download.save_as.await_count)

        result = await manager.download_url(page, _REQUEST_URL, verify_final_url=verify)

        assert saves_at_verification == [0]
        assert result is not None
        assert result.url == "https://cdn.example/a.txt"
        assert len(manager.downloads) == 1

    @pytest.mark.asyncio
    async def test_a_refused_final_address_cancels_the_download_and_saves_nothing(
        self, manager: DownloadManager, downloads_dir: Path
    ) -> None:
        page, download = _requesting_page()
        verify = AsyncMock(side_effect=BrowserNavigationBlockedError("SSRF blocked: 127.0.0.1 is loopback"))

        with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
            await manager.download_url(page, _REQUEST_URL, verify_final_url=verify)

        verify.assert_awaited_once_with(_FINAL_URL)
        download.cancel.assert_awaited_once()
        download.save_as.assert_not_awaited()
        assert manager.downloads == []
        assert list(downloads_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_a_verifier_that_cannot_judge_fails_closed(
        self, manager: DownloadManager, downloads_dir: Path
    ) -> None:
        page, download = _requesting_page()
        verify = AsyncMock(side_effect=RuntimeError("resolver unavailable"))

        assert await manager.download_url(page, _REQUEST_URL, verify_final_url=verify) is None

        download.cancel.assert_awaited_once()
        download.save_as.assert_not_awaited()
        assert list(downloads_dir.iterdir()) == []


class TestListenerStandDown:
    @pytest.mark.asyncio
    async def test_the_page_listener_leaves_the_download_to_the_waiting_request(self, manager: DownloadManager) -> None:
        page, download = _requesting_page("https://cdn.example/a.txt")
        page.evaluate.side_effect = lambda *_args: manager._on_download(download)  # the event the listener sees

        result = await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert result is not None
        assert download.save_as.await_count == 1
        assert len(manager.downloads) == 1

    @pytest.mark.asyncio
    async def test_a_download_of_another_page_is_still_saved_by_its_listener(self, manager: DownloadManager) -> None:
        page, _ = _requesting_page("https://cdn.example/a.txt")
        elsewhere = _download(MagicMock(), "https://cdn.example/elsewhere.txt")
        page.evaluate.side_effect = lambda *_args: manager._on_download(elsewhere)

        await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert sorted(result.url for result in manager.downloads) == [
            "https://cdn.example/a.txt",
            "https://cdn.example/elsewhere.txt",
        ]

    @pytest.mark.asyncio
    async def test_the_listener_resumes_once_the_request_has_ended(self, manager: DownloadManager) -> None:
        page, _ = _requesting_page("https://cdn.example/a.txt")
        await manager.download_url(page, _REQUEST_URL)

        manager._on_download(_download(page, "https://cdn.example/later.txt"))
        await _let_listener_tasks_finish(manager)

        assert [result.url for result in manager.downloads] == [
            "https://cdn.example/a.txt",
            "https://cdn.example/later.txt",
        ]

    @pytest.mark.asyncio
    async def test_the_stand_down_ends_when_the_request_times_out(self, manager: DownloadManager) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock()
        page.expect_download = MagicMock(side_effect=TimeoutError("no download started"))

        assert await manager.download_url(page, _REQUEST_URL) is None

        manager._on_download(_download(page, "https://cdn.example/later.txt"))
        await _let_listener_tasks_finish(manager)
        assert [result.url for result in manager.downloads] == ["https://cdn.example/later.txt"]

    def test_overlapping_requests_on_one_page_stand_down_until_the_last_one_ends(
        self, manager: DownloadManager
    ) -> None:
        page = MagicMock()

        with manager._owning_downloads_of(page):
            with manager._owning_downloads_of(page):
                pass
            assert manager._requesting_pages == {id(page): 1}

        assert manager._requesting_pages == {}

    def test_the_stand_down_ends_even_when_the_block_raises(self, manager: DownloadManager) -> None:
        page = MagicMock()

        with pytest.raises(RuntimeError), manager._owning_downloads_of(page):
            raise RuntimeError("request failed")

        assert manager._requesting_pages == {}
