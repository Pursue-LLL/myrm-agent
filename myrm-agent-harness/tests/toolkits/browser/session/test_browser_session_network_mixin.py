"""Unit tests for BrowserSessionNetworkMixin network replay.

Covers replay_network_request: only a GET is re-sent (a recorded write was an action the user's own flow
already performed, and replaying it would perform it again without anyone approving it), credentials in a
replayed response body are redacted after the JS-side wider window and before the output cut, a failed
replay says why, the answer opens with the status the replay got (noting when the page's own request got
another), and a server that stops answering ends the replay at the timeout with what arrived.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.browser_session_network_mixin import (
    _REPLAY_ERROR_MAX,
    _REPLAY_JS,
    _REPLAY_OUTPUT_MAX,
    _REPLAY_RAW_WINDOW,
    _REPLAY_TIMEOUT_S,
    BrowserSessionNetworkMixin,
)
from myrm_agent_harness.toolkits.browser.session.network_intelligence import NetworkIntelligence, _CdpRequest


def _see(ni: NetworkIntelligence, url: str, method: str = "GET", post_data: str | None = None) -> None:
    request: _CdpRequest = {"url": url, "method": method}
    if post_data is not None:
        request["postData"] = post_data
    ni._on_request_will_be_sent({"requestId": "req-1", "type": "Fetch", "request": request})


class _StubSession(BrowserSessionNetworkMixin):
    """Minimal mixin stand-in: the replay path runs against a real NetworkIntelligence."""

    def __init__(self, *, tracked: bool = True) -> None:
        page = MagicMock()
        self._tab_controller = MagicMock()
        self._tab_controller.get_active_page.return_value = page
        self._network_intelligence = NetworkIntelligence()
        if tracked:
            _see(self._network_intelligence, "https://api.example.com/data")
        self.page = page

    async def _ensure_components(self) -> None:
        """The replay needs only the active page; no browser components are built."""


class TestReplayRedaction:
    @pytest.mark.asyncio
    async def test_replay_output_redacted(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[200, '{"token":"sk-proj-abcdefghijklmnop12345678"}', False])

        result = await session.replay_network_request(1)

        assert "sk-proj-abcdefghijklmnop12345678" not in result
        assert "***" in result

    @pytest.mark.asyncio
    async def test_replay_output_crossing_cut_redacted(self) -> None:
        """A credential that would be cut by the 8000-char output limit must
        not survive as a plaintext fragment (JS returns a wider raw window)."""
        session = _StubSession()
        head = "x" * (_REPLAY_OUTPUT_MAX - 10)
        tail = '"password":"mysecretvalue12345678"}'
        session.page.evaluate = AsyncMock(return_value=[200, head + tail, False])

        result = await session.replay_network_request(1)

        _status_line, body = result.split("\n", 1)
        assert len(body) <= _REPLAY_OUTPUT_MAX
        assert "mysecretval" not in result

    @pytest.mark.asyncio
    async def test_replay_empty_response(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[200, "", False])

        result = await session.replay_network_request(1)

        assert result == "[HTTP 200]\nEmpty response"

    @pytest.mark.asyncio
    async def test_replay_error_names_the_cause(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(side_effect=Exception("fetch failed"))

        result = await session.replay_network_request(1)

        assert result == "Error replaying request: fetch failed"

    @pytest.mark.asyncio
    async def test_replay_error_names_only_the_first_line_of_the_cause(self) -> None:
        """The driver appends the page-side stack; the model needs the reason, not the trace."""
        session = _StubSession()
        session.page.evaluate = AsyncMock(
            side_effect=Exception(
                "Page.evaluate: TypeError: Failed to fetch\n"
                "    at eval (eval at evaluate (:403:30))\n"
                "    at UtilityScript"
            )
        )

        result = await session.replay_network_request(1)

        assert result == "Error replaying request: Page.evaluate: TypeError: Failed to fetch"

    @pytest.mark.asyncio
    async def test_replay_error_cause_is_redacted_and_bounded(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(
            side_effect=Exception("rejected sk-proj-abcdefghijklmnop12345678 " + "x" * 500)
        )

        result = await session.replay_network_request(1)

        assert "sk-proj-abcdefghijklmnop12345678" not in result
        assert len(result) <= len("Error replaying request: ") + _REPLAY_ERROR_MAX

    @pytest.mark.asyncio
    async def test_replay_error_without_a_message_names_the_exception_type(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(side_effect=TimeoutError())

        result = await session.replay_network_request(1)

        assert result == "Error replaying request: TimeoutError"

    @pytest.mark.asyncio
    async def test_replay_invalid_index(self) -> None:
        session = _StubSession(tracked=False)

        result = await session.replay_network_request(1)

        assert "Error: Invalid index" in result


class TestReplayIsReadOnly:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def test_a_recorded_write_is_refused_and_nothing_is_sent(self, method: str) -> None:
        session = _StubSession(tracked=False)
        _see(
            session._network_intelligence,
            "https://api.example.com/orders?token=abc123",
            method=method,
            post_data='{"sku":"SKU-1"}',
        )
        session.page.evaluate = AsyncMock(return_value="created")

        result = await session.replay_network_request(1)

        assert result == (
            f"Error: network_replay re-sends GET requests only; request #1 is {method}. "
            "Perform that action on the page instead."
        )
        session.page.evaluate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_refusal_does_not_echo_the_url_or_the_body(self) -> None:
        session = _StubSession(tracked=False)
        _see(
            session._network_intelligence,
            "https://api.example.com/orders?token=abc123",
            method="POST",
            post_data='{"password":"mysecretvalue12345678"}',
        )

        result = await session.replay_network_request(1)

        assert "abc123" not in result
        assert "mysecretvalue12345678" not in result

    @pytest.mark.asyncio
    async def test_a_get_is_re_sent_as_a_plain_fetch_of_its_url(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[200, "ok", False])

        assert await session.replay_network_request(1) == "[HTTP 200]\nok"

        js_code, arguments = session.page.evaluate.call_args[0]
        assert arguments == ["https://api.example.com/data", _REPLAY_RAW_WINDOW, _REPLAY_TIMEOUT_S * 1000]
        assert "fetch(url, {signal: controller.signal})" in js_code
        assert "method" not in js_code
        assert "body:" not in js_code
        assert "Content-Type" not in js_code

    @pytest.mark.asyncio
    async def test_the_url_reaches_the_page_as_data_never_as_code(self) -> None:
        session = _StubSession(tracked=False)
        hostile = 'https://api.example.com/x?q="); document.cookie; ("'
        _see(session._network_intelligence, hostile)
        session.page.evaluate = AsyncMock(return_value=[200, "ok", False])

        await session.replay_network_request(1)

        js_code, arguments = session.page.evaluate.call_args[0]
        assert js_code == _REPLAY_JS
        assert arguments[0] == hostile


class TestReplayBounds:
    @pytest.mark.asyncio
    async def test_a_server_that_stops_mid_body_ends_the_replay_with_what_arrived(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[200, "data: hello", True])

        result = await session.replay_network_request(1)

        assert result == f"[HTTP 200]\nStopped after {_REPLAY_TIMEOUT_S} s: the body is partial.\ndata: hello"

    @pytest.mark.asyncio
    async def test_a_server_that_sent_headers_and_no_body_before_the_timeout_says_so(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[200, "", True])

        result = await session.replay_network_request(1)

        assert result == f"[HTTP 200]\nStopped after {_REPLAY_TIMEOUT_S} s: the body is partial.\nEmpty response"

    @pytest.mark.asyncio
    async def test_a_server_that_never_answers_is_an_error_not_a_status(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[0, "", True])

        result = await session.replay_network_request(1)

        assert result == f"Error replaying request: no response within {_REPLAY_TIMEOUT_S} s"


def _answered(session: _StubSession, status: int, request_id: str = "req-1") -> None:
    session._network_intelligence._on_response_received(
        {"requestId": request_id, "response": {"status": status, "mimeType": "application/json"}}
    )


class TestReplayStatusLine:
    @pytest.mark.asyncio
    async def test_the_answer_opens_with_the_status_the_replay_got(self) -> None:
        session = _StubSession()
        _answered(session, 200)
        session.page.evaluate = AsyncMock(return_value=[200, '{"ok":true}', False])

        assert await session.replay_network_request(1) == '[HTTP 200]\n{"ok":true}'

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [204, 401])
    async def test_an_empty_body_is_told_apart_by_its_status(self, status: int) -> None:
        session = _StubSession()
        _answered(session, status)
        session.page.evaluate = AsyncMock(return_value=[status, "", False])

        assert await session.replay_network_request(1) == f"[HTTP {status}]\nEmpty response"

    @pytest.mark.asyncio
    async def test_a_status_other_than_the_pages_own_request_got_says_so(self) -> None:
        session = _StubSession()
        _answered(session, 200)
        session.page.evaluate = AsyncMock(return_value=[401, '{"error":"unauthorized"}', False])

        assert await session.replay_network_request(1) == (
            "[HTTP 401] the page's own request got 200; "
            "replay re-sends the URL only, without the page's request headers\n"
            '{"error":"unauthorized"}'
        )

    @pytest.mark.asyncio
    async def test_nothing_is_compared_while_the_page_has_no_status(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value=[200, "x", False])

        assert await session.replay_network_request(1) == "[HTTP 200]\nx"

    @pytest.mark.asyncio
    async def test_nothing_is_compared_for_a_page_request_that_failed(self) -> None:
        session = _StubSession()
        session._network_intelligence._on_loading_failed(
            {"requestId": "req-1", "errorText": "net::ERR_FAILED", "canceled": False}
        )
        session.page.evaluate = AsyncMock(return_value=[200, "x", False])

        assert await session.replay_network_request(1) == "[HTTP 200]\nx"

    @pytest.mark.asyncio
    async def test_a_redirected_request_is_compared_with_the_status_the_page_finally_got(self) -> None:
        session = _StubSession(tracked=False)
        ni = session._network_intelligence
        ni._on_request_will_be_sent(
            {"requestId": "r", "type": "Fetch", "request": {"url": "https://api.example.com/hop", "method": "GET"}}
        )
        ni._on_request_will_be_sent(
            {
                "requestId": "r",
                "type": "Fetch",
                "request": {"url": "https://api.example.com/target", "method": "GET"},
                "redirectResponse": {"status": 302, "mimeType": ""},
            }
        )
        _answered(session, 200, request_id="r")

        session.page.evaluate = AsyncMock(return_value=[200, "ok", False])
        assert await session.replay_network_request(1) == "[HTTP 200]\nok"

        session.page.evaluate = AsyncMock(return_value=[403, "no", False])
        assert (await session.replay_network_request(1)).startswith("[HTTP 403] the page's own request got 200;")

    @pytest.mark.asyncio
    async def test_a_reply_that_is_not_a_status_and_a_body_is_reported_as_a_failed_replay(self) -> None:
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value="ok")

        assert (await session.replay_network_request(1)).startswith("Error replaying request: ")
