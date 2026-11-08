"""DownloadManager judges where a download came from before it keeps a byte, whoever started the download.

The context's request filter is never handed a redirect hop, so the address a download finally came from is the only
place its origin can be judged. These tests pin the manager's side of that: the address of a download the agent asked
for and of one the page started itself is judged before anything is saved, a page-started download is judged at once
whatever else is downloading, a refused download is cancelled and deleted, and a waiting request takes only the first
download its page starts, so every other download of that page is judged by the page path. What a refused or abandoned
download leaves behind is pinned in ``test_download_manager_discard``; the real-Chromium proof is
``test_download_url_integration`` (requests) and ``test_download_page_started_integration`` (downloads a page starts
itself).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.errors import DownloadError
from myrm_agent_harness.toolkits.browser.session.download.manager import _START_NAVIGATION_JS, DownloadManager
from tests.toolkits.browser._download_doubles import DEFAULT_FINAL_URL, download_of, kept_files, requesting_page

_REQUEST_URL = "https://public.example/go"
_MANAGER_LOGGER = "myrm_agent_harness.toolkits.browser.session.download.manager"


async def _let_listener_tasks_finish(manager: DownloadManager) -> None:
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


async def _until_discarded(download: MagicMock) -> None:
    while not download.delete.await_count:
        await asyncio.sleep(0.01)


def _page_starts(manager: DownloadManager, *downloads: MagicMock) -> Callable[..., None]:
    """What a page does when a request navigates it: it starts these downloads, in this order."""

    def start(*_args: object) -> None:
        for download in downloads:
            manager._on_download(download)

    return start


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


@pytest.fixture
def verify() -> AsyncMock:
    """The address verifier of the manager under test: it allows every address until a test scripts a refusal."""
    return AsyncMock()


@pytest.fixture
def manager(downloads_dir: Path, verify: AsyncMock) -> DownloadManager:
    config = DownloadConfig(downloads_dir=downloads_dir, confined_to=downloads_dir.parent, download_timeout_s=5.0)
    return DownloadManager(config, verify_final_url=verify)


class TestFinalAddressVerification:
    @pytest.mark.asyncio
    async def test_the_url_reaches_the_page_as_an_argument_never_as_script_text(self, manager: DownloadManager) -> None:
        page, _ = requesting_page("https://example.com/a.txt")
        url = "https://example.com/a'b\"c.txt?x=1"

        await manager.download_url(page, url)

        page.evaluate.assert_awaited_once_with(_START_NAVIGATION_JS, url)
        assert url not in _START_NAVIGATION_JS

    @pytest.mark.asyncio
    async def test_the_final_address_is_judged_before_anything_is_saved(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        page, download = requesting_page("https://cdn.example/a.txt")
        saves_at_verification: list[int] = []

        async def record(_url: str) -> None:
            saves_at_verification.append(download.path.await_count)

        verify.side_effect = record

        result = await manager.download_url(page, _REQUEST_URL)

        assert saves_at_verification == [0]
        assert result is not None
        assert result.url == "https://cdn.example/a.txt"
        assert len(manager.downloads) == 1

    @pytest.mark.asyncio
    async def test_a_refused_final_address_discards_the_download_and_saves_nothing(
        self, manager: DownloadManager, verify: AsyncMock, downloads_dir: Path
    ) -> None:
        page, download = requesting_page()
        verify.side_effect = BrowserNavigationBlockedError("SSRF blocked: 127.0.0.1 is loopback")

        with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
            await manager.download_url(page, _REQUEST_URL)

        verify.assert_awaited_once_with(DEFAULT_FINAL_URL)
        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.path.assert_not_awaited()
        assert manager.downloads == []
        assert kept_files(downloads_dir) == []

    @pytest.mark.asyncio
    async def test_a_verifier_that_cannot_judge_fails_closed(
        self, manager: DownloadManager, verify: AsyncMock, downloads_dir: Path
    ) -> None:
        page, download = requesting_page()
        verify.side_effect = RuntimeError("resolver unavailable")

        with pytest.raises(DownloadError, match="could not complete the download"):
            await manager.download_url(page, _REQUEST_URL)

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.path.assert_not_awaited()
        assert kept_files(downloads_dir) == []


class TestPageStartedDownloads:
    """A download the page starts itself (a click, a script) is judged like one the agent asked for."""

    @pytest.mark.asyncio
    async def test_the_address_is_judged_before_the_download_is_saved(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        download = download_of(MagicMock(), "https://cdn.example/a.txt")
        saves_at_verification: list[int] = []

        async def record(_url: str) -> None:
            saves_at_verification.append(download.path.await_count)

        verify.side_effect = record

        manager._on_download(download)
        await _let_listener_tasks_finish(manager)

        assert saves_at_verification == [0]
        assert [result.url for result in manager.downloads] == ["https://cdn.example/a.txt"]

    @pytest.mark.asyncio
    async def test_a_refused_download_is_discarded_and_the_refusal_is_logged(
        self, manager: DownloadManager, verify: AsyncMock, downloads_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), f"{DEFAULT_FINAL_URL}?token=hunter2")
        verify.side_effect = BrowserNavigationBlockedError(
            f"SSRF blocked: {DEFAULT_FINAL_URL}?api_key=hunter2 is loopback"
        )
        caplog.set_level(logging.WARNING, logger=_MANAGER_LOGGER)

        manager._on_download(download)
        await _let_listener_tasks_finish(manager)

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.path.assert_not_awaited()
        assert manager.downloads == []
        assert kept_files(downloads_dir) == []
        assert "Refused a download from" in caplog.text
        assert "127.0.0.1:9/secret.txt" in caplog.text
        assert "hunter2" not in caplog.text

    @pytest.mark.asyncio
    async def test_a_download_that_cannot_be_judged_is_discarded(
        self, manager: DownloadManager, verify: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), "https://cdn.example/a.txt")
        verify.side_effect = RuntimeError("resolver unavailable")
        caplog.set_level(logging.WARNING, logger=_MANAGER_LOGGER)

        manager._on_download(download)
        await _let_listener_tasks_finish(manager)

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.path.assert_not_awaited()
        assert manager.downloads == []
        assert "Download handler error" in caplog.text

    @pytest.mark.asyncio
    async def test_a_refused_download_does_not_wait_for_a_free_slot(
        self, downloads_dir: Path, verify: AsyncMock
    ) -> None:
        """Judging needs no slot, so a download to refuse is discarded at once even while every slot is taken."""
        config = DownloadConfig(
            downloads_dir=downloads_dir, confined_to=downloads_dir.parent, max_concurrent_downloads=1
        )
        manager = DownloadManager(config, verify_final_url=verify)
        verify.side_effect = BrowserNavigationBlockedError("SSRF blocked: 127.0.0.1 is loopback")
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)

        async with manager._semaphore:  # the only slot belongs to another download
            manager._on_download(download)
            await asyncio.wait_for(_until_discarded(download), timeout=1.0)

        await _let_listener_tasks_finish(manager)
        download.path.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["blob:https://app.example/6f1c", "data:text/plain;base64,aGk="])
    async def test_a_download_the_page_made_itself_names_no_address_to_judge(
        self, manager: DownloadManager, verify: AsyncMock, url: str
    ) -> None:
        manager._on_download(download_of(MagicMock(), url))
        await _let_listener_tasks_finish(manager)

        verify.assert_not_awaited()
        assert [result.url for result in manager.downloads] == [url]


class TestRequestClaim:
    """A request takes the first download its page starts, the one ``page.expect_download`` resolves with.

    Every other download of the page goes through the page path, so none is saved or kept without a verdict.
    """

    @pytest.mark.asyncio
    async def test_the_request_takes_the_first_download_its_page_starts(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        page, download = requesting_page("https://cdn.example/a.txt")
        page.evaluate.side_effect = _page_starts(manager, download)

        result = await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert result is not None
        assert download.path.await_count == 1
        assert verify.await_count == 1
        assert len(manager.downloads) == 1

    @pytest.mark.asyncio
    async def test_a_second_download_of_the_page_is_judged_and_saved_by_the_page_path(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        page, first = requesting_page("https://cdn.example/a.txt")
        second = download_of(page, "https://cdn.example/b.txt")
        page.evaluate.side_effect = _page_starts(manager, first, second)

        await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert sorted(call.args[0] for call in verify.await_args_list) == [first.url, second.url]
        assert sorted(result.url for result in manager.downloads) == [first.url, second.url]
        assert first.path.await_count == 1
        assert second.path.await_count == 1

    @pytest.mark.asyncio
    async def test_a_second_download_of_the_page_is_refused_like_any_other(
        self, manager: DownloadManager, verify: AsyncMock, downloads_dir: Path
    ) -> None:
        page, first = requesting_page("https://cdn.example/a.txt")
        second = download_of(page, DEFAULT_FINAL_URL)
        page.evaluate.side_effect = _page_starts(manager, first, second)

        async def refuse_the_second(url: str) -> None:
            if url == second.url:
                raise BrowserNavigationBlockedError("SSRF blocked: 127.0.0.1 is loopback")

        verify.side_effect = refuse_the_second

        result = await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert result is not None
        second.cancel.assert_awaited_once()
        second.delete.assert_awaited_once()
        second.path.assert_not_awaited()
        assert [saved.url for saved in manager.downloads] == [first.url]
        assert len(kept_files(downloads_dir)) == 1

    @pytest.mark.asyncio
    async def test_a_download_of_another_page_is_still_saved_by_its_listener(self, manager: DownloadManager) -> None:
        page, _ = requesting_page("https://cdn.example/a.txt")
        elsewhere = download_of(MagicMock(), "https://cdn.example/elsewhere.txt")
        page.evaluate.side_effect = _page_starts(manager, elsewhere)

        await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert sorted(result.url for result in manager.downloads) == [
            "https://cdn.example/a.txt",
            "https://cdn.example/elsewhere.txt",
        ]

    @pytest.mark.asyncio
    async def test_the_page_path_handles_every_download_once_the_request_has_ended(
        self, manager: DownloadManager
    ) -> None:
        page, _ = requesting_page("https://cdn.example/a.txt")
        await manager.download_url(page, _REQUEST_URL)

        manager._on_download(download_of(page, "https://cdn.example/later.txt"))
        await _let_listener_tasks_finish(manager)

        assert [result.url for result in manager.downloads] == [
            "https://cdn.example/a.txt",
            "https://cdn.example/later.txt",
        ]

    @pytest.mark.asyncio
    async def test_the_page_path_handles_every_download_once_a_request_has_timed_out(
        self, manager: DownloadManager
    ) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock()
        page.expect_download = MagicMock(side_effect=TimeoutError("no download started"))

        with pytest.raises(DownloadError, match="no download started within"):
            await manager.download_url(page, _REQUEST_URL)

        manager._on_download(download_of(page, "https://cdn.example/later.txt"))
        await _let_listener_tasks_finish(manager)
        assert [result.url for result in manager.downloads] == ["https://cdn.example/later.txt"]

    @pytest.mark.asyncio
    async def test_the_page_path_handles_every_download_once_a_request_has_been_refused(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        page, _ = requesting_page("https://cdn.example/a.txt")
        verify.side_effect = [BrowserNavigationBlockedError("SSRF blocked"), None]

        with pytest.raises(BrowserNavigationBlockedError):
            await manager.download_url(page, _REQUEST_URL)

        manager._on_download(download_of(page, "https://cdn.example/later.txt"))
        await _let_listener_tasks_finish(manager)
        assert [result.url for result in manager.downloads] == ["https://cdn.example/later.txt"]
