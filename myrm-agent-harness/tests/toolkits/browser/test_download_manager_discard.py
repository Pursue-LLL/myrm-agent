"""What the manager does with a download it will not keep, and with a request that stops waiting.

Judging an address is pinned in ``test_download_manager_verification``. Here: a refused download is cancelled while
its body is still arriving and deleted once it finished, and so is one whose judgement was cut short; the caller waits
a bounded time for that, and the work goes on when the caller stops waiting (it is cancelled, or the browser is slow).
Once a download is processed the browser keeps nothing of it, whichever way the processing ended. A request that stops
waiting stops the navigation it started, even when it is cancelled again while stopping, so the answer still on its
way is not left to land unjudged, and a download it had claimed but not taken goes to the page path. The
real-Chromium proof is ``test_download_url_integration`` (requests) and ``test_download_page_started_integration``
(downloads a page starts itself).
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session import download_manager
from myrm_agent_harness.toolkits.browser.session.download_config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download_manager import DownloadManager
from tests.toolkits.browser._download_doubles import DEFAULT_FINAL_URL, download_of, requesting_page, waiting_page

_REQUEST_URL = "https://public.example/go"


@pytest.fixture(autouse=True)
def abort_navigation() -> Iterator[AsyncMock]:
    """The real call needs a live page; replaced, a test can tell when a request stopped its navigation."""
    with patch.object(download_manager, "abort_pending_navigation", new_callable=AsyncMock) as abort:
        yield abort


@pytest.fixture
def verify() -> AsyncMock:
    """The address verifier of the manager under test: it allows every address until a test scripts a refusal."""
    return AsyncMock()


@pytest.fixture
def manager(tmp_path: Path, verify: AsyncMock) -> DownloadManager:
    config = DownloadConfig(downloads_dir=tmp_path / "downloads", download_timeout_s=5.0)
    return DownloadManager(config, verify_final_url=verify)


def _verifier_that_never_answers(verify: AsyncMock) -> asyncio.Event:
    """Make the verifier take for ever; the returned event is set once it has been asked."""
    asked = asyncio.Event()

    async def never_answers(_url: str) -> None:
        asked.set()
        await asyncio.sleep(3600)

    verify.side_effect = never_answers
    return asked


async def _never_finishes(_path: str) -> None:
    await asyncio.sleep(3600)


class TestGivingUp:
    """A request that stops waiting stops the navigation it started, so an answer still on its way does not land."""

    @pytest.mark.asyncio
    async def test_a_request_that_times_out_stops_its_navigation(
        self, manager: DownloadManager, abort_navigation: AsyncMock
    ) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock()
        page.expect_download = MagicMock(side_effect=TimeoutError("no download started"))

        assert await manager.download_url(page, _REQUEST_URL) is None

        abort_navigation.assert_awaited_once_with(page)

    @pytest.mark.asyncio
    async def test_a_request_whose_page_fails_stops_its_navigation(
        self, manager: DownloadManager, abort_navigation: AsyncMock
    ) -> None:
        page = waiting_page()
        page.evaluate.side_effect = RuntimeError("page crashed")

        assert await manager.download_url(page, _REQUEST_URL) is None

        abort_navigation.assert_awaited_once_with(page)

    @pytest.mark.asyncio
    async def test_a_cancelled_request_stops_its_navigation_and_stays_cancelled(
        self, manager: DownloadManager, abort_navigation: AsyncMock
    ) -> None:
        page = waiting_page()
        request = asyncio.create_task(manager.download_url(page, _REQUEST_URL))
        await asyncio.sleep(0.01)

        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request

        abort_navigation.assert_awaited_once_with(page)

    @pytest.mark.asyncio
    async def test_a_cancelled_request_hands_the_download_it_claimed_to_the_page_path(
        self, manager: DownloadManager
    ) -> None:
        """A download the page started for the request to take must not go unjudged when the request is gone."""
        page = waiting_page()
        claimed = download_of(page, "https://cdn.example/claimed.txt")
        navigating = asyncio.Event()

        def start_the_download(*_args: object) -> None:
            manager._on_download(claimed)
            navigating.set()

        page.evaluate.side_effect = start_the_download
        request = asyncio.create_task(manager.download_url(page, _REQUEST_URL))
        await asyncio.wait_for(navigating.wait(), timeout=1.0)

        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)

        assert [result.url for result in manager.downloads] == [claimed.url]

    @pytest.mark.asyncio
    async def test_a_second_cancellation_does_not_cut_the_stop_short(
        self, manager: DownloadManager, abort_navigation: AsyncMock
    ) -> None:
        navigating, stopping, release, stopped = (asyncio.Event() for _ in range(4))

        async def stop_once_released(_page: MagicMock) -> None:
            stopping.set()
            await release.wait()
            stopped.set()

        abort_navigation.side_effect = stop_once_released
        page = waiting_page()
        page.evaluate.side_effect = lambda *_args: navigating.set()
        request = asyncio.create_task(manager.download_url(page, _REQUEST_URL))
        await asyncio.wait_for(navigating.wait(), timeout=1.0)
        request.cancel()
        await asyncio.wait_for(stopping.wait(), timeout=1.0)
        request.cancel()  # the stop is under way: this one must not interrupt it
        with pytest.raises(asyncio.CancelledError):
            await request

        release.set()
        await asyncio.wait_for(stopped.wait(), timeout=1.0)

    @pytest.mark.asyncio
    async def test_a_request_that_got_its_download_leaves_the_navigation_alone(
        self, manager: DownloadManager, verify: AsyncMock, abort_navigation: AsyncMock
    ) -> None:
        page, _ = requesting_page("https://cdn.example/a.txt")
        assert await manager.download_url(page, _REQUEST_URL) is not None

        verify.side_effect = BrowserNavigationBlockedError("SSRF blocked")
        page, _ = requesting_page()
        with pytest.raises(BrowserNavigationBlockedError):
            await manager.download_url(page, _REQUEST_URL)

        abort_navigation.assert_not_awaited()


class TestDiscard:
    @pytest.mark.asyncio
    async def test_it_cancels_a_body_still_arriving_and_deletes_one_that_finished(
        self, manager: DownloadManager
    ) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        calls: list[str] = []
        download.cancel.side_effect = lambda: calls.append("cancel")
        download.delete.side_effect = lambda: calls.append("delete")

        await manager._discard(download)

        assert calls == ["cancel", "delete"]

    @pytest.mark.asyncio
    async def test_a_delete_that_fails_after_the_cancel_is_not_an_error(self, manager: DownloadManager) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        download.delete.side_effect = RuntimeError("Download.delete: canceled")  # what Chromium answers

        await manager._discard(download)

        download.cancel.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_cancel_that_fails_still_deletes(self, manager: DownloadManager) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        download.cancel.side_effect = RuntimeError("target closed")

        await manager._discard(download)

        download.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_download_that_never_answers_cannot_hold_the_caller(self, manager: DownloadManager) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)

        async def hang() -> None:
            await asyncio.sleep(3600)

        download.cancel.side_effect = hang

        with patch.object(download_manager, "_DISCARD_TIMEOUT_S", 0.05):
            started = time.monotonic()
            await manager._discard(download)

        assert time.monotonic() - started < 1.0
        await manager.cleanup()  # the discard that never ends is cancelled with the manager
        assert manager._pending_tasks == set()

    @pytest.mark.asyncio
    async def test_a_browser_slower_than_the_wait_still_gets_the_whole_discard(
        self, manager: DownloadManager, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Cancelling a call to the browser aborts it there, so the work must not be dropped when the wait ends."""
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        deleted = asyncio.Event()

        async def slow_cancel() -> None:
            await asyncio.sleep(0.2)

        download.cancel.side_effect = slow_cancel
        download.delete.side_effect = deleted.set

        with patch.object(download_manager, "_DISCARD_TIMEOUT_S", 0.05), caplog.at_level(logging.WARNING):
            await manager._discard(download)

        assert not deleted.is_set()  # the caller was released while the browser was still cancelling
        assert "taking longer" in caplog.text
        await asyncio.wait_for(deleted.wait(), timeout=2.0)

    @pytest.mark.asyncio
    async def test_a_caller_that_is_cancelled_does_not_cut_the_cleanup_short(self, manager: DownloadManager) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        deleted = asyncio.Event()

        async def delete() -> None:
            await asyncio.sleep(0.05)
            deleted.set()

        download.delete.side_effect = delete

        discarding = asyncio.create_task(manager._discard(download))
        await asyncio.sleep(0.01)
        discarding.cancel()
        with pytest.raises(asyncio.CancelledError):
            await discarding

        await asyncio.wait_for(deleted.wait(), timeout=1.0)


