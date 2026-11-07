"""DownloadManager judges where a download came from before it keeps a byte, whoever started the download.

The context's request filter is never handed a redirect hop, so the address a download finally came from is the only
place its origin can be judged. These tests pin the manager's side of that: the address of a download the agent asked
for and of one the page started itself is judged before anything is saved, a refused download is cancelled and
deleted, and the page's own listener stands down while a request waits so it cannot save what the verifier refuses.
What a refused or abandoned download leaves behind is pinned in ``test_download_manager_discard``; the real-Chromium
proof is ``test_download_url_integration``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session.download_manager import (
    _START_NAVIGATION_JS,
    DownloadConfig,
    DownloadManager,
)
from tests.toolkits.browser._download_doubles import DEFAULT_FINAL_URL, download_of, requesting_page

_REQUEST_URL = "https://public.example/go"
_MANAGER_LOGGER = "myrm_agent_harness.toolkits.browser.session.download_manager"


async def _let_listener_tasks_finish(manager: DownloadManager) -> None:
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


@pytest.fixture
def verify() -> AsyncMock:
    """The address verifier of the manager under test: it allows every address until a test scripts a refusal."""
    return AsyncMock()


@pytest.fixture
def manager(downloads_dir: Path, verify: AsyncMock) -> DownloadManager:
    config = DownloadConfig(downloads_dir=downloads_dir, download_timeout_s=5.0)
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
            saves_at_verification.append(download.save_as.await_count)

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
        download.save_as.assert_not_awaited()
        assert manager.downloads == []
        assert list(downloads_dir.iterdir()) == []

    @pytest.mark.asyncio
    async def test_a_verifier_that_cannot_judge_fails_closed(
        self, manager: DownloadManager, verify: AsyncMock, downloads_dir: Path
    ) -> None:
        page, download = requesting_page()
        verify.side_effect = RuntimeError("resolver unavailable")

        assert await manager.download_url(page, _REQUEST_URL) is None

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.save_as.assert_not_awaited()
        assert list(downloads_dir.iterdir()) == []


class TestPageStartedDownloads:
    """A download the page starts itself (a click, a script) is judged like one the agent asked for."""

    @pytest.mark.asyncio
    async def test_the_address_is_judged_before_the_download_is_saved(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        download = download_of(MagicMock(), "https://cdn.example/a.txt")
        saves_at_verification: list[int] = []

        async def record(_url: str) -> None:
            saves_at_verification.append(download.save_as.await_count)

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
        download.save_as.assert_not_awaited()
        assert manager.downloads == []
        assert list(downloads_dir.iterdir()) == []
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
        download.save_as.assert_not_awaited()
        assert manager.downloads == []
        assert "Download handler error" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["blob:https://app.example/6f1c", "data:text/plain;base64,aGk="])
    async def test_a_download_the_page_made_itself_names_no_address_to_judge(
        self, manager: DownloadManager, verify: AsyncMock, url: str
    ) -> None:
        manager._on_download(download_of(MagicMock(), url))
        await _let_listener_tasks_finish(manager)

        verify.assert_not_awaited()
        assert [result.url for result in manager.downloads] == [url]


class TestListenerStandDown:
    @pytest.mark.asyncio
    async def test_the_page_listener_leaves_the_download_to_the_waiting_request(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        page, download = requesting_page("https://cdn.example/a.txt")
        page.evaluate.side_effect = lambda *_args: manager._on_download(download)  # the event the listener sees

        result = await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert result is not None
        assert download.save_as.await_count == 1
        assert verify.await_count == 1
        assert len(manager.downloads) == 1

    @pytest.mark.asyncio
    async def test_a_download_of_another_page_is_still_saved_by_its_listener(self, manager: DownloadManager) -> None:
        page, _ = requesting_page("https://cdn.example/a.txt")
        elsewhere = download_of(MagicMock(), "https://cdn.example/elsewhere.txt")
        page.evaluate.side_effect = lambda *_args: manager._on_download(elsewhere)

        await manager.download_url(page, _REQUEST_URL)
        await _let_listener_tasks_finish(manager)

        assert sorted(result.url for result in manager.downloads) == [
            "https://cdn.example/a.txt",
            "https://cdn.example/elsewhere.txt",
        ]

    @pytest.mark.asyncio
    async def test_the_listener_resumes_once_the_request_has_ended(self, manager: DownloadManager) -> None:
        page, _ = requesting_page("https://cdn.example/a.txt")
        await manager.download_url(page, _REQUEST_URL)

        manager._on_download(download_of(page, "https://cdn.example/later.txt"))
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

        manager._on_download(download_of(page, "https://cdn.example/later.txt"))
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
