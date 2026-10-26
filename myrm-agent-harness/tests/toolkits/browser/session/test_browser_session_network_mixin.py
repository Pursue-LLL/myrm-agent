"""Unit tests for BrowserSessionNetworkMixin network replay redaction.

Covers replay_network_request output: credentials in replayed response bodies
must be redacted after the JS-side wider window and before the output cut.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.browser_session_network_mixin import (
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
    async def test_replay_uses_raw_post_data_not_redacted(self):
        """network_replay must re-send the real body; the redacted form would
        break authenticated replays."""
        session = _StubSession(tracked=False)
        _see(
            session._network_intelligence,
            "https://api.example.com/login",
            method="POST",
            post_data='{"op":"login","password":"mysecretvalue12345678"}',
        )
        session.page.evaluate = AsyncMock(return_value="ok")

        await session.replay_network_request(1)

        js_code = session.page.evaluate.call_args[0][0]
        assert "mysecretvalue12345678" in js_code
        assert "***" not in js_code

    @pytest.mark.asyncio
    async def test_replay_error_fallback(self):
        session = _StubSession()
        session.page.evaluate = AsyncMock(side_effect=Exception("fetch failed"))

        result = await session.replay_network_request(1)

        assert result == "Error replaying request"

    @pytest.mark.asyncio
    async def test_replay_invalid_index(self):
        session = _StubSession(tracked=False)

        result = await session.replay_network_request(1)

        assert "Error: Invalid index" in result
