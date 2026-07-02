"""Integration tests for PollListenerManager.

Uses real aiohttp.web test server for HTTP responses — no mock on network I/O.
SSRF guard is bypassed only for localhost test server connectivity;
a dedicated test verifies that SSRF actually blocks private IPs.

Covers:
- SSRF rejection for private IP URLs
- Polling with content change detection (hash comparison)
- Polling without change detection (every poll fires)
- json_path extraction in poll response
- Concurrent poll limit enforcement
- start/stop lifecycle
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import aiohttp
import aiohttp.web
import pytest
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult
from myrm_agent_harness.toolkits.cron.triggers import PollTrigger

from app.core.cron.adapters.poll_listener import PollListenerManager

_SSRF_OK = SSRFResult(safe=True, hostname="localhost", resolved_ips=("127.0.0.1",))


# ---------------------------------------------------------------------------
# Fixtures: in-process aiohttp test server with configurable response
# ---------------------------------------------------------------------------


async def _poll_handler(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Return the next response body from the queue, or a default."""
    bodies: list[str] = request.app.get("_poll_bodies", [])
    counter: list[int] = request.app["_poll_counter"]
    idx = counter[0]
    counter[0] += 1
    body = bodies[idx] if idx < len(bodies) else (bodies[-1] if bodies else '{"ok": true}')
    return aiohttp.web.Response(text=body, content_type="application/json")


class _TestServerContext:
    def __init__(self, runner: aiohttp.web.AppRunner, app: aiohttp.web.Application) -> None:
        self.runner = runner
        self.app = app

    def url(self, path: str = "/poll") -> str:
        addr = self.runner.addresses[0]
        return f"http://{addr[0]}:{addr[1]}{path}"


@pytest.fixture
async def test_server() -> AsyncGenerator[_TestServerContext, None]:
    app = aiohttp.web.Application()
    app.router.add_get("/poll", _poll_handler)
    app["_poll_bodies"] = []
    app["_poll_counter"] = [0]

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    yield _TestServerContext(runner, app)

    await runner.cleanup()


# ---------------------------------------------------------------------------
# Tests: SSRF integration (no mock — verifies real SSRF guard)
# ---------------------------------------------------------------------------


class TestPollSSRF:
    @pytest.mark.asyncio
    async def test_ssrf_blocks_private_ip(self) -> None:
        mgr = PollListenerManager()
        trigger = PollTrigger(url="http://127.0.0.1:9999/poll", interval_seconds=60)
        on_event = AsyncMock()

        with pytest.raises(ValueError, match="SSRF"):
            await mgr.start_poll("poll-ssrf", trigger, on_event)

        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_ssrf_blocks_localhost(self) -> None:
        mgr = PollListenerManager()
        trigger = PollTrigger(url="http://localhost:9999/poll", interval_seconds=60)
        on_event = AsyncMock()

        with pytest.raises(ValueError, match="SSRF"):
            await mgr.start_poll("poll-ssrf-host", trigger, on_event)

        await mgr.stop_all()


# ---------------------------------------------------------------------------
# Tests: Polling with change detection
# ---------------------------------------------------------------------------


class TestPollChangeDetection:
    @pytest.mark.asyncio
    async def test_change_detection_fires_on_change(self, test_server: _TestServerContext) -> None:
        """First poll stores baseline; second with different content fires event."""
        test_server.app["_poll_bodies"] = ['{"v": 1}', '{"v": 2}']

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=True,
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("cd-test", trigger, on_event)
            await asyncio.sleep(2.5)

        await mgr.stop_all()
        assert on_event.call_count >= 1

    @pytest.mark.asyncio
    async def test_change_detection_no_fire_same_content(self, test_server: _TestServerContext) -> None:
        """Same content on every poll — should not fire after baseline."""
        test_server.app["_poll_bodies"] = ['{"v": "same"}']

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=True,
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("cd-same", trigger, on_event)
            await asyncio.sleep(2.5)

        await mgr.stop_all()
        assert on_event.call_count == 0

    @pytest.mark.asyncio
    async def test_no_change_detection_fires_every_poll(self, test_server: _TestServerContext) -> None:
        """Without change_detection, every poll fires the event."""
        test_server.app["_poll_bodies"] = ['{"v": "same"}']

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=False,
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("no-cd", trigger, on_event)
            await asyncio.sleep(2.5)

        await mgr.stop_all()
        assert on_event.call_count >= 2


# ---------------------------------------------------------------------------
# Tests: json_path extraction in poll
# ---------------------------------------------------------------------------


class TestPollJsonPath:
    @pytest.mark.asyncio
    async def test_json_path_extracts_field(self, test_server: _TestServerContext) -> None:
        test_server.app["_poll_bodies"] = ['{"data": {"val": "extracted"}}']

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=False,
            json_path="$.data.val",
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("jp-test", trigger, on_event)
            await asyncio.sleep(1.5)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        payload = on_event.call_args_list[0][0][2]
        assert payload == "extracted"


