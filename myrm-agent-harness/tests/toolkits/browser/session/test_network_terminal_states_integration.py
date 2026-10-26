"""Real-Chromium proof that network_log / network_detail / network_replay tell the truth about a page's requests.

A redirect hop names its status and its successor, a failed request names the browser's error, a response the
page dropped after it arrived keeps the status the server gave, and a replay re-sends a GET but never a write.
Chrome's own `Network.loadingFailed` events are recorded alongside as the control for what the tool reports. The
loopback server records every request it receives, so a refused replay is proven by the server's hit count, not
by what the browser-side answer says. Run with:
`pytest -m integration tests/toolkits/browser/session/test_network_terminal_states_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._local_browser_session import local_session
from tests.toolkits.browser._redirect_servers import Gated, Reply, redirect, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_JSON = "application/json"
_SETTLE_TIMEOUT_S = 10.0


def _script_page(script: str) -> Reply:
    return Reply(body=f"<!DOCTYPE html><html><head></head><body>app<script>{script}</script></body></html>".encode())


async def _until_every_request_has_ended(session: BrowserSession, expected: int) -> None:
    """Wait until `expected` API requests are tracked and none is still in flight."""
    network = session._network_intelligence
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while True:
            tracked = network.get_api_requests()
            if len(tracked) >= expected and all(r.status or r.failure for r in tracked):
                return
            await asyncio.sleep(0.05)


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while not condition():
            await asyncio.sleep(0.05)


async def _record_chrome_failures(session: BrowserSession) -> list[dict[str, object]]:
    """Collect the raw `Network.loadingFailed` events Chrome sends (the tool's own listener was attached first)."""
    page = session.get_active_page()
    events: list[dict[str, object]] = []
    cdp = await page.context.new_cdp_session(page)
    cdp.on("Network.loadingFailed", lambda event: events.append(event))
    await cdp.send("Network.enable")
    return events


async def _body_once_loaded(session: BrowserSession, index: int) -> str:
    """The response body of request `index`; Chrome serves it only once the body has finished loading."""
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while True:
            answer = await session.get_network_detail(index)
            if not answer.startswith("The browser kept no body"):
                return answer
            await asyncio.sleep(0.05)


def _log_lines(session: BrowserSession) -> list[str]:
    return [line.strip() for line in session._network_intelligence.get_summary().splitlines() if line.strip()]


def _number_of(session: BrowserSession, path: str) -> int:
    """The network_log number of the API request whose URL ends with `path`."""
    return next(r.seq for r in session._network_intelligence.get_api_requests() if r.url.endswith(path))


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
async def test_every_redirect_status_labels_its_hop_and_points_at_the_request_that_carries_on(status: int) -> None:
    routes = {
        "/app": _script_page("fetch('/api/hop')"),
        "/api/hop": redirect("/api/target", status=status),
        "/api/target": Reply(body=b'{"ok": true}', content_type=_JSON),
    }
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=2)

            lines = _log_lines(session)
            assert lines[0].endswith(f"/api/hop [{status}]"), lines
            assert lines[1].endswith("/api/target [200]"), lines
            assert await session.get_network_detail(1) == f"Redirected ({status}); the response is request #2"
            assert '"ok": true' in await _body_once_loaded(session, 2)


async def test_a_request_the_browser_refuses_reads_as_failed_with_the_browsers_own_error() -> None:
    routes = {"/app": _script_page("fetch('http://127.0.0.1:1/never').catch(() => {})")}
    with serve(routes) as site:
        async with local_session() as session:
            page = session.get_active_page()
            reported_by_chrome: list[str] = []
            cdp = await page.context.new_cdp_session(page)
            cdp.on("Network.loadingFailed", lambda event: reported_by_chrome.append(event["errorText"]))
            await cdp.send("Network.enable")

            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=1)

            assert reported_by_chrome and reported_by_chrome[0].startswith("net::ERR_"), "control: Chrome failed it"
            (line,) = _log_lines(session)
            assert f"[failed: {reported_by_chrome[0]}" in line
            assert "[pending]" not in line
            assert (await session.get_network_detail(1)).startswith(f"Request failed: {reported_by_chrome[0]}")


