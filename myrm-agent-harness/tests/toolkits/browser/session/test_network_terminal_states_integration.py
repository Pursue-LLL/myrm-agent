"""Real-Chromium proof that network_log / network_detail / network_replay tell the truth about a page's requests.

A redirect hop names its status and its successor, a failed request names the browser's error, and a replay
re-sends a GET but never a write. The loopback server records every request it receives, so a refused replay
is proven by the server's hit count, not by what the browser-side answer says. Run with:
`pytest -m integration tests/toolkits/browser/session/test_network_terminal_states_integration.py`.
"""

from __future__ import annotations

import asyncio

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._local_browser_session import local_session
from tests.toolkits.browser._redirect_servers import Reply, redirect, serve

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


async def _body_once_loaded(session: BrowserSession, index: int) -> str:
    """The response body of request `index`; Chrome serves it only once the body has finished loading."""
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while True:
            answer = await session.get_network_detail(index)
            if not answer.startswith("Error retrieving response body"):
                return answer
            await asyncio.sleep(0.05)


def _log_lines(session: BrowserSession) -> list[str]:
    return [line.strip() for line in session._network_intelligence.get_summary().splitlines() if line.strip()]


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
