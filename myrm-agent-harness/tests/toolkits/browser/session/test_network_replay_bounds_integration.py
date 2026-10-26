"""Real-Chromium proof that network_replay stays bounded when the server misbehaves.

A body that never ends is cut at the window instead of being read whole, a server that stops mid-body ends the replay
at the timeout with what arrived, and one that never answers ends it with an error: the replay never waits for the
server's own patience. The timeout is shortened for the run; the loopback server holds those replies open far longer.
Run with: `pytest -m integration tests/toolkits/browser/session/test_network_replay_bounds_integration.py`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.session import browser_session_network_mixin
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
_TEST_TIMEOUT_S = 1
_HELD_OPEN_S = 8.0

_PAGE = Reply(
    body=(
        b"<!DOCTYPE html><html><head></head><body>app<script>"
        b"fetch('/api/endless').then(r => r.body.cancel());"
        b"fetch('/api/stall').then(r => r.body.cancel());"
        b"fetch('/api/hang').catch(() => {});"
        b"</script></body></html>"
    )
)
_ROUTES = {
    "/app": _PAGE,
    # 200 KB of the promised 50 MB, then silence: only a read that stops at the window answers before the timeout
    "/api/endless": Reply(
        body=b"a" * 200_000, content_type=_JSON, declared_length=50_000_000, hold_open_s=_HELD_OPEN_S
    ),
    "/api/stall": Reply(
        body=b"data: hello\n\n", content_type="text/event-stream", declared_length=1_000_000, hold_open_s=_HELD_OPEN_S
    ),
    "/api/hang": Reply(body=b"late", content_type=_JSON, delay_s=_HELD_OPEN_S),
}


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(_SETTLE_TIMEOUT_S):
        while not condition():
            await asyncio.sleep(0.05)


def _number_of(session: BrowserSession, path: str) -> int:
    return next(r.seq for r in session._network_intelligence.get_api_requests() if r.url.endswith(path))


@pytest.fixture(autouse=True)
def _short_replay_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser_session_network_mixin, "_REPLAY_TIMEOUT_S", _TEST_TIMEOUT_S)


async def _replay(path: str) -> tuple[str, float]:
    with serve(_ROUTES) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))
            await _until(lambda: len(session._network_intelligence.get_api_requests()) == 3)
            started = time.monotonic()
            answer = await session.replay_network_request(_number_of(session, path))
            return answer, time.monotonic() - started


async def test_a_body_that_never_ends_is_cut_at_the_window_and_answers_before_the_timeout() -> None:
    answer, elapsed = await _replay("/api/endless")

    status_line, body = answer.split("\n", 1)
    assert status_line == "[HTTP 200]"
    assert body == "a" * browser_session_network_mixin._REPLAY_OUTPUT_MAX
    assert elapsed < _TEST_TIMEOUT_S


async def test_a_server_that_stops_mid_body_ends_the_replay_at_the_timeout_with_what_arrived() -> None:
    answer, elapsed = await _replay("/api/stall")

    assert answer == f"[HTTP 200]\nStopped after {_TEST_TIMEOUT_S} s: the body is partial.\ndata: hello\n\n"
    assert _TEST_TIMEOUT_S / 2 < elapsed < _HELD_OPEN_S


async def test_a_server_that_never_answers_ends_the_replay_with_an_error() -> None:
    answer, elapsed = await _replay("/api/hang")

    assert answer == f"Error replaying request: no response within {_TEST_TIMEOUT_S} s"
    assert _TEST_TIMEOUT_S / 2 < elapsed < _HELD_OPEN_S
