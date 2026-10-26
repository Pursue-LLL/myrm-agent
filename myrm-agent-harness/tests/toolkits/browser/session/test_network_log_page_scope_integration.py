"""Real-Chromium proof that network_log lists the page being looked at, and only data.

A new document, a reload and a tab switch each start the list over, a `pushState` route change does not, a failed
script of the page that was left is not listed on the next one, and an image or font the page fetched is counted
rather than listed. Numbers are never reused, so an earlier page's number is refused with the numbers valid now.
Run with: `pytest -m integration tests/toolkits/browser/session/test_network_log_page_scope_integration.py`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.session.browser_session_network_mixin import _API_LIST_HEADER
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
_EARLIER_PAGES = "(not listed: requests of earlier pages)"


def _page(script: str = "", markup: str = "") -> Reply:
    return Reply(
        body=f"<!DOCTYPE html><html><head></head><body>app{markup}<script>{script}</script></body></html>".encode()
    )


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while not condition():
            await asyncio.sleep(0.05)


async def _until_answered(session: BrowserSession, count: int) -> None:
    """Wait until the current page has `count` API requests and every one of them has an outcome."""
    network = session._network_intelligence
    await _until(
        lambda: (
            len(network.get_api_requests()) >= count and all(r.status or r.failure for r in network.get_api_requests())
        )
    )


def _routes() -> dict[str, Reply]:
    return {
        "/one": _page("fetch('/api/one')"),
        "/two": _page("fetch('/api/two')"),
        "/api/one": Reply(body=b'{"page":1}', content_type=_JSON),
        "/api/two": Reply(body=b'{"page":2}', content_type=_JSON),
        "/api/again": Reply(body=b'{"again":true}', content_type=_JSON),
    }


async def test_a_new_page_lists_its_own_requests_and_refuses_the_number_of_the_page_it_left() -> None:
    with serve(_routes()) as site:
        async with local_session() as session:
            await session.navigate(site.url("/one"))
            await _until_answered(session, 1)
            assert session.get_network_log().splitlines()[1] == f"  1. GET {site.url('/api/one')} [200]"

            await session.navigate(site.url("/two"))
            await _until_answered(session, 1)

            assert session.get_network_log().splitlines() == [
                _API_LIST_HEADER,
                f"  2. GET {site.url('/api/two')} [200]",
                _EARLIER_PAGES,
            ]
            assert (await session.get_network_detail(1)).startswith("Error: Invalid index 1. Valid range: 2;")
            assert json.loads(await session.get_network_detail(2)) == {"page": 2}


async def test_a_reload_starts_the_list_over() -> None:
    with serve(_routes()) as site:
        async with local_session() as session:
            await session.navigate(site.url("/one"))
            await _until_answered(session, 1)

            await session.get_active_page().reload()
            await _until(lambda: [r.seq for r in session._network_intelligence.get_api_requests()] == [2])

            assert session.get_network_log().splitlines()[1].startswith("  2. GET ")
            assert (await session.get_network_detail(1)).startswith("Error: Invalid index 1.")


async def test_a_route_change_without_a_new_document_keeps_the_list() -> None:
    with serve(_routes()) as site:
        async with local_session() as session:
            await session.navigate(site.url("/one"))
            await _until_answered(session, 1)

            await session.get_active_page().evaluate(
                "() => { history.pushState({}, '', '/route-2'); fetch('/api/again') }"
            )
            await _until_answered(session, 2)

            assert session.get_network_log().splitlines() == [
                _API_LIST_HEADER,
                f"  1. GET {site.url('/api/one')} [200]",
                f"  2. GET {site.url('/api/again')} [200]",
            ]


async def test_images_and_fonts_the_page_fetched_are_counted_not_listed() -> None:
    routes = {
        "/app": _page("fetch('/api/one'); fetch('/logo.png'); fetch('/font.woff2')"),
        "/api/one": Reply(body=b'{"page":1}', content_type=_JSON),
        "/logo.png": Reply(body=b"\x89PNG\r\n\x1a\n" + bytes(32), content_type="image/png"),
        "/font.woff2": Reply(body=b"wOF2" + bytes(32), content_type="font/woff2"),
    }
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until(lambda: session._network_intelligence.hidden_summary().startswith("(not listed: 2 image"))
            await _until_answered(session, 1)

            assert session.get_network_log().splitlines() == [
                _API_LIST_HEADER,
                f"  1. GET {site.url('/api/one')} [200]",
                "(not listed: 2 image, audio, video and font responses)",
            ]
            assert (await session.get_network_detail(2)).startswith("Error: Invalid index 2. Valid range: 1;")


async def test_a_script_that_failed_on_the_page_left_is_not_listed_on_the_next_one() -> None:
    routes = {"/one": _page(markup='<script src="/missing.js"></script>'), "/two": _page()}
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/one"))
            await _until(lambda: bool(session._network_logger.get_other_failed_summary()))
            assert "/missing.js" in session.get_network_log()

            await session.navigate(site.url("/two"))

            assert session.get_network_log() == "No API requests captured."


async def test_switching_tabs_lists_the_tab_now_shown_and_not_the_one_left() -> None:
    with serve(_routes()) as site:
        async with local_session() as session:
            first = session.get_active_tab_id()
            await session.navigate(site.url("/one"))
            await _until_answered(session, 1)

            await session.new_tab()
            await session.navigate(site.url("/two"))
            await _until_answered(session, 1)
            assert session.get_network_log().splitlines()[1] == f"  2. GET {site.url('/api/two')} [200]"

            await session.switch_tab(first)

            assert session.get_network_log().splitlines() == ["No API requests captured.", _EARLIER_PAGES]
            await session.get_active_page().evaluate("() => fetch('/api/again')")
            await _until_answered(session, 1)
            assert session.get_network_log().splitlines()[1] == f"  3. GET {site.url('/api/again')} [200]"
