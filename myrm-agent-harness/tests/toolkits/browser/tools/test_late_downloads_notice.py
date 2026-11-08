"""A download can settle after the action that started it was answered: the next text answer carries what it came to.

The answer to a click waits only a moment for the downloads the page started (every click pays that moment), so a
page that starts a download from a timer of its own, or whose server takes a while to answer, settles it later. The
cancel boundary that wraps every browser tool hands the agent that outcome once, with the next text result, the way it
hands over a tab reset.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain.tools import tool
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.browser.session.download import DownloadActivity, DownloadRefusal, DownloadResult
from myrm_agent_harness.toolkits.browser.tools.cancel_boundary import apply_cancel_boundary
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, set_cancel_token

_SAVED = DownloadResult(url="https://x.test/a.pdf", path="/w/.agent/downloads/a.pdf", file_name="a.pdf", file_size=3)
_REFUSED = DownloadRefusal(file_name="setup.exe", reason='file type ".exe" is not allowed')
_HEADER = "Downloads from earlier actions have settled since:"


@pytest.fixture(autouse=True)
def _cancel_token() -> Iterator[None]:
    set_cancel_token(CancellationToken("req"))
    yield
    set_cancel_token(None)


def _session(*settled: DownloadActivity) -> MagicMock:
    """A session that hands over each of ``settled`` once, in order, and nothing after them."""
    session = MagicMock()
    session.active_tab_crashed = MagicMock(return_value=False)
    session.recover_active_tab = AsyncMock(return_value=None)
    session.take_tab_reset_notice = MagicMock(return_value=None)
    session.take_unannounced_downloads = MagicMock(side_effect=[*settled, *([DownloadActivity()] * 5)])
    return session


def _echo_tool(result: object) -> BaseTool:
    @tool("echo_tool")
    async def echo_tool(value: str) -> object:
        """Echo."""
        return result

    return echo_tool


async def _answer(tool_to_guard: BaseTool, session: MagicMock) -> object:
    (guarded,) = apply_cancel_boundary([tool_to_guard], session)
    return await guarded.ainvoke({"value": "a"})


class TestTheNextAnswer:
    @pytest.mark.asyncio
    async def test_it_carries_what_settled_late_exactly_once(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,), refused=(_REFUSED,)))
        (guarded,) = apply_cancel_boundary([_echo_tool("page text")], session)

        first = await guarded.ainvoke({"value": "a"})
        second = await guarded.ainvoke({"value": "a"})

        assert isinstance(first, str)
        assert first.startswith("page text\n\n")
        assert _HEADER in first
        assert "File downloaded: a.pdf (3 bytes)\nPath: /w/.agent/downloads/a.pdf" in first
        assert 'Download refused: setup.exe: file type ".exe" is not allowed' in first
        assert "UNTRUSTED_DATA" in first
        assert second == "page text"

    @pytest.mark.asyncio
    async def test_the_tab_reset_comes_ahead_of_the_text_and_the_downloads_after_it(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,)))
        session.take_tab_reset_notice.return_value = "The tab was reset."

        answer = await _answer(_echo_tool("page text"), session)

        assert isinstance(answer, str)
        assert answer.index("The tab was reset.") < answer.index("page text") < answer.index("File downloaded")

    @pytest.mark.asyncio
    async def test_nothing_settled_leaves_the_text_as_it_is(self) -> None:
        assert await _answer(_echo_tool("page text"), _session()) == "page text"

    @pytest.mark.asyncio
    async def test_a_structured_result_is_left_untouched_and_the_downloads_stay_pending(self) -> None:
        session = _session(DownloadActivity(saved=(_SAVED,)))
        structured = {"url": "https://x.test/", "title": "t"}

        assert await _answer(_echo_tool(structured), session) == structured
        session.take_unannounced_downloads.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_failing_tool_leaves_the_downloads_pending(self) -> None:
        @tool("fail_tool")
        async def fail_tool(value: str) -> str:
            """Fails."""
            raise RuntimeError("boom")

        session = _session(DownloadActivity(saved=(_SAVED,)))

        with pytest.raises(RuntimeError, match="boom"):
            await _answer(fail_tool, session)

        session.take_unannounced_downloads.assert_not_called()
