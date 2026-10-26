"""Unit tests for BrowserSessionNetworkMixin network replay.

Covers replay_network_request: only a GET is re-sent (a recorded write was an action the user's own flow
already performed, and replaying it would perform it again without anyone approving it), credentials in a
replayed response body are redacted after the JS-side wider window and before the output cut, and a failed
replay says why.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.browser_session_network_mixin import (
    _REPLAY_ERROR_MAX,
    _REPLAY_OUTPUT_MAX,
    BrowserSessionNetworkMixin,
)
from myrm_agent_harness.toolkits.browser.session.network_intelligence import NetworkIntelligence


def _see(ni: NetworkIntelligence, url: str, method: str = "GET", post_data: str | None = None) -> None:
    request: dict[str, str] = {"url": url, "method": method}
    if post_data is not None:
        request["postData"] = post_data
    ni._on_request_will_be_sent({"requestId": "req-1", "type": "Fetch", "request": request})


class _StubSession(BrowserSessionNetworkMixin):
    """Minimal mixin stand-in: the replay path runs against a real NetworkIntelligence."""

    def __init__(self, *, tracked: bool = True) -> None:
        self._ensure_components = AsyncMock()
        page = MagicMock()
        self._tab_controller = MagicMock()
        self._tab_controller.get_active_page.return_value = page
        self._network_intelligence = NetworkIntelligence()
        if tracked:
            _see(self._network_intelligence, "https://api.example.com/data")
        self.page = page


class TestReplayRedaction:
    @pytest.mark.asyncio
    async def test_replay_output_redacted(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value='{"token":"sk-proj-abcdefghijklmnop12345678"}')

        result = await session.replay_network_request(1)

        assert "sk-proj-abcdefghijklmnop12345678" not in result
        assert "***" in result

    @pytest.mark.asyncio
    async def test_replay_output_crossing_cut_redacted(self):
        """A credential that would be cut by the 8000-char output limit must
        not survive as a plaintext fragment (JS returns a wider raw window)."""
        session = _StubSession()
        head = "x" * (_REPLAY_OUTPUT_MAX - 10)
        tail = '"password":"mysecretvalue12345678"}'
        session.page.evaluate = AsyncMock(return_value=head + tail)

        result = await session.replay_network_request(1)

        assert len(result) <= _REPLAY_OUTPUT_MAX
        assert "mysecretval" not in result

    @pytest.mark.asyncio
    async def test_replay_empty_response(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value="")

        result = await session.replay_network_request(1)

        assert result == "Empty response"

    @pytest.mark.asyncio
    async def test_replay_error_names_the_cause(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(side_effect=Exception("fetch failed"))

        result = await session.replay_network_request(1)

        assert result == "Error replaying request: fetch failed"

    @pytest.mark.asyncio
    async def test_replay_error_names_only_the_first_line_of_the_cause(self):
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
    async def test_replay_error_cause_is_redacted_and_bounded(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(
            side_effect=Exception("rejected sk-proj-abcdefghijklmnop12345678 " + "x" * 500)
        )

        result = await session.replay_network_request(1)

        assert "sk-proj-abcdefghijklmnop12345678" not in result
        assert len(result) <= len("Error replaying request: ") + _REPLAY_ERROR_MAX

    @pytest.mark.asyncio
    async def test_replay_error_without_a_message_names_the_exception_type(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(side_effect=TimeoutError())

        result = await session.replay_network_request(1)

        assert result == "Error replaying request: TimeoutError"

    @pytest.mark.asyncio
    async def test_replay_invalid_index(self):
        session = _StubSession(tracked=False)

        result = await session.replay_network_request(1)

        assert "Error: Invalid index" in result


class TestReplayIsReadOnly:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def test_a_recorded_write_is_refused_and_nothing_is_sent(self, method: str):
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
    async def test_the_refusal_does_not_echo_the_url_or_the_body(self):
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
    async def test_a_get_is_re_sent_as_a_plain_fetch_of_its_url(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(return_value="ok")

        assert await session.replay_network_request(1) == "ok"

        js_code = session.page.evaluate.call_args[0][0]
        assert 'fetch("https://api.example.com/data")' in js_code
        assert "method" not in js_code
        assert "body" not in js_code
        assert "Content-Type" not in js_code
