"""Real-Chromium proof of what network_log lists for a page whose resources fail.

A script that 404s is listed on its own line with no number, so the number 1 still opens the API request that
holds it; with no XHR/Fetch request at all (a white page) the failed script is still listed; a POST whose body is
not text keeps its record in the driver's log. The loopback server answers 404 for every path it is not given.
Run with: `pytest -m integration tests/toolkits/browser/session/test_network_log_listing_integration.py`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._local_browser_session import local_session
from tests.toolkits.browser._redirect_servers import Reply, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_JSON = "application/json"
_SETTLE_TIMEOUT_S = 10.0
_SETTLE_TIMEOUT_MS = 10_000
_BUNDLE = '<script src="/static/main.js"></script>'
# The page reads the response and says so: the browser keeps a body for network_detail once the page has read it.
_FETCH_API_AND_SIGNAL = "fetch('/api/ok').then(r => r.text()).then(() => { window.bodyRead = true })"


def _page(markup: str) -> Reply:
    return Reply(body=f"<!DOCTYPE html><html><head></head><body><div id=app></div>{markup}</body></html>".encode())


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while not condition():
            await asyncio.sleep(0.05)


async def _until_the_failed_script_is_logged(session: BrowserSession) -> None:
    await _until(lambda: bool(session._network_logger.get_other_failed_summary()))


async def test_a_script_that_404s_is_listed_without_a_number_and_number_one_still_opens_the_api_request() -> None:
    routes = {
        "/app": _page(f"{_BUNDLE}<script>{_FETCH_API_AND_SIGNAL}</script>"),
        "/api/ok": Reply(body=b'{"ok":1}', content_type=_JSON),
    }
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await session._tab_controller.get_active_page().wait_for_function(
                "window.bodyRead === true", timeout=_SETTLE_TIMEOUT_MS
            )
            await _until_the_failed_script_is_logged(session)

            lines = session.get_network_log().splitlines()

            assert lines[1] == f"  1. GET {site.url('/api/ok')} [200]"
            assert lines[-1] == f"  script GET {site.url('/static/main.js')} [404]"
            assert json.loads(await session.get_network_detail(1)) == {"ok": 1}


async def test_a_white_page_whose_script_404s_still_lists_the_script() -> None:
    with serve({"/app": _page(_BUNDLE)}) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until_the_failed_script_is_logged(session)

            lines = session.get_network_log().splitlines()

            assert lines[0] == "No API requests captured."
            assert lines[-1] == f"  script GET {site.url('/static/main.js')} [404]"


async def test_a_post_whose_body_is_not_text_keeps_its_record() -> None:
    upload = "fetch('/api/upload', {method: 'POST', body: new Uint8Array([0xff, 0xfe, 0x00, 0x80])})"
    routes = {"/app": _page(f"<script>{upload}</script>"), "/api/upload": Reply(body=b"{}", content_type=_JSON)}
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until(lambda: any(r.method == "POST" for r in session._network_logger._requests))

            posts = [r for r in session._network_logger._requests if r.method == "POST"]

            assert [(r.status, r.post_data_preview) for r in posts] == [(200, "<binary body>")]