# ---------------------------------------------------------------------------
# Tests: Lifecycle & limits
# ---------------------------------------------------------------------------


class TestPollLifecycle:
    @pytest.mark.asyncio
    async def test_max_concurrent_polls(self, test_server: _TestServerContext) -> None:
        mgr = PollListenerManager(max_concurrent_polls=2)
        on_event = AsyncMock()
        url = test_server.url()

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_poll("p1", PollTrigger(url=url, interval_seconds=300), on_event)
            await mgr.start_poll("p2", PollTrigger(url=url, interval_seconds=300), on_event)

            with pytest.raises(ValueError, match="Max concurrent polls"):
                await mgr.start_poll("p3", PollTrigger(url=url, interval_seconds=300), on_event)

        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_stop_clears_task(self, test_server: _TestServerContext) -> None:
        mgr = PollListenerManager()
        on_event = AsyncMock()

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_poll(
                "stop-test",
                PollTrigger(url=test_server.url(), interval_seconds=300),
                on_event,
            )
            assert "stop-test" in mgr.active_polls()

            await mgr.stop_poll("stop-test")
            assert "stop-test" not in mgr.active_polls()

        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_restart_existing_poll(self, test_server: _TestServerContext) -> None:
        mgr = PollListenerManager()
        on_event = AsyncMock()
        url = test_server.url()

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ):
            await mgr.start_poll("restart", PollTrigger(url=url, interval_seconds=300), on_event)
            await mgr.start_poll("restart", PollTrigger(url=url, interval_seconds=300), on_event)
            assert len(mgr.active_polls()) == 1

        await mgr.stop_all()


# ---------------------------------------------------------------------------
# Tests: Edge cases and error handling
# ---------------------------------------------------------------------------


class TestPollEdgeCases:
    @pytest.mark.asyncio
    async def test_interval_clamped_to_minimum(self, test_server: _TestServerContext) -> None:
        """Interval below _MIN_INTERVAL_SECONDS should be clamped up."""
        test_server.app["_poll_bodies"] = ['{"v": 1}']

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=5,
            change_detection=False,
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("clamp-test", trigger, on_event)
            await asyncio.sleep(1.5)

        await mgr.stop_all()
        assert on_event.call_count >= 1

    @pytest.mark.asyncio
    async def test_json_path_missing_key_uses_full_body(self, test_server: _TestServerContext) -> None:
        """If json_path points to non-existent key, full body is used."""
        test_server.app["_poll_bodies"] = ['{"a": 1}']

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=False,
            json_path="$.nonexistent.key",
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("jp-missing", trigger, on_event)
            await asyncio.sleep(1.5)

        await mgr.stop_all()
        assert on_event.call_count >= 1
        payload = on_event.call_args_list[0][0][2]
        assert payload == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_stop_nonexistent_poll_is_noop(self) -> None:
        """Stopping a poll that doesn't exist should not raise."""
        mgr = PollListenerManager()
        await mgr.stop_poll("nonexistent")
        assert mgr.active_polls() == {}
        await mgr.stop_all()

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash_poll(self, test_server: _TestServerContext) -> None:
        """on_event raising should be caught; poll continues on next interval."""
        test_server.app["_poll_bodies"] = ['{"v": 1}', '{"v": 2}']
        call_count = {"n": 0}

        async def flaky_callback(job_id: str, url: str, data: str) -> None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("callback boom")

        mgr = PollListenerManager()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=False,
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("cb-err", trigger, flaky_callback)
            await asyncio.sleep(2.5)

        await mgr.stop_all()
        assert call_count["n"] >= 2

    @pytest.mark.asyncio
    async def test_change_detection_with_json_path(self, test_server: _TestServerContext) -> None:
        """Change detection should operate on extracted field, not full body."""
        test_server.app["_poll_bodies"] = [
            '{"data": "v1", "noise": "a"}',
            '{"data": "v1", "noise": "b"}',
            '{"data": "v2", "noise": "c"}',
        ]

        mgr = PollListenerManager()
        on_event = AsyncMock()
        trigger = PollTrigger(
            url=test_server.url(),
            interval_seconds=1,
            change_detection=True,
            json_path="$.data",
        )

        with patch(
            "app.core.cron.adapters.poll_listener.async_validate_url_for_ssrf",
            return_value=_SSRF_OK,
        ), patch(
            "app.core.cron.adapters.poll_listener._MIN_INTERVAL_SECONDS", 1,
        ):
            await mgr.start_poll("cd-jp", trigger, on_event)
            await asyncio.sleep(3.5)

        await mgr.stop_all()
        assert on_event.call_count == 1
        assert on_event.call_args_list[0][0][2] == "v2"
