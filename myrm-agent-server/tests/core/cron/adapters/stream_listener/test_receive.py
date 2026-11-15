"""Integration tests for StreamListenerManager: what a stream receives.

Uses real aiohttp.web test server for WS/SSE — no mock on network I/O.
SSRF guard is bypassed only for localhost test server connectivity;
a dedicated test verifies that SSRF actually blocks private IPs.

Covers:
- SSRF rejection for private IP URLs
- WS connection + message receipt + filter (json_path, regex)
- SSE connection + W3C multi-line data parsing
- extract_json_path shared utility
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.triggers import StreamProtocol, StreamTrigger

from app.core.cron.adapters.stream_listener import (
    StreamListenerManager,
    extract_json_path,
)
from tests.support.stream_listener_server import SSRF_OK, ServerContext

# ---------------------------------------------------------------------------
# Tests: extract_json_path (shared utility)
# ---------------------------------------------------------------------------


class TestExtractJsonPath:
    def test_simple_dotted_path(self) -> None:
        data = '{"a": {"b": {"c": "value"}}}'
        assert extract_json_path(data, "$.a.b.c") == "value"

    def test_root_field(self) -> None:
        assert extract_json_path('{"key": 42}', "$.key") == "42"

    def test_array_index(self) -> None:
        assert extract_json_path('{"items": [10, 20, 30]}', "$.items.1") == "20"

    def test_missing_key_returns_none(self) -> None:
        assert extract_json_path('{"a": 1}', "$.b") is None

    def test_invalid_json_returns_none(self) -> None:
        assert extract_json_path("not-json", "$.a") is None

    def test_empty_path_returns_full(self) -> None:
        result = extract_json_path('{"x": 1}', "$")
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: SSRF integration (no mock — verifies real SSRF guard)
# ---------------------------------------------------------------------------


class TestStreamSSRF:
    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_ip(self) -> None:
        """SSRF guard must reject 127.0.0.1 (private) without allowlist."""
        mgr = StreamListenerManager()
        trigger = StreamTrigger(url="ws://127.0.0.1:9999/ws")
        on_event = AsyncMock()

        with pytest.raises(ValueError, match="SSRF"):
            await mgr.start_stream("job-ssrf", trigger, on_event)

        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_internal_hostname(self) -> None:
        """SSRF guard blocks hostnames resolving to private IPs."""
        mgr = StreamListenerManager()
        trigger = StreamTrigger(url="ws://localhost:9999/ws")
        on_event = AsyncMock()

        with pytest.raises(ValueError, match="SSRF"):
            await mgr.start_stream("job-ssrf-host", trigger, on_event)

        await mgr.stop_all()


# ---------------------------------------------------------------------------
# Tests: WebSocket integration (real aiohttp server)
# ---------------------------------------------------------------------------


class TestStreamWS:
    @pytest.mark.asyncio
    async def test_ws_receives_message(self, test_server: ServerContext) -> None:
        test_server.app["_ws_messages"] = ['{"event": "ping"}']

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(url=test_server.ws_url(), protocol=StreamProtocol.WS)

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("ws-test", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        call_args = on_event.call_args_list[0]
        assert call_args[0][0] == "ws-test"
        assert '"ping"' in call_args[0][2]

    @pytest.mark.asyncio
    async def test_ws_json_path_filter(self, test_server: ServerContext) -> None:
        test_server.app["_ws_messages"] = ['{"data": {"status": "ok"}}', '{"data": {"other": "x"}}']

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.ws_url(),
            protocol=StreamProtocol.WS,
            filter_json_path="$.data.status",
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("ws-filter", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1

    @pytest.mark.asyncio
    async def test_ws_regex_filter_no_match(self, test_server: ServerContext) -> None:
        test_server.app["_ws_messages"] = ['{"value": "hello"}']

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.ws_url(),
            protocol=StreamProtocol.WS,
            filter_regex="^NEVER_MATCH$",
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("ws-regex-no", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count == 0


# ---------------------------------------------------------------------------
# Tests: SSE integration (real aiohttp server, W3C multi-line)
# ---------------------------------------------------------------------------


class TestStreamSSE:
    @pytest.mark.asyncio
    async def test_sse_single_data_line(self, test_server: ServerContext) -> None:
        test_server.app["_sse_lines"] = ["data: hello-sse", ""]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("sse-single", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == "hello-sse"

    @pytest.mark.asyncio
    async def test_sse_multiline_data(self, test_server: ServerContext) -> None:
        """W3C SSE: multiple data: lines concatenated with newlines."""
        test_server.app["_sse_lines"] = ["data: line1", "data: line2", "data: line3", ""]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("sse-multi", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        payload = on_event.call_args_list[0][0][2]
        assert payload == "line1\nline2\nline3"

    @pytest.mark.asyncio
    async def test_sse_ignores_comments(self, test_server: ServerContext) -> None:
        test_server.app["_sse_lines"] = [": this is a comment", "data: real-data", ""]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("sse-comment", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == "real-data"
