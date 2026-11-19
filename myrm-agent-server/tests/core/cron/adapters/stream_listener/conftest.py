"""The ``test_server`` fixture: a loopback aiohttp server the stream listener tests connect to."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import aiohttp.web
import pytest

from tests.support.stream_listener_server import ServerContext, sse_handler, ws_handler


@pytest.fixture
async def test_server() -> AsyncGenerator[ServerContext, None]:
    app = aiohttp.web.Application()
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/sse", sse_handler)
    app["_ws_messages"] = []
    app["_sse_lines"] = []
    app["_ws_close_event"] = asyncio.Event()
    app["_sse_close_event"] = asyncio.Event()

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    site = aiohttp.web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    yield ServerContext(runner, app)

    app["_ws_close_event"].set()
    app["_sse_close_event"].set()
    await asyncio.sleep(0.05)
    await runner.cleanup()