async def test_a_request_the_domain_filter_aborts_reads_as_failed_and_never_reaches_the_server() -> None:
    routes = {"/app": _script_page("fetch('/api/blocked').catch(() => {})")}
    with serve(routes) as site:
        async with local_session() as session:
            # The abort `domain_filter/http_filter.py::_abort_route_safely` issues for a request it refuses.
            await session.get_active_page().route("**/api/blocked", lambda route: route.abort("blockedbyclient"))
            chrome_failures = await _record_chrome_failures(session)
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=1)
            await _until(lambda: len(chrome_failures) == 1)

            error = str(chrome_failures[0]["errorText"])
            assert error.startswith("net::ERR_BLOCKED_BY_CLIENT"), "control: Chrome reports it as a client block"
            assert chrome_failures[0]["canceled"] is False, "control: a block is a failure, not a drop"
            (line,) = _log_lines(session)
            assert line.endswith(f"/api/blocked [failed: {error}]"), line
            assert await session.get_network_detail(1) == f"Request failed: {error}"
            assert "/api/blocked" not in site.paths()


async def test_a_response_the_page_never_reads_keeps_the_status_the_server_gave() -> None:
    routes = {
        "/app": _script_page("fetch('/api/orders/7', {method: 'DELETE'}); fetch('/api/ping'); fetch('/api/me')"),
        "/api/orders/7": Reply(status=204),
        "/api/ping": Reply(),
        "/api/me": Reply(status=401),
    }
    with serve(routes) as site:
        async with local_session() as session:
            chrome_failures = await _record_chrome_failures(session)
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=3)
            await _until(lambda: len(chrome_failures) == 3)

            assert all(event["canceled"] for event in chrome_failures), "control: Chrome calls each of them canceled"
            assert [line.rsplit(" ", 1)[1] for line in _log_lines(session)] == ["[204]", "[200]", "[401]"]


async def test_a_body_the_server_cut_short_still_reads_as_failed() -> None:
    routes = {
        "/app": _script_page("fetch('/api/export').then(r => r.text()).catch(() => {})"),
        "/api/export": Reply(body=b"0123456789", content_type="text/plain", declared_length=1000),
    }
    with serve(routes) as site:
        async with local_session() as session:
            chrome_failures = await _record_chrome_failures(session)
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=1)
            await _until(lambda: len(chrome_failures) == 1)

            error = chrome_failures[0]["errorText"]
            assert chrome_failures[0]["canceled"] is False, "control: a cut-off body is a failure, not a drop"
            (line,) = _log_lines(session)
            assert line.endswith(f"[failed: {error}]"), line
            assert await session.get_network_detail(1) == f"Request failed: {error}"


async def test_a_page_that_aborts_after_the_headers_keeps_the_answer_and_one_that_aborts_before_them_fails() -> None:
    routes = {
        "/app": _script_page(
            "const early = new AbortController();"
            "fetch('/api/stream', {signal: early.signal}).then(() => early.abort()).catch(() => {});"
            "const late = new AbortController();"
            "fetch('/api/slow', {signal: late.signal}).catch(() => {});"
            "setTimeout(() => late.abort(), 300)"
        ),
        "/api/stream": Reply(body=b"x" * 2000, content_type="text/plain", declared_length=100_000, hold_open_s=3.0),
        "/api/slow": Reply(body=b"late", delay_s=3.0),
    }
    with serve(routes) as site:
        async with local_session() as session:
            chrome_failures = await _record_chrome_failures(session)
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=2)
            await _until(lambda: len(chrome_failures) == 2)

            assert all(event["canceled"] for event in chrome_failures), "control: both are aborts by the page"
            stream, slow = _log_lines(session)
            assert stream.endswith("/api/stream [200]"), stream
            assert slow.endswith("/api/slow [failed: net::ERR_ABORTED]"), slow


