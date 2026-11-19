"""Coverage-completion tests for LoopbackCdpRelayServer edge branches."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.server import LoopbackCdpRelayServer


@pytest.mark.asyncio
async def test_http_endpoint_none_before_start() -> None:
    server = LoopbackCdpRelayServer(ExtensionCdpRelayBridge())
    assert server.http_endpoint is None
    assert server.is_running is False


@pytest.mark.asyncio
async def test_start_returns_existing_endpoint_when_running() -> None:
    server = LoopbackCdpRelayServer(ExtensionCdpRelayBridge())
    server._port = 4321
    server._runner = MagicMock()
    assert server.start is not None
    endpoint = await server.start()
    assert endpoint == "http://127.0.0.1:4321"


@pytest.mark.asyncio
async def test_concurrent_first_starts_share_one_listener() -> None:
    """The extension connecting and tool calls asking for the endpoint reach a fresh server together."""
    from unittest.mock import patch

    from aiohttp import web

    from app.services.extension.cdp_relay import server as server_module

    runners: list[web.AppRunner] = []

    class SlowRunner(web.AppRunner):
        def __init__(self, app: web.Application) -> None:
            super().__init__(app)
            runners.append(self)

        async def setup(self) -> None:
            # Holds the first caller inside start() so the others arrive while the listener is still being built.
            await asyncio.sleep(0.05)
            await super().setup()

    server = LoopbackCdpRelayServer(ExtensionCdpRelayBridge())
    try:
        with patch.object(server_module.web, "AppRunner", SlowRunner):
            endpoints = await asyncio.gather(server.start(), server.start(), server.start())
        assert len(runners) == 1
        assert set(endpoints) == {server.http_endpoint}
    finally:
        # Without the guard every caller builds its own listener and all but the last are unreachable.
        leaked = [runner for runner in runners if runner is not server._runner]  # noqa: SLF001
        await server.stop()
        for runner in leaked:
            await runner.cleanup()


@pytest.mark.asyncio
async def test_start_fails_when_no_sockets() -> None:
    from unittest.mock import patch

    from app.services.extension.cdp_relay import server as server_module

    mock_site = MagicMock()
    mock_site.start = AsyncMock()
    mock_site._server = SimpleNamespace(sockets=[])
    with patch.object(server_module.web, "TCPSite", return_value=mock_site):
        server = LoopbackCdpRelayServer(ExtensionCdpRelayBridge())
        with pytest.raises(RuntimeError, match="Failed to bind"):
            await server.start()


@pytest.mark.asyncio
async def test_json_list_rejects_non_loopback() -> None:
    bridge = ExtensionCdpRelayBridge()
    bridge.set_identity(user_agent="UA", browser_version="Chrome/9.9")
    server = LoopbackCdpRelayServer(bridge)
    await server.start()
    try:
        app = server._runner.app  # noqa: SLF001 — test inspects bound app
        async with TestClient(TestServer(app)) as client:
            forbidden = await client.get("/json/list", headers={"Host": "evil.example"})
            assert forbidden.status == 403
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_cdp_websocket_roundtrip() -> None:
    bridge = ExtensionCdpRelayBridge()
    bridge.set_identity(user_agent="UA", browser_version="Chrome/9.9")
    server = LoopbackCdpRelayServer(bridge)
    await server.start()
    try:
        app = server._runner.app  # noqa: SLF001 — test inspects bound app
        async with TestClient(TestServer(app)) as client:
            async with client.ws_connect("/cdp") as ws:
                await ws.send_str(json.dumps({"id": 7, "method": "Browser.getVersion"}))
                msg = await ws.receive_json(timeout=5)
                assert msg["id"] == 7
                assert msg["result"]["product"] == "Chrome/9.9"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_cdp_websocket_rejects_non_loopback() -> None:
    from aiohttp.client_exceptions import WSServerHandshakeError

    bridge = ExtensionCdpRelayBridge()
    server = LoopbackCdpRelayServer(bridge)
    await server.start()
    try:
        app = server._runner.app  # noqa: SLF001 — test inspects bound app
        async with TestClient(TestServer(app)) as client:
            with pytest.raises(WSServerHandshakeError) as exc_info:
                await client.ws_connect("/cdp", headers={"Host": "evil.example"})
            assert exc_info.value.status == 403
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_devtools_endpoints_accept_a_trailing_slash() -> None:
    # Playwright's connect_over_cdp asks for /json/version/ with the slash.
    server = LoopbackCdpRelayServer(ExtensionCdpRelayBridge())
    await server.start()
    try:
        app = server._runner.app  # noqa: SLF001 — test inspects bound app
        async with TestClient(TestServer(app)) as client:
            for path in ("/json/version/", "/json/list/", "/json/"):
                response = await client.get(path)
                assert response.status == 200, path
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_requests_carrying_an_origin_are_refused() -> None:
    # A web page can open a WebSocket to 127.0.0.1; browsers always attach the page's Origin, automation clients never do.
    from aiohttp.client_exceptions import WSServerHandshakeError

    server = LoopbackCdpRelayServer(ExtensionCdpRelayBridge())
    await server.start()
    try:
        app = server._runner.app  # noqa: SLF001 — test inspects bound app
        async with TestClient(TestServer(app)) as client:
            for path in ("/json/version", "/json/list"):
                refused = await client.get(path, headers={"Origin": "https://evil.example"})
                assert refused.status == 403, path
            with pytest.raises(WSServerHandshakeError) as exc_info:
                await client.ws_connect("/cdp", headers={"Origin": "https://evil.example"})
            assert exc_info.value.status == 403
            async with client.ws_connect("/cdp") as ws:
                await ws.send_str(json.dumps({"id": 1, "method": "Browser.getVersion"}))
                assert (await ws.receive_json(timeout=5))["id"] == 1
    finally:
        await server.stop()
