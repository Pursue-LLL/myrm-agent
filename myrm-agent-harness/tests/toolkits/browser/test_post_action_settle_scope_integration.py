"""Real-Chromium proof of which actions the post-action settle covers and where it waits.

Selecting, checking, unchecking, uploading and dragging are answered after the response they asked for as much as a
click is; an element inside an iframe is waited for in the iframe's own document; a wait that reaches its cap says so in
the answer; and an action that navigates is answered while the page it lands on is still loading, not after it.
Run with: `pytest -m integration tests/toolkits/browser/test_post_action_settle_scope_integration.py`.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from myrm_agent_harness.toolkits.browser.wait import capped_note
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._redirect_servers import page
from tests.toolkits.browser._settle_pages import LOAD, act, click_center, document_with, opened, shown

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_SELECT = "<select onchange=\"show('/api/data')\"><option>a</option><option>b</option></select>"
_CHECK = '<input type="checkbox" onchange="show(\'/api/data\')">'
_UNCHECK = '<input type="checkbox" checked onchange="show(\'/api/data\')">'
_UPLOAD = '<input type="file" onchange="show(\'/api/data\')">'
# A drag ends on the body, so the body is made tall enough to hold the point it is dragged to.
_DRAG = (
    '<button>drag me</button><div style="height: 900px"></div>'
    "<script>document.addEventListener('mouseup', () => show('/api/data'))</script>"
)
_LONG_POLL = "<button onclick=\"show('/api/longpoll')\">load</button>"
_LINK = '<a href="/next">go</a>'
_FORM = '<form action="/next"><input name="q"></form>'
# The page a navigation lands on asks for something that takes far longer than an answer should be held back.
_NEXT = page('<div id="out">next</div><script>fetch("/api/longpoll")</script>')
_ANSWERED_WITHIN_S = 2.0


class TestEveryActionThatCanChangeThePageWaits:
    @pytest.mark.parametrize(
        ("control", "arguments"),
        [
            pytest.param(_SELECT, {"action": "select", "text": "b"}, id="select"),
            pytest.param(_CHECK, {"action": "check"}, id="check"),
            pytest.param(_UNCHECK, {"action": "uncheck"}, id="uncheck"),
            pytest.param(_DRAG, {"action": "drag", "text": "100,400"}, id="drag"),
        ],
    )
    async def test_the_request_the_action_makes_is_waited_for(self, control: str, arguments: dict[str, str]) -> None:
        async with opened(control) as (session, tab):
            await act(session, **arguments)

            assert await shown(tab) == "data-ready"

    async def test_an_upload_waits_for_the_request_of_its_handler(self, tmp_path: Path) -> None:
        report = tmp_path / "report.txt"
        report.write_text("quarterly figures")
        async with opened(_UPLOAD) as (session, tab):
            await act(session, action="upload_file", text=str(report))

            assert await shown(tab) == "data-ready"


class TestWhereTheWaitIsAsked:
    async def test_an_element_in_an_iframe_is_waited_for_in_that_iframe(self) -> None:
        host = '<iframe src="/frame" width="400" height="200"></iframe>'
        async with opened(host, routes={"/frame": document_with(LOAD)}) as (session, tab):
            await act(session, ref="f1_e0", action="click")

            assert await tab.frame_locator("iframe").locator("#out").inner_text() == "data-ready"


class TestWhatTheAnswerSaysWhenTheWaitReachesItsCap:
    async def test_an_action_on_an_element_says_the_page_was_still_loading(self) -> None:
        async with opened(_LONG_POLL) as (session, _):
            answer = await act(session, action="click")

        assert capped_note("capped") in answer

    async def test_an_action_at_coordinates_says_so_too(self) -> None:
        async with opened(_LONG_POLL) as (session, tab):
            answer = await click_center(session, tab)

        assert capped_note("capped") in answer

    async def test_an_action_that_was_waited_for_in_time_says_nothing(self) -> None:
        async with opened(LOAD) as (session, _):
            answer = await act(session, action="click")

        assert capped_note("capped") not in answer


class TestAnActionThatNavigatesIsNotHeldBack:
    @pytest.mark.parametrize(
        ("control", "arguments"),
        [
            pytest.param(_LINK, {"action": "click"}, id="link"),
            pytest.param(_FORM, {"action": "press", "text": "Enter"}, id="enter-submits-a-form"),
        ],
    )
    async def test_the_answer_comes_while_the_new_page_still_loads(
        self, control: str, arguments: dict[str, str]
    ) -> None:
        async with opened(control, routes={"/next": _NEXT}) as (session, tab):
            started = time.perf_counter()
            answer = await act(session, **arguments)

            assert time.perf_counter() - started < _ANSWERED_WITHIN_S
            assert capped_note("capped") not in answer
            assert await shown(tab) == "next"
