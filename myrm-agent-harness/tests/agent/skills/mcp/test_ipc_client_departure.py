"""A request in flight on the MCP IPC server ends with its client.

The generated client holds one request per connection and sends nothing while it waits. When its script is killed (a stop,
a host timeout) or gives the call up, the connection closes; the server must then cancel the call down to the MCP server
instead of leaving it to occupy the server until the tool's own limit.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.mcp.ipc_proxy import MCPIPCServer

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix socket transport")

_ANSWER = '{"success": true, "result": "done", "error": null}'


def _frame(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload).encode()
    return len(body).to_bytes(4, "big") + body


async def _read_response(reader: asyncio.StreamReader) -> dict[str, object]:
    length = int.from_bytes(await reader.readexactly(4), "big")
    response: dict[str, object] = json.loads(await reader.readexactly(length))
    return response


@asynccontextmanager
async def _server() -> AsyncIterator[MCPIPCServer]:
    # AF_UNIX paths are short-limited; pytest's tmp_path is not.
    socket_dir = Path(tempfile.mkdtemp(prefix="ipc"))
    server = MCPIPCServer(str(socket_dir / "s.sock"))
    await server.start()
    try:
        yield server
    finally:
        await server.stop()
        shutil.rmtree(socket_dir, ignore_errors=True)


class _Probe:
    """Replaces request processing with a call that reports when it starts and when it is cancelled."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def process(self, message: str) -> str:
        self.started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return _ANSWER


async def _send_request_and_wait_until_running(server: MCPIPCServer, probe: _Probe) -> asyncio.StreamWriter:
    _, writer = await asyncio.open_unix_connection(server.socket_path)
    writer.write(_frame({"skill_name": "s", "tool_name": "t", "params": {}}))
    await writer.drain()
    await asyncio.wait_for(probe.started.wait(), 5)
    return writer


@pytest.mark.asyncio
async def test_a_request_is_cancelled_when_its_client_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _server() as server:
        probe = _Probe()
        monkeypatch.setattr(server, "_process_request", probe.process)
        writer = await _send_request_and_wait_until_running(server, probe)

        writer.close()
        await writer.wait_closed()

        await asyncio.wait_for(probe.cancelled.wait(), 5)


@pytest.mark.asyncio
async def test_stray_bytes_while_a_request_is_in_flight_cancel_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The client never pipelines; bytes arriving mid-request are a protocol violation, not a second request."""
    async with _server() as server:
        probe = _Probe()
        monkeypatch.setattr(server, "_process_request", probe.process)
        writer = await _send_request_and_wait_until_running(server, probe)

        writer.write(b"\x00")
        await writer.drain()

        await asyncio.wait_for(probe.cancelled.wait(), 5)
        writer.close()


@pytest.mark.asyncio
async def test_a_client_that_waits_is_answered_and_may_send_the_next_request(monkeypatch: pytest.MonkeyPatch) -> None:
    async with _server() as server:
        calls: list[str] = []

        async def answer_after_a_moment(message: str) -> str:
            calls.append(message)
            await asyncio.sleep(0.3)
            return _ANSWER

        monkeypatch.setattr(server, "_process_request", answer_after_a_moment)
        reader, writer = await asyncio.open_unix_connection(server.socket_path)

        for _ in range(2):
            writer.write(_frame({"skill_name": "s", "tool_name": "t", "params": {}}))
            await writer.drain()
            assert (await asyncio.wait_for(_read_response(reader), 5))["result"] == "done"

        assert len(calls) == 2
        writer.close()
        await writer.wait_closed()
