"""Integration tests for StreamListenerManager: lifecycle, limits and edge cases.

Uses real aiohttp.web test server for WS/SSE — no mock on network I/O;
SSRF guard is bypassed only for localhost test server connectivity.

Covers:
- Concurrent stream limit enforcement
- start/stop/restart lifecycle
- Callback failures, empty and ignored SSE fields, combined filters, oversized regex, non-JSON messages
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.triggers import StreamProtocol, StreamTrigger

from app.core.cron.adapters.stream_listener import StreamListenerManager
from tests.support.stream_listener_server import SSRF_OK, ServerContext, stream_tasks

# ---------------------------------------------------------------------------
# Tests: Lifecycle & limits
# ---------------------------------------------------------------------------


class TestStreamLifecycle:
    @pytest.mark.asyncio
    async def test_max_concurrent_streams(self, test_server: ServerContext) -> None:
        mgr = StreamListenerManager(max_concurrent_streams=2)
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("s1", StreamTrigger(url=test_server.ws_url()), on_event)
            await mgr.start_stream("s2", StreamTrigger(url=test_server.ws_url()), on_event)

            with pytest.raises(ValueError, match="Max concurrent streams"):
                await mgr.start_stream("s3", StreamTrigger(url=test_server.ws_url()), on_event)

        test_server.app["_ws_close_event"].set()
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_stop_clears_task(self, test_server: ServerContext) -> None:
        mgr = StreamListenerManager()
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("stop-test", StreamTrigger(url=test_server.ws_url()), on_event)
            assert stream_tasks() == ["stream-ws-stop-test"]

            await mgr.stop_stream("stop-test")
            assert stream_tasks() == []

        test_server.app["_ws_close_event"].set()
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_restart_existing_stream(self, test_server: ServerContext) -> None:
        mgr = StreamListenerManager()
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("restart", StreamTrigger(url=test_server.ws_url()), on_event)
            await mgr.start_stream("restart", StreamTrigger(url=test_server.ws_url()), on_event)
            assert stream_tasks() == ["stream-ws-restart"]

        test_server.app["_ws_close_event"].set()
        await mgr.stop_all()


# ---------------------------------------------------------------------------
# Tests: Edge cases and error handling
# ---------------------------------------------------------------------------


class TestStreamEdgeCases:
    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash_stream(self, test_server: ServerContext) -> None:
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
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("cb-err", trigger, flaky_callback)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert call_count["n"] >= 2

    @pytest.mark.asyncio
    async def test_sse_empty_data_line(self, test_server: ServerContext) -> None:
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
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("sse-empty", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == ""

    @pytest.mark.asyncio
    async def test_sse_event_and_id_fields_ignored(self, test_server: ServerContext) -> None:
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
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("sse-fields", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_sse_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        assert on_event.call_args_list[0][0][2] == "payload"

    @pytest.mark.asyncio
    async def test_ws_json_path_and_regex_combined(self, test_server: ServerContext) -> None:
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
            return_value=SSRF_OK,
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

        with (
            patch(
                "app.core.cron.adapters.stream_listener.async_validate_url_for_ssrf",
                return_value=SSRF_OK,
            ),
            pytest.raises(ValueError, match="too large"),
        ):
            await mgr.start_stream("redos", trigger, on_event)

        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_stop_nonexistent_stream_is_noop(self) -> None:
        """Stopping a stream that doesn't exist should not raise."""
        mgr = StreamListenerManager()
        await mgr.stop_stream("nonexistent")
        assert stream_tasks() == []
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_ws_non_json_message_with_json_path_skipped(self, test_server: ServerContext) -> None:
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
            return_value=SSRF_OK,
        ):
            await mgr.start_stream("non-json", trigger, on_event)

        await asyncio.sleep(0.3)
        test_server.app["_ws_close_event"].set()
        await asyncio.sleep(0.1)

        await mgr.stop_all()
        assert on_event.call_count == 0