class TestCancelledJudgement:
    """A judgement that is cut short leaves the download undecided, and an undecided download is not kept."""

    @pytest.mark.asyncio
    async def test_a_page_started_download_is_discarded_when_its_judgement_is_cancelled(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        asked = _verifier_that_never_answers(verify)

        manager._on_download(download)
        await asyncio.wait_for(asked.wait(), timeout=1.0)
        handlers = list(manager._pending_tasks)
        for handler in handlers:
            handler.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.save_as.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_requested_download_is_discarded_when_its_judgement_is_cancelled(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        page, download = requesting_page()
        asked = _verifier_that_never_answers(verify)

        request = asyncio.create_task(manager.download_url(page, _REQUEST_URL))
        await asyncio.wait_for(asked.wait(), timeout=1.0)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.save_as.assert_not_awaited()


class TestWhatTheBrowserKeepsOfAProcessedDownload:
    """Once a download is processed the browser keeps nothing of it, whichever way the processing ended."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "outcome",
        ["saved", "disallowed-extension", "save-timeout", "save-failure", "too-large", "nothing-written"],
    )
    async def test_the_browsers_copy_is_released_exactly_once(
        self, tmp_path: Path, verify: AsyncMock, outcome: str
    ) -> None:
        download = download_of(MagicMock(), DEFAULT_FINAL_URL)
        timeout_s, limit_mb = 5.0, 100
        match outcome:
            case "disallowed-extension":
                download.suggested_filename = "tool.exe"
            case "save-timeout":
                timeout_s = 0.05
                download.save_as = AsyncMock(side_effect=_never_finishes)
            case "save-failure":
                download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))
            case "too-large":
                limit_mb = 0
            case "nothing-written":
                download.save_as = AsyncMock()
        config = DownloadConfig(
            downloads_dir=tmp_path / "downloads", download_timeout_s=timeout_s, max_file_size_mb=limit_mb
        )
        manager = DownloadManager(config, verify_final_url=verify)

        await manager._process_download(download)

        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
