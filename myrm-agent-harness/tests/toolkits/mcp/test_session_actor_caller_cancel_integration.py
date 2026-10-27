"""A caller that gives up on an MCP call must not leave the warm session busy or the request running.

Real MCP servers over real transports (stdio subprocess, streamable HTTP, SSE): the caller of a long ``slow`` call is
cancelled (what Stop, pause or the generic tool-gate cut does). The session has to forward the cancellation so the
server stops working, serve the next call at once, and stay healthy for the calls after that.
"""

from __future__ import annotations

import asyncio
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.mcp.config import MCPConfig
from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager
from myrm_agent_harness.toolkits.mcp.connection_pool_types import MCPConnection
from tests.support import mcp_cancel_probe_server
from tests.support.marked_processes import wait_until
from tests.support.mcp_cancel_probe_server import CANCELLED, STARTED, build_cancel_probe_server
from tests.support.mcp_live_server import HTTP_ENDPOINT_PATH, start_live_server

_SLOW_SECONDS = 60.0
# A call that waited out the slow one would take ~60s; serving the next call at once takes milliseconds.
_NEXT_CALL_BUDGET_S = 5.0


@pytest.fixture
def _reset_manager() -> object:
    MCPConnectionManager._instance = None
    yield
    MCPConnectionManager._instance = None


@asynccontextmanager
async def _probe_connection(transport: str, marks_dir: Path) -> AsyncIterator[MCPConnection]:
    """A pooled connection to the cancel-probe server over *transport*."""
    if transport == "stdio":
        cfg = MCPConfig(
            name="cancelprobe",
            type="stdio",
            command=sys.executable,
            args=[mcp_cancel_probe_server.__file__, str(marks_dir)],
            description="cancel probe",
            connect_timeout=30.0,
        )
        live = None
    else:
        server = build_cancel_probe_server(marks_dir)
        live = await start_live_server(server.sse_app() if transport == "sse" else server.streamable_http_app())
        cfg = MCPConfig(
            name="cancelprobe",
            type=transport,
            url=f"{live.base_url}{HTTP_ENDPOINT_PATH[transport]}",
            description="cancel probe",
            connect_timeout=30.0,
        )
    manager = await MCPConnectionManager.get_instance()
    try:
        yield await manager.get_connection([cfg])
    finally:
        await manager.stop()
        if live is not None:
            await live.stop()


async def _cancel_in_flight_slow_call(conn: MCPConnection, marks_dir: Path) -> None:
    slow_call = asyncio.create_task(conn.call("cancelprobe", "slow", {"seconds": _SLOW_SECONDS}))
    await wait_until(lambda: (marks_dir / STARTED).exists())
    slow_call.cancel()
    with suppress(asyncio.CancelledError):
        await slow_call


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "streamable_http", "sse"])
async def test_a_cancelled_caller_stops_the_server_side_call_and_frees_the_session(
    transport: str, tmp_path: Path, _reset_manager: object
) -> None:
    async with _probe_connection(transport, tmp_path) as conn:
        assert "fast-done" in str(await conn.call("cancelprobe", "fast", {}))

        await _cancel_in_flight_slow_call(conn, tmp_path)

        began = time.monotonic()
        assert "fast-done" in str(await asyncio.wait_for(conn.call("cancelprobe", "fast", {}), _NEXT_CALL_BUDGET_S))
        assert time.monotonic() - began < _NEXT_CALL_BUDGET_S
        await wait_until(lambda: (tmp_path / CANCELLED).exists(), timeout=_NEXT_CALL_BUDGET_S)

        # The session survived the cancellation and keeps serving.
        assert "fast-done" in str(await conn.call("cancelprobe", "fast", {}))


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["stdio", "streamable_http", "sse"])
async def test_a_call_that_is_not_cancelled_still_completes_after_an_earlier_one_was(
    transport: str, tmp_path: Path, _reset_manager: object
) -> None:
    async with _probe_connection(transport, tmp_path) as conn:
        await _cancel_in_flight_slow_call(conn, tmp_path)
        (tmp_path / STARTED).unlink()

        result = await asyncio.wait_for(conn.call("cancelprobe", "slow", {"seconds": 0.2}), _NEXT_CALL_BUDGET_S)

        assert "slow-done" in str(result)
