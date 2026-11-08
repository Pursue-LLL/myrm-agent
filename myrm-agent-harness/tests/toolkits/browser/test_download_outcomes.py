"""What a session's downloads came to and who has been told: counted from a mark, announced once.

A download a page starts can settle after the action that started it was answered, so its outcome waits until an
answer carries it. The answer to the action that started it carries the outcomes it reports; a later answer carries
the rest, once. A file the agent requested is answered by the request itself and never waits.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.download import manager as download_manager
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig, PageStartedPolicy
from myrm_agent_harness.toolkits.browser.session.download.manager import DownloadManager
from myrm_agent_harness.toolkits.browser.session.download.outcomes import UNANNOUNCED_KEPT, DownloadOutcomes
from myrm_agent_harness.toolkits.browser.session.download.records import (
    DownloadActivity,
    DownloadRefusal,
    DownloadResult,
)
from tests.toolkits.browser._download_doubles import download_of, requesting_page

_URL = "https://cdn.example/report.pdf"


def _saved(name: str) -> DownloadResult:
    return DownloadResult(url=f"https://cdn.example/{name}", path=f"/w/{name}", file_name=name, file_size=1)


def _refused(name: str, reason: str = "blocked") -> DownloadRefusal:
    return DownloadRefusal(file_name=name, reason=reason)


class TestLedger:
    def test_a_report_holds_what_came_after_its_mark_only(self) -> None:
        outcomes = DownloadOutcomes()
        outcomes.record_saved(_saved("old.txt"))
        outcomes.record_refusal(_refused("old.bin"))
        mark = outcomes.mark(started=0)

        outcomes.record_saved(_saved("new.txt"))
        outcomes.record_refusal(_refused("new.bin"))
        activity = outcomes.report_since(mark)

        assert [saved.file_name for saved in activity.saved] == ["new.txt"]
        assert [refusal.file_name for refusal in activity.refused] == ["new.bin"]

    def test_what_a_report_carried_is_not_handed_over_again(self) -> None:
        outcomes = DownloadOutcomes()
        mark = outcomes.mark(started=0)
        saved, refusal = _saved("a.txt"), _refused("b.bin")
        outcomes.record_saved(saved)
        outcomes.leave_unannounced(saved)
        outcomes.record_refusal(refusal)
        outcomes.leave_unannounced(refusal)

        assert outcomes.report_since(mark) == DownloadActivity(saved=(saved,), refused=(refusal,))
        assert outcomes.take_unannounced() == DownloadActivity()

    def test_what_no_report_carried_is_handed_over_once(self) -> None:
        outcomes = DownloadOutcomes()
        saved, refusal = _saved("late.txt"), _refused("late.bin")
        outcomes.record_saved(saved)
        outcomes.leave_unannounced(saved)
        outcomes.record_refusal(refusal)
        outcomes.leave_unannounced(refusal)

        assert outcomes.take_unannounced() == DownloadActivity(saved=(saved,), refused=(refusal,))
        assert outcomes.take_unannounced() == DownloadActivity()

    def test_an_outcome_equal_to_a_reported_one_is_not_swallowed_with_it(self) -> None:
        """The same file refused twice is two outcomes: reporting the later one leaves the earlier one waiting."""
        outcomes = DownloadOutcomes()
        earlier, later = _refused("a.bin"), _refused("a.bin")
        outcomes.record_refusal(earlier)
        outcomes.leave_unannounced(earlier)
        mark = outcomes.mark(started=1)
        outcomes.record_refusal(later)
        outcomes.leave_unannounced(later)

        (reported,) = outcomes.report_since(mark).refused
        (left_over,) = outcomes.take_unannounced().refused

        assert reported is later
        assert left_over is earlier

    def test_only_the_latest_outcomes_wait_to_be_told(self) -> None:
        outcomes = DownloadOutcomes()
        for index in range(UNANNOUNCED_KEPT + 3):
            result = _saved(f"f{index}.txt")
            outcomes.record_saved(result)
            outcomes.leave_unannounced(result)

        waiting = [saved.file_name for saved in outcomes.take_unannounced().saved]

        assert waiting == [f"f{index}.txt" for index in range(3, UNANNOUNCED_KEPT + 3)]
        assert len(outcomes.saved) == UNANNOUNCED_KEPT + 3  # the listing still has every file

    def test_a_saved_file_nobody_left_unannounced_is_never_handed_over(self) -> None:
        outcomes = DownloadOutcomes()
        outcomes.record_saved(_saved("requested.txt"))

        assert outcomes.take_unannounced() == DownloadActivity()


@pytest.fixture(autouse=True)
def _no_navigation_to_stop() -> Iterator[None]:
    with patch.object(download_manager, "abort_pending_navigation", new_callable=AsyncMock):
        yield


def _manager(tmp_path: Path, *, admit: PageStartedPolicy | None = None) -> DownloadManager:
    config = DownloadConfig(downloads_dir=tmp_path / "downloads", confined_to=tmp_path, admit_page_started=admit)
    return DownloadManager(config, verify_final_url=AsyncMock())


async def _page_starts(manager: DownloadManager, download: MagicMock) -> None:
    manager._on_download(download)
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


class TestWhatAPageStartedReachesTheAgentOnce:
    @pytest.mark.asyncio
    async def test_a_download_that_settles_after_the_report_is_left_to_the_next_answer(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        mark = manager.mark()
        assert await manager.activity_since(mark) == DownloadActivity()  # reported before anything had settled

        await _page_starts(manager, download_of(MagicMock(), _URL, name="late.txt"))

        assert [saved.file_name for saved in manager.take_unannounced().saved] == ["late.txt"]
        assert manager.take_unannounced() == DownloadActivity()

    @pytest.mark.asyncio
    async def test_a_refusal_after_the_report_is_left_to_the_next_answer_too(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path, admit=lambda _address: False)
        assert await manager.activity_since(manager.mark()) == DownloadActivity()

        await _page_starts(manager, download_of(MagicMock(), _URL, name="late.txt"))

        assert [refusal.file_name for refusal in manager.take_unannounced().refused] == ["late.txt"]

    @pytest.mark.asyncio
    async def test_what_a_report_carried_is_not_left_to_the_next_answer(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        mark = manager.mark()
        await _page_starts(manager, download_of(MagicMock(), _URL, name="a.txt"))

        assert [saved.file_name for saved in (await manager.activity_since(mark)).saved] == ["a.txt"]
        assert manager.take_unannounced() == DownloadActivity()

    @pytest.mark.asyncio
    async def test_a_file_the_agent_requested_is_not_left_to_be_announced(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path)
        page, _ = requesting_page(_URL)

        result = await manager.download_url(page, _URL)

        assert result.file_name == "secret.txt"
        assert manager.take_unannounced() == DownloadActivity()
