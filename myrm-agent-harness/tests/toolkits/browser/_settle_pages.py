"""Pages that call a local server whose endpoints answer after a set time, for the real-Chromium settle tests.

[INPUT]
- toolkits.browser::BrowserSession (POS: the aggregate root every browser tool talks to)
- toolkits.browser.tools.interact::create_interact_tool (POS: the interact tool the agent calls)
- tests.toolkits.browser._download_integration::open_session (POS: a real session on a one-browser pool)
- tests.toolkits.browser._redirect_servers::Reply, page, serve (POS: scripted loopback replies and the server that serves them)

[OUTPUT]
- ENDPOINTS: the slow endpoints the pages call (``/api/data`` answers after 1 s, ``/api/longpoll`` after 20 s, ...)
- LOAD / document_with: a button that loads ``/api/data`` into ``#out``; a page with any control and that ``#out``
- opened: a session on such a page, with more pages and endpoints servable beside it
- act / click_center / shown: run one interact action the way the agent does and get its answer; click the middle of
  the button by coordinates; read what ``#out`` shows

[POS]
Test support for ``test_post_action_settle_integration`` and ``test_post_action_settle_scope_integration``. An endpoint
answers after a set time and the page writes its answer into ``#out``, so what ``#out`` shows at the moment an
interaction is answered tells whether the interaction waited for the response.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.tools.interact import create_interact_tool
from tests.toolkits.browser._download_integration import open_session
from tests.toolkits.browser._redirect_servers import Reply, page, serve

if TYPE_CHECKING:
    from patchright.async_api import Page

_REF = re.compile(r"\b(e\d+)\b")  # the first element ref of a snapshot of any page here


def _after(text: str, seconds: float) -> Reply:
    return Reply(body=text.encode(), content_type="text/plain", delay_s=seconds)


ENDPOINTS = {
    "/api/data": _after("data-ready", 1.0),
    "/login": _after("login-ready", 1.0),
    "/api/suggest": _after("suggest-ready", 0.6),
    "/api/first": _after("first", 0.4),
    "/api/second": _after("second-ready", 0.4),
    "/api/ping": _after("pong", 2.0),
    "/api/slow": _after("slow-ready", 3.0),
    "/api/longpoll": _after("late", 20.0),
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
LOAD = "<button onclick=\"show('/api/data')\">load</button>"


def document_with(control: str) -> Reply:
    """A page with ``control`` and an ``#out`` that shows the response of the last request the page made."""
    return page(f'{control}<div id="out">idle</div><script>{_SCRIPT}</script>')


@asynccontextmanager
async def opened(
    control: str, *, routes: Mapping[str, Reply] | None = None
) -> AsyncIterator[tuple[BrowserSession, Page]]:
    """A session on a page with ``control`` that calls the local server, which also serves ``routes``."""
    with serve({"/home": document_with(control), **ENDPOINTS, **(routes or {})}) as site:
        async with open_session(None, local=True) as session:
            await session.navigate(site.url("/home"))
            yield session, session.get_active_page()


async def shown(tab: Page) -> str:
    return await tab.inner_text("#out")


async def _ask(session: BrowserSession, arguments: Mapping[str, object]) -> str:
    answer = await create_interact_tool(session).ainvoke(dict(arguments))
    assert isinstance(answer, str), answer
    return answer


async def act(session: BrowserSession, **arguments: object) -> str:
    """Run one interact action the way the agent does, on the first element of the page unless ``ref`` says."""
    snapshot, _ = await session.snapshot()
    match = _REF.search(str(snapshot))
    assert match, f"no ref in the snapshot: {snapshot!r}"
    return await _ask(session, {"ref": match.group(1), **arguments})


async def click_center(session: BrowserSession, tab: Page) -> str:
    """Click the middle of the page's button by coordinates, the way the agent does in visual mode."""
    box = await tab.locator("button").bounding_box()
    assert box is not None
    return await _ask(session, {"action": "click", "x": box["x"] + box["width"] / 2, "y": box["y"] + box["height"] / 2})
