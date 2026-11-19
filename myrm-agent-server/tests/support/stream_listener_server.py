"""In-process aiohttp server with a WebSocket and an SSE endpoint, for the stream listener tests.

The listener connects over real loopback sockets; only its SSRF guard is replaced by ``SSRF_OK`` so that a
127.0.0.1 target is reachable.
"""

from __future__ import annotations

import asyncio

import aiohttp
import aiohttp.web
from myrm_agent_harness.core.security.guards.ssrf import SSRFResult

SSRF_OK = SSRFResult(safe=True, hostname="localhost", resolved_ips=("127.0.0.1",))


def stream_tasks() -> list[str]:
    """Names of the live stream tasks; the manager names each one ``stream-<protocol>-<job id>``."""
    return sorted(task.get_name() for task in asyncio.all_tasks() if task.get_name().startswith("stream-"))


async def ws_handler(request: aiohttp.web.Request) -> aiohttp.web.WebSocketResponse:
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


async def sse_handler(request: aiohttp.web.Request) -> aiohttp.web.StreamResponse:
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


class ServerContext:
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
