"""Real-Chromium proof of what the agent is told when a page starts a download, and which ones the policy lets a page keep.

A click that starts a download, in a link or in the click handler of a button, by element or by coordinates, is
answered with where the file is, or why it was not kept, even when the verdict takes a while. A download the page starts
later from a timer of its own is not in that answer but is kept and listed, and the next answer of any tool says what it
came to, once. A navigation to an address that answers with a file is answered with the file, not with a failure. The
policy decides on the address the download came from; a policy that says no keeps nothing, tells the agent, and still
leaves the agent free to request the file itself; and the listing of downloads reports what was not kept. The hosts are
fake (see ``test_download_url_integration``).
Run with: `pytest -m integration tests/toolkits/browser/test_download_policy_integration.py`.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.exceptions import BrowserNavigationError
from myrm_agent_harness.toolkits.browser.tools import create_browser_tools
from myrm_agent_harness.toolkits.browser.tools.interact import create_interact_tool
from myrm_agent_harness.toolkits.browser.tools.manage import create_manage_tool
from myrm_agent_harness.toolkits.browser.tools.navigate import create_navigate_tool
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_doubles import kept_files
from tests.toolkits.browser._download_integration import (
    DNS_ANSWERS,
    DOWNLOAD_TIMEOUT_S,
    attachment,
    delay_verdicts,
    kept_by_browser_once_settled,
    open_session,
    point_browser_tmpdir,
    until,
)
from tests.toolkits.browser._fake_dns import process_dns, url_on
from tests.toolkits.browser._redirect_servers import page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_SLOW_VERDICT_S = 1.0
_LINK_PAGE = page('<a href="/file" download>get the report</a>')
# An export button whose click handler starts the download itself.
_EXPORT_PAGE = page(
    "<button onclick=\"document.getElementById('f').click()\">export</button>"
    '<a id="f" href="/file" download hidden>report</a>'
)
# An export button whose page starts the download from a timer, well after the click's answer has been given.
_DEFERRED_START_S = 0.6
_BUTTON_PAGE = page(
    f"<button onclick=\"setTimeout(() => document.getElementById('f').click(), {int(_DEFERRED_START_S * 1000)})\">"
    'export</button><a id="f" href="/file" download hidden>report</a>'
)
_REF = re.compile(r"\b(e\d+)\b")  # the first element ref of a snapshot of either page


@pytest.fixture(autouse=True)
def _process_dns() -> Iterator[None]:
    with process_dns(DNS_ANSWERS):
        yield


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


@pytest.fixture
def browser_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return point_browser_tmpdir(tmp_path, monkeypatch)


async def _first_ref(session: BrowserSession, site_url: str) -> str:
    """Open the page and return the ref of its first element."""
    await session.navigate(site_url)
    snapshot, _ = await session.snapshot()
    match = _REF.search(str(snapshot))
    assert match, f"no ref in the snapshot: {snapshot!r}"
    return match.group(1)


async def _click_the_first_element(session: BrowserSession, site_url: str) -> str:
    """Open the page and click its first element through the interact tool, as the agent does."""
    ref = await _first_ref(session, site_url)
    return str(await create_interact_tool(session).ainvoke({"action": "click", "ref": ref}))


class TestClickReport:
    async def test_a_click_is_answered_with_the_file_even_when_the_verdict_takes_a_while(
        self, downloads_dir: Path, browser_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        delay_verdicts(monkeypatch, _SLOW_VERDICT_S)
        with serve({"/home": _LINK_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                started = time.monotonic()

                answer = await _click_the_first_element(session, url_on("public.test", site, "/home"))

                assert "File downloaded: a.txt (5 bytes)" in answer
                assert time.monotonic() - started >= _SLOW_VERDICT_S
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == ["a.txt"]

    async def test_a_download_the_click_handler_starts_is_in_the_answer(self, downloads_dir: Path) -> None:
        with serve({"/home": _EXPORT_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                answer = await _click_the_first_element(session, url_on("public.test", site, "/home"))

                assert "File downloaded: a.txt (5 bytes)" in answer

    async def test_a_download_the_page_starts_later_is_kept_and_listed_though_not_in_the_answer(
        self, downloads_dir: Path
    ) -> None:
        with serve({"/home": _BUTTON_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                answer = await _click_the_first_element(session, url_on("public.test", site, "/home"))
                assert "File downloaded" not in answer

                await until(lambda: bool(session.list_downloads()))
                listing = str(await create_manage_tool(session).ainvoke({"action": "list_downloads"}))

                assert "a.txt" in listing
            assert kept_files(downloads_dir) == ["a.txt"]

    async def test_a_click_whose_download_a_policy_refuses_says_why_and_keeps_nothing(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        with serve({"/home": _LINK_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False, admit_page_started=lambda _address: False) as session:
                answer = await _click_the_first_element(session, url_on("public.test", site, "/home"))

                assert "Download refused: a.txt: the permission policy does not let a page save files" in answer
                assert "download_url" in answer
                assert session.list_downloads() == []
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == []


class TestPolicy:
    async def test_the_policy_decides_on_the_address_the_download_came_from(self, downloads_dir: Path) -> None:
        asked: list[str] = []

        def admit(address: str) -> bool:
            asked.append(address)
            return True

        with serve({"/home": _LINK_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False, admit_page_started=admit) as session:
                await _click_the_first_element(session, url_on("public.test", site, "/home"))

                assert asked == [url_on("public.test", site, "/file")]

    async def test_a_page_that_may_not_save_on_its_own_does_not_stop_the_agent_requesting_the_file(
        self, downloads_dir: Path
    ) -> None:
        with serve({"/home": _LINK_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False, admit_page_started=lambda _address: False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                saved = await session.download_url(url_on("public.test", site, "/file"))

                assert Path(saved.path).read_bytes() == b"hello"

    async def test_the_listing_reports_what_a_page_started_that_was_not_kept(self, downloads_dir: Path) -> None:
        with serve({"/home": _LINK_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False, admit_page_started=lambda _address: False) as session:
                await _click_the_first_element(session, url_on("public.test", site, "/home"))
                await until(lambda: bool(session.download_refusals))

                listing = str(await create_manage_tool(session).ainvoke({"action": "list_downloads"}))

                assert "Downloads not kept (1):" in listing
                assert " - a.txt: the permission policy does not let a page save files" in listing


class TestCoordinateClick:
    async def test_a_click_by_coordinates_is_answered_with_the_file(self, downloads_dir: Path) -> None:
        with serve({"/home": _EXPORT_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))
                box = await session.get_active_page().locator("button").bounding_box()
                assert box is not None

                answer = await create_interact_tool(session).ainvoke(
                    {"action": "click", "x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2}
                )

                assert "File downloaded: a.txt (5 bytes)" in str(answer)


def _guarded_tools(session: BrowserSession) -> dict[str, BaseTool]:
    """The tools as the agent gets them: behind the boundary that carries what settled after its action was answered."""
    return {tool.name: tool for tool in create_browser_tools(session)}


async def _list_tabs(tools: dict[str, BaseTool]) -> str:
    return str(await tools["browser_manage_tool"].ainvoke({"action": "list_tabs"}))


class TestWhatSettlesAfterTheAnswer:
    async def test_a_download_the_page_starts_later_is_in_a_later_answer_once(self, downloads_dir: Path) -> None:
        with serve({"/home": _BUTTON_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                tools = _guarded_tools(session)
                ref = await _first_ref(session, url_on("public.test", site, "/home"))
                answer = str(await tools["browser_interact_tool"].ainvoke({"action": "click", "ref": ref}))
                assert "File downloaded" not in answer

                async with asyncio.timeout(DOWNLOAD_TIMEOUT_S):  # the download settles on its own time
                    while "File downloaded" not in (later := await _list_tabs(tools)):
                        await asyncio.sleep(0.05)

                assert "Downloads from earlier actions have settled since:" in later
                assert "File downloaded: a.txt (5 bytes)" in later
                assert "File downloaded" not in await _list_tabs(tools)

    async def test_what_the_click_answer_carried_is_not_said_again(self, downloads_dir: Path) -> None:
        with serve({"/home": _LINK_PAGE, "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                tools = _guarded_tools(session)
                ref = await _first_ref(session, url_on("public.test", site, "/home"))

                answer = str(await tools["browser_interact_tool"].ainvoke({"action": "click", "ref": ref}))

                assert answer.count("File downloaded: a.txt (5 bytes)") == 1
                assert "File downloaded" not in await _list_tabs(tools)


class TestNavigatingToAFile:
    async def test_the_navigation_is_answered_with_the_saved_file_and_not_with_a_failure(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        with serve({"/home": page("home"), "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                answer = await create_navigate_tool(session).ainvoke({"url": url_on("public.test", site, "/file")})

                assert isinstance(answer, str)
                assert "started a file download instead of opening a page" in answer
                assert "File downloaded: a.txt (5 bytes)" in answer
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == ["a.txt"]

    async def test_a_download_a_policy_refuses_is_answered_with_the_reason(self, downloads_dir: Path) -> None:
        with serve({"/home": page("home"), "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False, admit_page_started=lambda _address: False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                answer = await create_navigate_tool(session).ainvoke({"url": url_on("public.test", site, "/file")})

                assert "Download refused: a.txt: the permission policy does not let a page save files" in str(answer)
            assert kept_files(downloads_dir) == []

    async def test_a_session_without_download_support_still_fails(self, browser_tmp: Path) -> None:
        with serve({"/home": page("home"), "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(None, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                with pytest.raises(BrowserNavigationError):
                    await create_navigate_tool(session).ainvoke({"url": url_on("public.test", site, "/file")})

                assert await kept_by_browser_once_settled(browser_tmp) == []  # the browser cancelled the download
