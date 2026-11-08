"""Downloads a page starts by itself: the policy that admits them, the notes for those not kept, the wait for them.

A page starts a download without any call the agent made, so nobody can be asked: the config's policy decides
beforehand, and only a yes keeps the file. A download that is not kept is remembered with the reason (the last few, no
address in any of them) so the agent can be told, and a report of what a click came to waits for the downloads in
flight. The real-Chromium proof is ``test_download_page_started_integration``.
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
from myrm_agent_harness.toolkits.browser.session.download import manager as download_manager
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig, PageStartedPolicy
from myrm_agent_harness.toolkits.browser.session.download.manager import DownloadManager
from myrm_agent_harness.toolkits.browser.session.download.records import DownloadMark, DownloadRefusal
from tests.toolkits.browser._download_doubles import download_of, kept_files, requesting_page, waiting_page

_URL = "https://cdn.example/report.pdf"
_MANAGER_LOGGER = "myrm_agent_harness.toolkits.browser.session.download.manager"


@pytest.fixture(autouse=True)
def _no_navigation_to_stop() -> Iterator[None]:
    with patch.object(download_manager, "abort_pending_navigation", new_callable=AsyncMock):
        yield


@pytest.fixture
def verify() -> AsyncMock:
    return AsyncMock()


def _manager(
    tmp_path: Path,
    verify: AsyncMock,
    *,
    admit: PageStartedPolicy | None = None,
    max_files: int = 200,
    timeout_s: float = 5.0,
) -> DownloadManager:
    config = DownloadConfig(
        downloads_dir=tmp_path / "downloads",
        confined_to=tmp_path,
        admit_page_started=admit,
        max_files=max_files,
        download_timeout_s=timeout_s,
    )
    return DownloadManager(config, verify_final_url=verify)


async def _settled(manager: DownloadManager) -> None:
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


async def _page_starts(manager: DownloadManager, *downloads: MagicMock) -> None:
    for download in downloads:
        manager._on_download(download)
    await _settled(manager)


class TestAdmission:
    @pytest.mark.asyncio
    async def test_without_a_policy_a_download_that_passes_the_address_check_is_kept(
        self, tmp_path: Path, verify: AsyncMock
    ) -> None:
        manager = _manager(tmp_path, verify)

        await _page_starts(manager, download_of(MagicMock(), _URL))

        assert [result.url for result in manager.downloads] == [_URL]

    @pytest.mark.asyncio
    async def test_a_policy_that_says_no_discards_the_download_before_its_address_is_judged(
        self, tmp_path: Path, verify: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        manager = _manager(tmp_path, verify, admit=lambda _address: False)
        download = download_of(MagicMock(), f"{_URL}?sig=hunter2")
        caplog.set_level(logging.WARNING, logger=_MANAGER_LOGGER)

        await _page_starts(manager, download)

        verify.assert_not_awaited()
        download.cancel.assert_awaited_once()
        download.delete.assert_awaited_once()
        download.path.assert_not_awaited()
        assert manager.downloads == []
        assert kept_files(tmp_path / "downloads") == []
        assert [refusal.file_name for refusal in manager.refusals] == ["secret.txt"]
        assert "permission policy" in manager.refusals[0].reason
        assert "does not admit downloads a page starts" in caplog.text
        assert "hunter2" not in caplog.text

    @pytest.mark.asyncio
    async def test_the_policy_is_asked_about_the_address_the_download_came_from(
        self, tmp_path: Path, verify: AsyncMock
    ) -> None:
        admit = MagicMock(return_value=True)

        await _page_starts(_manager(tmp_path, verify, admit=admit), download_of(MagicMock(), _URL))

        admit.assert_called_once_with(_URL)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["blob:https://app.example/6f1c", "data:text/plain;base64,aGk="])
    async def test_a_download_the_page_built_itself_is_judged_as_the_page_that_built_it(
        self, tmp_path: Path, verify: AsyncMock, url: str
    ) -> None:
        admit = MagicMock(return_value=True)
        page = MagicMock()
        page.url = "https://app.example/export"

        await _page_starts(_manager(tmp_path, verify, admit=admit), download_of(page, url))

        admit.assert_called_once_with("https://app.example/export")

    @pytest.mark.asyncio
    async def test_a_policy_that_fails_refuses_and_logs_only_what_kind_of_failure(
        self, tmp_path: Path, verify: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        admit = MagicMock(side_effect=RuntimeError("internal detail"))
        manager = _manager(tmp_path, verify, admit=admit)
        caplog.set_level(logging.WARNING, logger=_MANAGER_LOGGER)

        await _page_starts(manager, download_of(MagicMock(), _URL))

        assert manager.downloads == []
        assert len(manager.refusals) == 1
        assert "RuntimeError" in caplog.text
        assert "internal detail" not in caplog.text

    @pytest.mark.asyncio
    async def test_the_policy_does_not_reach_a_download_the_agent_asked_for(
        self, tmp_path: Path, verify: AsyncMock
    ) -> None:
        admit = MagicMock(return_value=False)
        manager = _manager(tmp_path, verify, admit=admit)
        page, _ = requesting_page(_URL)

        result = await manager.download_url(page, _URL)

        assert result.url == _URL
        admit.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_download_a_request_claimed_but_never_took_goes_through_the_policy(
        self, tmp_path: Path, verify: AsyncMock
    ) -> None:
        manager = _manager(tmp_path, verify, admit=lambda _address: False)
        page = waiting_page()
        claimed = download_of(page, _URL)
        navigating = asyncio.Event()

        def start_the_download(*_args: object) -> None:
            manager._on_download(claimed)
            navigating.set()

        page.evaluate.side_effect = start_the_download
        request = asyncio.create_task(manager.download_url(page, "https://public.example/go"))
        await asyncio.wait_for(navigating.wait(), timeout=1.0)
        request.cancel()
        with pytest.raises(asyncio.CancelledError):
            await request
        await _settled(manager)

        claimed.path.assert_not_awaited()
        assert manager.downloads == []


class TestRefusalNotes:
    @pytest.mark.asyncio
    async def test_a_refused_address_is_noted_without_the_address(self, tmp_path: Path, verify: AsyncMock) -> None:
        verify.side_effect = BrowserNavigationBlockedError("SSRF blocked: 127.0.0.1 is loopback")
        manager = _manager(tmp_path, verify)

        await _page_starts(
            manager, download_of(MagicMock(), "http://user:hunter2@127.0.0.1:9/a.txt", name="../../a.txt")
        )

        (note,) = manager.refusals
        assert note.file_name == "a.txt"
        assert "network safety policy" in note.reason
        assert "127.0.0.1" not in note.reason
        assert "hunter2" not in note.reason

    @pytest.mark.asyncio
    async def test_a_file_that_cannot_be_kept_is_noted_with_why(self, tmp_path: Path, verify: AsyncMock) -> None:
        manager = _manager(tmp_path, verify, max_files=1)

        await _page_starts(
            manager,
            download_of(MagicMock(), _URL, name="first.pdf"),
            download_of(MagicMock(), _URL, name="setup.exe"),
        )
        await _page_starts(manager, download_of(MagicMock(), _URL, name="second.pdf"))

        reasons = {note.file_name: note.reason for note in manager.refusals}
        assert reasons["setup.exe"] == 'file type ".exe" is not allowed'
        assert "folder is full" in reasons["second.pdf"]

    @pytest.mark.asyncio
    async def test_a_download_that_could_not_be_processed_is_noted(self, tmp_path: Path, verify: AsyncMock) -> None:
        verify.side_effect = RuntimeError("resolver unavailable")
        manager = _manager(tmp_path, verify)

        await _page_starts(manager, download_of(MagicMock(), _URL))

        assert [note.reason for note in manager.refusals] == ["it could not be processed"]

    @pytest.mark.asyncio
    async def test_only_the_latest_refusals_are_remembered(self, tmp_path: Path, verify: AsyncMock) -> None:
        manager = _manager(tmp_path, verify, admit=lambda _address: False)

        await _page_starts(manager, *(download_of(MagicMock(), _URL, name=f"f{index}.txt") for index in range(8)))

        assert [note.file_name for note in manager.refusals] == [f"f{index}.txt" for index in range(3, 8)]
        assert manager.mark() == DownloadMark(saved=0, refused=8)


class TestActivitySince:
    @pytest.mark.asyncio
    async def test_it_reports_what_came_after_the_mark_only(self, tmp_path: Path, verify: AsyncMock) -> None:
        manager = _manager(tmp_path, verify)
        verify.side_effect = [BrowserNavigationBlockedError("blocked"), None, None]
        await _page_starts(manager, download_of(MagicMock(), _URL, name="old-refused.txt"))
        await _page_starts(manager, download_of(MagicMock(), _URL, name="old-saved.txt"))
        mark = manager.mark()

        await _page_starts(manager, download_of(MagicMock(), _URL, name="new-saved.txt"))
        activity = await manager.activity_since(mark)

        assert [saved.file_name for saved in activity.saved] == ["new-saved.txt"]
        assert activity.refused == ()

    @pytest.mark.asyncio
    async def test_it_reports_the_refusals_after_the_mark(self, tmp_path: Path, verify: AsyncMock) -> None:
        manager = _manager(tmp_path, verify, admit=lambda _address: False)
        await _page_starts(manager, download_of(MagicMock(), _URL, name="old.txt"))
        mark = manager.mark()

        await _page_starts(manager, download_of(MagicMock(), _URL, name="new.txt"))
        activity = await manager.activity_since(mark)

        assert activity.refused == (DownloadRefusal(file_name="new.txt", reason=manager.refusals[-1].reason),)
        assert activity.saved == ()

    @pytest.mark.asyncio
    async def test_it_waits_for_a_download_that_is_still_being_judged(self, tmp_path: Path, verify: AsyncMock) -> None:
        """A verdict still pending would otherwise read as no download at all."""

        async def slow_verdict(_url: str) -> None:
            await asyncio.sleep(0.2)

        verify.side_effect = slow_verdict
        manager = _manager(tmp_path, verify)
        mark = manager.mark()

        manager._on_download(download_of(MagicMock(), _URL))
        activity = await manager.activity_since(mark)

        assert [saved.url for saved in activity.saved] == [_URL]

    @pytest.mark.asyncio
    async def test_it_does_not_wait_longer_than_a_download_may_take(self, tmp_path: Path, verify: AsyncMock) -> None:
        async def never_answers(_url: str) -> None:
            await asyncio.sleep(3600)

        verify.side_effect = never_answers
        manager = _manager(tmp_path, verify, timeout_s=0.1)
        mark = manager.mark()
        manager._on_download(download_of(MagicMock(), _URL))

        started = time.monotonic()
        activity = await manager.activity_since(mark)

        assert time.monotonic() - started < 2.0
        assert activity.saved == ()
        await manager.cleanup()

    @pytest.mark.asyncio
    async def test_with_nothing_in_flight_it_answers_at_once(self, tmp_path: Path, verify: AsyncMock) -> None:
        manager = _manager(tmp_path, verify, admit=lambda _address: False)
        await _page_starts(manager, download_of(MagicMock(), _URL))
        await _settled(manager)

        activity = await manager.activity_since(manager.mark())

        assert activity.saved == ()
        assert activity.refused == ()
