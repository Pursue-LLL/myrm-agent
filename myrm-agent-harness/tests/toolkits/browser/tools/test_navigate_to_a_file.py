"""An address that answers with a file: the navigation fails, and the agent is told what the download came to.

The browser turns such a navigation into a download, so the navigation reports a failure although the download was
saved (or refused, with a reason). The answer says what the download came to, so the agent neither reads a saved file
as a failure nor retries and saves it twice. A navigation that failed for any other reason fails as before.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.exceptions import BrowserNavigationError
from myrm_agent_harness.toolkits.browser.session.download import (
    DownloadActivity,
    DownloadMark,
    DownloadRefusal,
    DownloadResult,
)
from myrm_agent_harness.toolkits.browser.tools import download_actions as download_actions_module
from myrm_agent_harness.toolkits.browser.tools.navigate import create_navigate_tool

_URL = "https://files.example/report.pdf"
_SAVED = DownloadResult(url=_URL, path="/w/.agent/downloads/report.pdf", file_name="report.pdf", file_size=3)
_MARK = DownloadMark(saved=2, refused=1, started=3)


@pytest.fixture(autouse=True)
def _no_grace_period(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(download_actions_module, "_DOWNLOAD_START_GRACE_S", 0)


def _session(activity: DownloadActivity, *, failure: Exception | None, enabled: bool = True) -> MagicMock:
    session = MagicMock()
    session.download_enabled = enabled
    session.download_mark = MagicMock(return_value=_MARK)
    session.downloads_since = AsyncMock(return_value=activity)
    session.navigate = AsyncMock(side_effect=failure, return_value="Navigated to the page")
    page = MagicMock()
    page.url = "https://example.com/"
    page.title = AsyncMock(return_value="Example")
    session.get_active_page = MagicMock(return_value=page)
    return session


def _cut_short_by_a_download() -> BrowserNavigationError:
    return BrowserNavigationError(
        f"Navigation to {_URL} failed: Download is starting", url=_URL, error_text="Download is starting"
    )


class TestNavigationCutShortByADownload:
    @pytest.mark.asyncio
    async def test_a_saved_file_is_answered_instead_of_the_failure(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,)), failure=_cut_short_by_a_download())

        answer = await create_navigate_tool(session).ainvoke({"url": _URL})

        assert isinstance(answer, str)
        assert "started a file download instead of opening a page" in answer
        assert "File downloaded: report.pdf (3 bytes)\nPath: /w/.agent/downloads/report.pdf" in answer
        assert "UNTRUSTED_DATA" in answer

    @pytest.mark.asyncio
    async def test_a_refused_download_is_answered_with_the_reason(self) -> None:
        refusal = DownloadRefusal(file_name="setup.exe", reason='file type ".exe" is not allowed')
        session = _session(DownloadActivity(refused=(refusal,)), failure=_cut_short_by_a_download())

        answer = await create_navigate_tool(session).ainvoke({"url": _URL})

        assert 'Download refused: setup.exe: file type ".exe" is not allowed' in answer

    @pytest.mark.asyncio
    async def test_the_report_counts_from_before_the_navigation(self) -> None:
        order: list[str] = []

        def mark() -> DownloadMark:
            order.append("mark")
            return _MARK

        def navigate(*_args: object, **_kwargs: object) -> str:
            order.append("navigate")
            raise _cut_short_by_a_download()

        session = _session(DownloadActivity(saved=(_SAVED,)), failure=None)
        session.download_mark.side_effect = mark
        session.navigate.side_effect = navigate

        await create_navigate_tool(session).ainvoke({"url": _URL})

        assert order == ["mark", "navigate"]
        session.downloads_since.assert_awaited_once_with(_MARK)


class TestNavigationThatFailedForAnotherReason:
    @pytest.mark.asyncio
    async def test_it_still_fails_when_no_download_started(self) -> None:
        failure = BrowserNavigationError("Navigation to https://x.test/ stalled", url="https://x.test/")
        session = _session(DownloadActivity(), failure=failure)

        with pytest.raises(BrowserNavigationError, match="stalled"):
            await create_navigate_tool(session).ainvoke({"url": "https://x.test/"})

    @pytest.mark.asyncio
    async def test_it_still_fails_in_a_session_without_download_support(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,)), failure=_cut_short_by_a_download(), enabled=False)

        with pytest.raises(BrowserNavigationError):
            await create_navigate_tool(session).ainvoke({"url": _URL})

        session.downloads_since.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failure_that_is_not_a_navigation_failure_is_not_interpreted(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,)), failure=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await create_navigate_tool(session).ainvoke({"url": _URL})

        session.downloads_since.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_navigation_that_succeeded_is_not_asked_about_downloads(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,)), failure=None)

        answer = await create_navigate_tool(session).ainvoke({"url": "https://example.com/"})

        assert "Navigated to the page" in answer["content"]
        session.downloads_since.assert_not_awaited()
