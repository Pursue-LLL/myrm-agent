"""A download slot bounds the saves in progress, nothing else.

``max_concurrent_downloads`` limits how many downloads are being saved at once, requested and page-started alike. A
request still waiting for its page to start a download, a download being judged and one that is refused hold no slot:
with the only slot taken by another save, none of them waits for it. The real-Chromium proof of the same is
``test_download_url_integration`` and ``test_download_page_started_integration``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session.download import manager as download_manager
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.manager import DownloadManager
from tests.toolkits.browser._download_doubles import DEFAULT_FINAL_URL, download_of, requesting_page, waiting_page

_REQUEST_URL = "https://public.example/go"
_SETTLE_S = 0.05  # long enough for every task that can go on to have gone on


@pytest.fixture(autouse=True)
def _no_navigation_to_stop() -> Iterator[None]:
    with patch.object(download_manager, "abort_pending_navigation", new_callable=AsyncMock):
        yield


@pytest.fixture
def verify() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def manager(tmp_path: Path, verify: AsyncMock) -> DownloadManager:
    """A manager with a single slot, so a download that holds it is felt by every other one."""
    config = DownloadConfig(
        downloads_dir=tmp_path / "downloads", confined_to=tmp_path, max_concurrent_downloads=1, download_timeout_s=5.0
    )
    return DownloadManager(config, verify_final_url=verify)


def _finishing_when(gate: asyncio.Event, download: MagicMock) -> MagicMock:
    """``download`` reports its finished file only once ``gate`` opens."""
    finish: Callable[[], Awaitable[Path]] = download.path.side_effect

    async def path() -> Path:
        await gate.wait()
        return await finish()

    download.path = AsyncMock(side_effect=path)
    return download


async def _settled(manager: DownloadManager) -> None:
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


class TestSavesAreBounded:
    @pytest.mark.asyncio
    async def test_page_started_saves_take_the_only_slot_in_turn(self, manager: DownloadManager) -> None:
        gate = asyncio.Event()
        first = _finishing_when(gate, download_of(MagicMock(), DEFAULT_FINAL_URL, name="first.txt"))
        second = download_of(MagicMock(), DEFAULT_FINAL_URL, name="second.txt")

        manager._on_download(first)
        manager._on_download(second)
        await asyncio.sleep(_SETTLE_S)
        first.path.assert_awaited_once()
        second.path.assert_not_awaited()

        gate.set()
        await _settled(manager)
        assert [result.file_name for result in manager.downloads] == ["first.txt", "second.txt"]

    @pytest.mark.asyncio
    async def test_a_request_saves_only_once_a_slot_is_free(self, manager: DownloadManager) -> None:
        page, download = requesting_page()

        async with manager._semaphore:  # another save holds the only slot
            request = asyncio.create_task(manager.download_url(page, _REQUEST_URL))
            await asyncio.sleep(_SETTLE_S)
            download.path.assert_not_awaited()

        result = await asyncio.wait_for(request, timeout=1.0)
        assert result.url == DEFAULT_FINAL_URL


class TestWhatHoldsNoSlot:
    @pytest.mark.asyncio
    async def test_a_request_still_waiting_for_its_download_holds_none(self, manager: DownloadManager) -> None:
        request = asyncio.create_task(manager.download_url(waiting_page(), _REQUEST_URL))
        await asyncio.sleep(_SETTLE_S)  # the request waits for a download its page does not start

        manager._on_download(download_of(MagicMock(), DEFAULT_FINAL_URL))
        await asyncio.wait_for(_settled(manager), timeout=1.0)

        assert [result.url for result in manager.downloads] == [DEFAULT_FINAL_URL]
        request.cancel()
        await asyncio.gather(request, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_a_request_to_refuse_is_judged_at_once_even_while_the_only_slot_is_taken(
        self, manager: DownloadManager, verify: AsyncMock
    ) -> None:
        verify.side_effect = BrowserNavigationBlockedError("SSRF blocked: 127.0.0.1 is loopback")
        page, download = requesting_page()

        async with manager._semaphore:
            with pytest.raises(BrowserNavigationBlockedError):
                await asyncio.wait_for(manager.download_url(page, _REQUEST_URL), timeout=1.0)

        download.delete.assert_awaited_once()
        download.path.assert_not_awaited()
