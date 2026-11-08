"""Download requests on one page take turns, so each takes the download it started and none another's.

The browser reports a page's first download to every request waiting on that page, so two requests started together
would take the same download and leave the other's file to the page path. A request therefore starts its navigation
only once the page's previous request has its download; it does not wait for that download to be saved, and requests on
other pages never wait. The real-Chromium proof is ``test_download_url_integration``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.download import manager as download_manager
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.manager import DownloadManager
from tests.toolkits.browser._download_doubles import ExpectDownload, download_of, finished_file

_FIRST_URL = "https://public.example/first"
_SECOND_URL = "https://public.example/second"


@pytest.fixture(autouse=True)
def _no_navigation_to_stop() -> Iterator[None]:
    with patch.object(download_manager, "abort_pending_navigation", new_callable=AsyncMock):
        yield


@pytest.fixture
def manager(tmp_path: Path) -> DownloadManager:
    config = DownloadConfig(downloads_dir=tmp_path / "downloads", confined_to=tmp_path)
    return DownloadManager(config, verify_final_url=AsyncMock())


def _page_serving(*downloads: MagicMock) -> MagicMock:
    """A page whose download requests are answered with these downloads, one per request, in the order they are made."""
    page = MagicMock()
    page.evaluate = AsyncMock()
    served = list(downloads)
    page.expect_download = lambda **_kw: ExpectDownload(served.pop(0))
    return page


def _holding_first_navigation(page: MagicMock) -> tuple[list[str], asyncio.Event, asyncio.Event]:
    """Make the page's first navigation wait until the returned gate opens; the other event says it has started."""
    started: list[str] = []
    first_started, gate = asyncio.Event(), asyncio.Event()

    async def navigate(_script: str, url: str) -> None:
        started.append(url)
        if len(started) == 1:
            first_started.set()
            await gate.wait()

    page.evaluate = AsyncMock(side_effect=navigate)
    return started, first_started, gate


class TestTakingTurns:
    @pytest.mark.asyncio
    async def test_a_request_navigates_only_once_the_previous_request_of_the_page_has_its_download(
        self, manager: DownloadManager
    ) -> None:
        page = _page_serving(
            download_of(MagicMock(), "https://cdn.example/a.txt", name="a.txt"),
            download_of(MagicMock(), "https://cdn.example/b.txt", name="b.txt"),
        )
        started, first_started, gate = _holding_first_navigation(page)

        first = asyncio.create_task(manager.download_url(page, _FIRST_URL))
        await asyncio.wait_for(first_started.wait(), timeout=1.0)
        second = asyncio.create_task(manager.download_url(page, _SECOND_URL))
        await asyncio.sleep(0.05)

        assert started == [_FIRST_URL]  # the second request waits for its turn

        gate.set()
        first_result, second_result = await asyncio.gather(first, second)

        assert started == [_FIRST_URL, _SECOND_URL]
        assert (first_result.file_name, second_result.file_name) == ("a.txt", "b.txt")

    @pytest.mark.asyncio
    async def test_requests_on_other_pages_do_not_wait(self, manager: DownloadManager) -> None:
        busy = _page_serving(download_of(MagicMock(), "https://cdn.example/a.txt"))
        _, first_started, gate = _holding_first_navigation(busy)
        idle = _page_serving(download_of(MagicMock(), "https://cdn.example/b.txt"))

        waiting = asyncio.create_task(manager.download_url(busy, _FIRST_URL))
        await asyncio.wait_for(first_started.wait(), timeout=1.0)

        result = await asyncio.wait_for(manager.download_url(idle, _SECOND_URL), timeout=2.0)

        assert result.url == "https://cdn.example/b.txt"
        assert not waiting.done()
        gate.set()
        await waiting

    @pytest.mark.asyncio
    async def test_a_request_that_gives_up_waiting_for_its_turn_does_not_hold_up_the_next(
        self, manager: DownloadManager
    ) -> None:
        page = _page_serving(
            download_of(MagicMock(), "https://cdn.example/a.txt", name="a.txt"),
            download_of(MagicMock(), "https://cdn.example/c.txt", name="c.txt"),
        )
        started, first_started, gate = _holding_first_navigation(page)
        first = asyncio.create_task(manager.download_url(page, _FIRST_URL))
        await asyncio.wait_for(first_started.wait(), timeout=1.0)
        abandoned = asyncio.create_task(manager.download_url(page, "https://public.example/abandoned"))
        third = asyncio.create_task(manager.download_url(page, _SECOND_URL))
        await asyncio.sleep(0.05)

        abandoned.cancel()
        gate.set()
        first_result, third_result = await asyncio.gather(first, third)

        assert abandoned.cancelled()
        assert started == [_FIRST_URL, _SECOND_URL]
        assert (first_result.file_name, third_result.file_name) == ("a.txt", "c.txt")
        assert manager._requests == []

    @pytest.mark.asyncio
    async def test_the_turn_ends_when_the_download_is_taken_not_when_it_is_saved(
        self, manager: DownloadManager
    ) -> None:
        slow = download_of(MagicMock(), "https://cdn.example/a.txt", name="a.txt")
        saving, release = asyncio.Event(), asyncio.Event()

        async def slow_finish() -> Path:
            saving.set()
            await release.wait()
            return finished_file(b"a")

        slow.path = AsyncMock(side_effect=slow_finish)
        page = _page_serving(slow, download_of(MagicMock(), "https://cdn.example/b.txt", name="b.txt"))
        first = asyncio.create_task(manager.download_url(page, _FIRST_URL))
        await asyncio.wait_for(saving.wait(), timeout=1.0)

        second_result = await asyncio.wait_for(manager.download_url(page, _SECOND_URL), timeout=2.0)

        assert second_result.file_name == "b.txt"
        assert not first.done()
        release.set()
        assert (await first).file_name == "a.txt"
