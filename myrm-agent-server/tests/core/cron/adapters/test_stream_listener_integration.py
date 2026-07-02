"""Integration tests for StreamListenerManager.

Uses real aiohttp.web test server for WS/SSE — no mock on network I/O.
SSRF guard is bypassed only for localhost test server connectivity;
a dedicated test verifies that SSRF actually blocks private IPs.

Covers:
- SSRF rejection for private IP URLs
- WS connection + message receipt + filter (json_path, regex)
- SSE connection + W3C multi-line data parsing
- Concurrent stream limit enforcement
- start/stop lifecycle
- extract_json_path shared utility
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import aiohttp
import aiohttp.web
import pytest
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult
from myrm_agent_harness.toolkits.cron.triggers import StreamProtocol, StreamTrigger

from app.core.cron.adapters.stream_listener import (
    StreamListenerManager,
    extract_json_path,
)

_SSRF_OK = SSRFResult(safe=True, hostname="localhost", resolved_ips=("127.0.0.1",))


# ---------------------------------------------------------------------------
# Fixtures: in-process aiohttp test server with WS & SSE endpoints
# ---------------------------------------------------------------------------

async def _ws_handler(request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
    ws = aiohttp.web.WebSocketResponse()
    await ws.prepare(request)
    messages = request.app.get("_ws_messages", [])
    for msg in messages:
        await ws.send_str(msg)
        await asyncio.sleep(0.01)
    close_event: asyncio.Event = request.app["_ws_close_event"]
    await close_event.wait()
    await ws.close()
    return ws


async def _sse_handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
    resp = aiohttp.web.StreamResponse()
    resp.content_type = "text/event-stream"
    await resp.prepare(request)
    lines: list[str] = request.app.get("_sse_lines", [])
    for line in lines:
        await resp.write((line + "\n").encode())
        await asyncio.sleep(0.005)
    close_event: asyncio.Event = request.app["_sse_close_event"]
    await close_event.wait()
    return resp


class _TestServerContext:
    """Holds both the runner and the app for easy access in tests."""
    def __init__(self, runner: aiohttp.web.AppRunner, app: aiohttp.web.Application) -> None:
        self.runner = runner
        self.app = app

    @property
    def addresses(self) -> list[tuple[str, int]]:
        return self.runner.addresses

    def url(self, path: str = "") -> str:
        addr = self.addresses[0]
        return f"http://{addr[0]}:{addr[1]}{path}"

    def ws_url(self, path: str = "/ws") -> str:
        addr = self.addresses[0]
        return f"ws://{addr[0]}:{addr[1]}{path}"


@pytest.fixture
async def test_server() -> AsyncGenerator[_TestServerContext, None]:
    app = aiohttp.web.Application()
    app.router.add_get("/ws", _ws_handler)
    app.router.add_get("/sse", _sse_handler)
    app["_ws_messages"] = []
    app["_sse_lines"] = []
    app["_ws_close_event"] = asyncio.Event()
    app["_sse_close_event"] = asyncio.Event()

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    yield _TestServerContext(runner, app)

    app["_ws_close_event"].set()
    app["_sse_close_event"].set()
    await asyncio.sleep(0.05)
    await runner.cleanup()


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
    async def test_ws_receives_message(self, test_server: _TestServerContext) -> None:
        test_server.app["_ws_messages"] = ['{"event": "ping"}']

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(url=test_server.ws_url(), protocol=StreamProtocol.WS)

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
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
    async def test_ws_json_path_filter(self, test_server: _TestServerContext) -> None:
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
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("ws-filter", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1

    @pytest.mark.asyncio
    async def test_ws_regex_filter_no_match(self, test_server: _TestServerContext) -> None:
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
            return_value=_SSRF_OK,
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
    async def test_sse_single_data_line(self, test_server: _TestServerContext) -> None:
        test_server.app["_sse_lines"] = ["data: hello-sse", ""]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("sse-single", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == "hello-sse"

    @pytest.mark.asyncio
    async def test_sse_multiline_data(self, test_server: _TestServerContext) -> None:
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
            return_value=_SSRF_OK,
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
    async def test_sse_ignores_comments(self, test_server: _TestServerContext) -> None:
        test_server.app["_sse_lines"] = [": this is a comment", "data: real-data", ""]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("sse-comment", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == "real-data"


# ---------------------------------------------------------------------------
# Tests: Lifecycle & limits
# ---------------------------------------------------------------------------


class TestStreamLifecycle:
    @pytest.mark.asyncio
    async def test_max_concurrent_streams(self, test_server: _TestServerContext) -> None:
        mgr = StreamListenerManager(max_concurrent_streams=2)
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("s1", StreamTrigger(url=test_server.ws_url()), on_event)
            await mgr.start_stream("s2", StreamTrigger(url=test_server.ws_url()), on_event)

            with pytest.raises(ValueError, match="Max concurrent streams"):
                await mgr.start_stream("s3", StreamTrigger(url=test_server.ws_url()), on_event)

        test_server.app["_ws_close_event"].set()
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_stop_clears_task(self, test_server: _TestServerContext) -> None:
        mgr = StreamListenerManager()
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("stop-test", StreamTrigger(url=test_server.ws_url()), on_event)
            assert "stop-test" in mgr.active_streams()

            await mgr.stop_stream("stop-test")
            assert "stop-test" not in mgr.active_streams()

        test_server.app["_ws_close_event"].set()
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_restart_existing_stream(self, test_server: _TestServerContext) -> None:
        mgr = StreamListenerManager()
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("restart", StreamTrigger(url=test_server.ws_url()), on_event)
            await mgr.start_stream("restart", StreamTrigger(url=test_server.ws_url()), on_event)
            assert len(mgr.active_streams()) == 1

        test_server.app["_ws_close_event"].set()
        await mgr.stop_all()


# ---------------------------------------------------------------------------
# Tests: Edge cases and error handling
# ---------------------------------------------------------------------------


class TestStreamEdgeCases:
    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash_stream(self, test_server: _TestServerContext) -> None:
        """on_event raising should be caught and logged, not crash the loop."""
        test_server.app["_ws_messages"] = ['{"a": 1}', '{"a": 2}']
        call_count = {"n": 0}

        async def flaky_callback(job_id: str, url: str, data: str) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("callback boom")

        mgr = StreamListenerManager()
        trigger = StreamTrigger(url=test_server.ws_url(), protocol=StreamProtocol.WS)

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("cb-err", trigger, flaky_callback)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert call_count["n"] >= 2

    @pytest.mark.asyncio
    async def test_sse_empty_data_line(self, test_server: _TestServerContext) -> None:
        """data: with no value should still be collected (empty string)."""
        test_server.app["_sse_lines"] = ["data:", ""]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("sse-empty", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == ""

    @pytest.mark.asyncio
    async def test_sse_event_and_id_fields_ignored(self, test_server: _TestServerContext) -> None:
        """event: and id: lines should not appear in data output."""
        test_server.app["_sse_lines"] = [
            "event: custom-event",
            "id: 42",
            "data: payload",
            "",
        ]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.url("/sse"),
            protocol=StreamProtocol.SSE,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("sse-fields", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == "payload"

    @pytest.mark.asyncio
    async def test_ws_json_path_and_regex_combined(self, test_server: _TestServerContext) -> None:
        """Both json_path AND regex must match for event to fire."""
        test_server.app["_ws_messages"] = [
            '{"status": "ok"}',
            '{"status": "error"}',
        ]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.ws_url(),
            protocol=StreamProtocol.WS,
            filter_json_path="$.status",
            filter_regex="^ok$",
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("combo-filter", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count == 1

    @pytest.mark.asyncio
    async def test_oversized_regex_rejected(self) -> None:
        """Regex pattern exceeding 64KB should raise ValueError (ReDoS guard)."""
        mgr = StreamListenerManager()
        on_event = AsyncMock()
        huge_regex = "a" * 70_000
        trigger = StreamTrigger(
            url="ws://example.com/ws",
            protocol=StreamProtocol.WS,
            filter_regex=huge_regex,
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), pytest.raises(ValueError, match="too large"):
            await mgr.start_stream("redos", trigger, on_event)

        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_stop_nonexistent_stream_is_noop(self) -> None:
        """Stopping a stream that doesn't exist should not raise."""
        mgr = StreamListenerManager()
        await mgr.stop_stream("nonexistent")
        assert mgr.active_streams() == {}
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_ws_non_json_message_with_json_path_skipped(self, test_server: _TestServerContext) -> None:
        """Non-JSON message with json_path filter should be silently skipped."""
        test_server.app["_ws_messages"] = ["not-json-at-all"]

        mgr = StreamListenerManager()
        on_event = AsyncMock()
        trigger = StreamTrigger(
            url=test_server.ws_url(),
            protocol=StreamProtocol.WS,
            filter_json_path="$.key",
        )

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_stream("non-json", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count == 0
