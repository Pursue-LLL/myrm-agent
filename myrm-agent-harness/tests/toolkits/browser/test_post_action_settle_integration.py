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
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from patchright.async_api import Page

from myrm_agent_harness.toolkits.browser import BrowserSession, enhancers
from myrm_agent_harness.toolkits.browser.tools.interact import create_interact_tool
from myrm_agent_harness.toolkits.browser.wait import settle_after_action
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_integration import open_session
from tests.toolkits.browser._redirect_servers import Reply, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_MAIN_WORLD = {"isolated_context": False}
_REF = re.compile(r"\b(e\d+)\b")  # the first element ref of a snapshot of any page here


def _answer(text: str, after_s: float) -> Reply:
    return Reply(body=text.encode(), content_type="text/plain", delay_s=after_s)


_ENDPOINTS = {
    "/api/data": _answer("data-ready", 1.0),
    "/login": _answer("login-ready", 1.0),
    "/api/suggest": _answer("suggest-ready", 0.6),
    "/api/first": _answer("first", 0.4),
    "/api/second": _answer("second-ready", 0.4),
    "/api/ping": _answer("pong", 2.0),
    "/api/slow": _answer("slow-ready", 3.0),
    "/api/longpoll": _answer("late", 20.0),
}
_SCRIPT = """
async function show(path) {
  const response = await fetch(path);
  document.getElementById('out').textContent = await response.text();
}
function showByXhr(path) {
  const request = new XMLHttpRequest();
  request.open('GET', path);
  request.onload = () => { document.getElementById('out').textContent = request.responseText; };
  request.send();
}
async function chain() { await show('/api/first'); await show('/api/second'); }
"""
_LOAD = "<button onclick=\"show('/api/data')\">load</button>"
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


def _page_with(control: str) -> Reply:
    return page(f'{control}<div id="out">idle</div><script>{_SCRIPT}</script>')


@asynccontextmanager
async def _opened(control: str) -> AsyncIterator[tuple[BrowserSession, Page]]:
    """A session on a page with ``control`` that calls the local server."""
    with serve({"/home": _page_with(control), **_ENDPOINTS}) as site:
        async with open_session(None, local=True) as session:
            await session.navigate(site.url("/home"))
            yield session, session.get_active_page()


async def _shown(tab: Page) -> str:
    return await tab.inner_text("#out")


async def _act(session: BrowserSession, **arguments: object) -> None:
    """Run one interact action the way the agent does, on the first element of the page."""
    snapshot, _ = await session.snapshot()
    match = _REF.search(str(snapshot))
    assert match, f"no ref in the snapshot: {snapshot!r}"
    await create_interact_tool(session).ainvoke({"ref": match.group(1), **arguments})


class TestAnActionIsAnsweredAfterTheResponseItAskedFor:
    @pytest.mark.parametrize(
        ("control", "shown"), [(_LOAD, "data-ready"), (_XHR, "data-ready"), (_LOGIN, "login-ready")]
    )
    async def test_a_click_waits_for_the_request_of_its_handler(self, control: str, shown: str) -> None:
        async with _opened(control) as (session, tab):
            await _act(session, action="click")

            assert await _shown(tab) == shown

    async def test_a_double_click_waits_for_the_request_of_its_handler(self) -> None:
        async with _opened(_LOAD.replace("onclick", "ondblclick")) as (session, tab):
            await _act(session, action="dblclick")

            assert await _shown(tab) == "data-ready"

    @pytest.mark.parametrize("action", ["fill", "type"])
    async def test_typing_waits_for_the_request_the_input_makes(self, action: str) -> None:
        async with _opened(_SUGGEST) as (session, tab):
            await _act(session, action=action, text="re")

            assert await _shown(tab) == "suggest-ready"

    async def test_a_key_press_waits_for_the_request_it_makes(self) -> None:
        keyed = "<input onkeydown=\"if (event.key === 'Enter') show('/api/data')\">"
        async with _opened(keyed) as (session, tab):
            await _act(session, action="press", text="Enter")

            assert await _shown(tab) == "data-ready"

    async def test_a_click_by_coordinates_waits_the_same(self) -> None:
        async with _opened(_LOAD) as (session, tab):
            box = await tab.locator("button").bounding_box()
            assert box is not None

            await create_interact_tool(session).ainvoke(
                {"action": "click", "x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2}
            )

            assert await _shown(tab) == "data-ready"

    async def test_a_request_started_when_the_pointer_goes_down_is_waited_for(self) -> None:
        async with _opened(_PRESS) as (session, tab):
            await _act(session, action="click")

            assert await _shown(tab) == "data-ready"

    async def test_a_response_the_page_draws_a_moment_later_is_on_the_page(self) -> None:
        async with _opened(_DRAWN_LATE) as (session, tab):
            await _act(session, action="click")

            assert await _shown(tab) == "data-ready"

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
        with serve({"/home": strict, "/app.js": app, **_ENDPOINTS}) as site:
            async with open_session(None, local=True) as session:
                await session.navigate(site.url("/home"))
                await _act(session, action="click")

                assert await _shown(session.get_active_page()) == "data-ready"

    async def test_a_request_that_follows_another_is_waited_for_too(self) -> None:
        async with _opened(_CHAIN) as (session, tab):
            await _act(session, action="click")

            assert await _shown(tab) == "second-ready"


class TestWhatIsNotWaitedFor:
    async def test_a_request_already_in_flight_when_the_action_began(self) -> None:
        async with _opened(_NOOP) as (_, tab):
            await tab.evaluate("void fetch('/api/longpoll')", **_MAIN_WORLD)
            await tab.click("button")
            started = time.perf_counter()

            assert await settle_after_action(tab) == "no_request"
            assert time.perf_counter() - started < 2.0

    async def test_a_beacon(self) -> None:
        async with _opened(_BEACON) as (_, tab):
            await tab.click("button")

            assert await settle_after_action(tab) == "no_request"
            assert await _shown(tab) == "idle"

    async def test_an_action_that_sent_no_input(self) -> None:
        async with _opened(_NOOP) as (_, tab):
            await tab.evaluate("void show('/api/data')", **_MAIN_WORLD)

            assert await settle_after_action(tab) == "untracked"
            assert await _shown(tab) == "idle"

    async def test_a_wait_that_reaches_its_cap(self) -> None:
        async with _opened(_SLOW) as (_, tab):
            await tab.click("button")
            started = time.perf_counter()

            assert await settle_after_action(tab, cap_ms=400) == "capped"
            assert time.perf_counter() - started < 2.5
            assert await _shown(tab) == "idle"

    async def test_a_document_the_tracker_was_not_delivered_to(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(enhancers, "get_dom_enhancer_script", lambda: "")
        async with _opened(_LOAD) as (_, tab):
            assert await tab.evaluate("window.__myrm_spa_state === undefined", **_MAIN_WORLD) is True

            await tab.click("button")

            assert await settle_after_action(tab) == "untracked"
            assert await _shown(tab) == "idle"


class TestTheStabilityFlagsOfThePage:
    async def test_they_follow_the_requests_and_the_changes_of_the_page(self) -> None:
        async with _opened(_LOAD) as (_, tab):
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
