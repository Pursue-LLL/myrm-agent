"""Real-Chromium proof that an interaction is answered after the response it asked for has been drawn.

A click, typing or a key press that makes the page call its backend is answered once the response is on the page, for at
most the cap; what the page was already doing when the action began (a long poll), a beacon, and an action that sent
no input are not waited for, and a document the tracker was not delivered to is left as the action left it. The pages
call a local server whose endpoints answer after a set time, so what the page shows at the moment the answer is given
tells whether the wait happened.
Run with: `pytest -m integration tests/toolkits/browser/test_post_action_settle_integration.py`.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from myrm_agent_harness.toolkits.browser import enhancers
from myrm_agent_harness.toolkits.browser.wait import settle_after_action
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_integration import open_session
from tests.toolkits.browser._redirect_servers import Reply, serve
from tests.toolkits.browser._settle_pages import ENDPOINTS, LOAD, act, click_center, opened, shown

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_MAIN_WORLD = {"isolated_context": False}
_LOGIN = "<button onclick=\"show('/login')\">log in</button>"
_XHR = "<button onclick=\"showByXhr('/api/data')\">load</button>"
_CHAIN = '<button onclick="chain()">load</button>'
_SUGGEST = "<input oninput=\"show('/api/suggest')\">"
_PRESS = "<button onpointerdown=\"show('/api/data')\">press</button>"
_DRAWN_LATE = (
    "<button onclick=\"fetch('/api/data').then((r) => r.text()).then((text) => "
    "setTimeout(() => { document.getElementById('out').textContent = text; }, 100))\">load</button>"
)
_BEACON = "<button onclick=\"show('/api/ping')\">beacon</button>"
_SLOW = "<button onclick=\"show('/api/slow')\">load</button>"
_NOOP = "<button>nothing</button>"


class TestAnActionIsAnsweredAfterTheResponseItAskedFor:
    @pytest.mark.parametrize(
        ("control", "expected"), [(LOAD, "data-ready"), (_XHR, "data-ready"), (_LOGIN, "login-ready")]
    )
    async def test_a_click_waits_for_the_request_of_its_handler(self, control: str, expected: str) -> None:
        async with opened(control) as (session, tab):
            await act(session, action="click")

            assert await shown(tab) == expected

    async def test_a_double_click_waits_for_the_request_of_its_handler(self) -> None:
        async with opened(LOAD.replace("onclick", "ondblclick")) as (session, tab):
            await act(session, action="dblclick")

            assert await shown(tab) == "data-ready"

    @pytest.mark.parametrize("action", ["fill", "type"])
    async def test_typing_waits_for_the_request_the_input_makes(self, action: str) -> None:
        async with opened(_SUGGEST) as (session, tab):
            await act(session, action=action, text="re")

            assert await shown(tab) == "suggest-ready"

    async def test_a_key_press_waits_for_the_request_it_makes(self) -> None:
        keyed = "<input onkeydown=\"if (event.key === 'Enter') show('/api/data')\">"
        async with opened(keyed) as (session, tab):
            await act(session, action="press", text="Enter")

            assert await shown(tab) == "data-ready"

    async def test_a_click_by_coordinates_waits_the_same(self) -> None:
        async with opened(LOAD) as (session, tab):
            await click_center(session, tab)

            assert await shown(tab) == "data-ready"

    async def test_a_request_started_when_the_pointer_goes_down_is_waited_for(self) -> None:
        async with opened(_PRESS) as (session, tab):
            await act(session, action="click")

            assert await shown(tab) == "data-ready"

    async def test_a_response_the_page_draws_a_moment_later_is_on_the_page(self) -> None:
        async with opened(_DRAWN_LATE) as (session, tab):
            await act(session, action="click")

            assert await shown(tab) == "data-ready"

    async def test_a_page_under_a_strict_script_policy_is_waited_for_too(self) -> None:
        strict = Reply(
            body=b'<!DOCTYPE html><html><body><button id="go">load</button><div id="out">idle</div>'
            b'<script src="/app.js"></script></body></html>',
            headers=(("Content-Security-Policy", "script-src 'self'"),),
        )
        app = Reply(
            body=b"document.getElementById('go').addEventListener('click', async () => {"
            b" const r = await fetch('/api/data'); document.getElementById('out').textContent = await r.text(); });",
            content_type="text/javascript",
        )
        with serve({"/home": strict, "/app.js": app, **ENDPOINTS}) as site:
            async with open_session(None, local=True) as session:
                await session.navigate(site.url("/home"))
                await act(session, action="click")

                assert await shown(session.get_active_page()) == "data-ready"

    async def test_a_request_that_follows_another_is_waited_for_too(self) -> None:
        async with opened(_CHAIN) as (session, tab):
            await act(session, action="click")

            assert await shown(tab) == "second-ready"


class TestWhatIsNotWaitedFor:
    async def test_a_request_already_in_flight_when_the_action_began(self) -> None:
        async with opened(_NOOP) as (_, tab):
            await tab.evaluate("void fetch('/api/longpoll')", **_MAIN_WORLD)
            await tab.click("button")
            started = time.perf_counter()

            assert await settle_after_action(tab) == "no_request"
            assert time.perf_counter() - started < 2.0

    async def test_a_beacon(self) -> None:
        async with opened(_BEACON) as (_, tab):
            await tab.click("button")

            assert await settle_after_action(tab) == "no_request"
            assert await shown(tab) == "idle"

    async def test_an_action_that_sent_no_input(self) -> None:
        async with opened(_NOOP) as (_, tab):
            await tab.evaluate("void show('/api/data')", **_MAIN_WORLD)

            assert await settle_after_action(tab) == "untracked"
            assert await shown(tab) == "idle"

    async def test_a_wait_that_reaches_its_cap(self) -> None:
        async with opened(_SLOW) as (_, tab):
            await tab.click("button")
            started = time.perf_counter()

            assert await settle_after_action(tab, cap_ms=400) == "capped"
            assert time.perf_counter() - started < 2.5
            assert await shown(tab) == "idle"

    async def test_a_document_the_tracker_was_not_delivered_to(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(enhancers, "get_dom_enhancer_script", lambda: "")
        async with opened(LOAD) as (_, tab):
            assert await tab.evaluate("window.__myrm_spa_state === undefined", **_MAIN_WORLD) is True

            await tab.click("button")

            assert await settle_after_action(tab) == "untracked"
            assert await shown(tab) == "idle"


class TestTheStabilityFlagsOfThePage:
    async def test_they_follow_the_requests_and_the_changes_of_the_page(self) -> None:
        async with opened(LOAD) as (_, tab):
            await tab.click("button")

            during = await tab.evaluate(
                "({inflight: window.__myrm_spa_state.inflightRequests, stable: window.__myrm_spa_state.stable})",
                **_MAIN_WORLD,
            )
            async with asyncio.timeout(10):
                while not await tab.evaluate("window.__myrm_spa_state.stable", **_MAIN_WORLD):
                    await asyncio.sleep(0.1)

            assert during == {"inflight": 1, "stable": False}
            assert await tab.evaluate("window.__myrm_spa_state.inflightRequests", **_MAIN_WORLD) == 0