async def test_network_detail_says_why_a_response_has_no_body() -> None:
    routes = {
        "/app": _script_page(
            "fetch('/api/orders/7', {method: 'DELETE'}); fetch('/api/ping'); fetch('/api/empty').then(r => r.text())"
        ),
        "/api/orders/7": Reply(status=204),
        "/api/ping": Reply(),
        "/api/empty": Reply(),
    }
    with serve(routes) as site:
        async with local_session() as session:
            chrome_failures = await _record_chrome_failures(session)
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=3)
            await _until(lambda: len(chrome_failures) == 2)

            assert await session.get_network_detail(1) == "No response body (status 204)"
            assert await session.get_network_detail(2) == (
                "The browser kept no body for this request: it may still be loading, or the page dropped it"
            )
            assert await _body_once_loaded(session, 3) == "Empty response"


async def test_a_replay_re_sends_a_get_and_never_reaches_the_server_with_a_write() -> None:
    routes = {
        "/app": _script_page(
            "fetch('/api/items');"
            "fetch('/api/orders', {method: 'POST', body: '{}'});"
            "fetch('/api/items/7', {method: 'DELETE'});"
            "fetch('/api/drafts/7', {method: 'PUT', body: '{}'})"
        ),
        "/api/items": Reply(body=b'{"items": [7]}', content_type=_JSON),
        "/api/orders": Reply(status=201, body=b'{"id": 1}', content_type=_JSON),
        "/api/items/7": Reply(body=b'{"deleted": true}', content_type=_JSON),
        "/api/drafts/7": Reply(body=b'{"saved": true}', content_type=_JSON),
    }
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=4)
            number = {r.method: r.seq for r in session._network_intelligence.get_api_requests()}
            writes_before = [hit for hit in site.hits if hit[0] != "GET"]
            assert sorted(method for method, _ in writes_before) == ["DELETE", "POST", "PUT"], "control: the page wrote"

            assert '"items": [7]' in await session.replay_network_request(number["GET"])
            assert site.paths("GET").count("/api/items") == 2

            for method in ("POST", "DELETE", "PUT"):
                answer = await session.replay_network_request(number[method])
                assert answer.startswith(
                    f"Error: network_replay re-sends GET requests only; request #{number[method]} is {method}"
                )
            assert [hit for hit in site.hits if hit[0] != "GET"] == writes_before, "a refused replay reached the server"


async def test_a_replay_names_the_status_it_got_and_says_when_the_page_got_another() -> None:
    routes: dict[str, Reply | Gated] = {
        "/app": _script_page(
            "fetch('/api/orders', {headers: {Authorization: 'Bearer t0k3n'}}); fetch('/api/items'); fetch('/api/ping')"
        ),
        "/api/orders": Gated(
            header="Authorization",
            value="Bearer t0k3n",
            reply=Reply(body=b'[{"id": 1}]', content_type=_JSON),
            otherwise=Reply(status=401, body=b'{"error": "unauthorized"}', content_type=_JSON),
        ),
        "/api/items": Reply(body=b'{"items": [7]}', content_type=_JSON),
        "/api/ping": Reply(status=204),
    }
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until_every_request_has_ended(session, expected=3)

            items = await session.replay_network_request(_number_of(session, "/api/items"))
            ping = await session.replay_network_request(_number_of(session, "/api/ping"))
            orders = await session.replay_network_request(_number_of(session, "/api/orders"))

            assert items == '[HTTP 200]\n{"items": [7]}'
            assert ping == "[HTTP 204]\nEmpty response"
            assert orders == (
                "[HTTP 401] the page's own request got 200; "
                "replay re-sends the URL only, without the page's request headers\n"
                '{"error": "unauthorized"}'
            )
