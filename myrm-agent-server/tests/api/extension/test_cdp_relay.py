"""Unit tests for extension CDP relay bridge and pairing."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge, build_extension_call_extension
from app.services.extension.cdp_relay.protocol import RelayTabInfo
from app.services.extension.pairing import consume_pairing_ticket, create_pairing_ticket


@pytest.mark.asyncio
async def test_relay_browser_get_version() -> None:
    bridge = ExtensionCdpRelayBridge()
    bridge.set_identity(user_agent="UA", browser_version="Chrome/1.2.3")
    sent: list[str] = []

    on_message, on_close = bridge.attach_cdp_client(lambda raw: sent.append(raw))
    on_message(json.dumps({"id": 1, "method": "Browser.getVersion"}))
    await asyncio.sleep(0.01)
    on_close()

    assert sent
    payload = json.loads(sent[0])
    assert payload["id"] == 1
    assert payload["result"]["product"] == "Chrome/1.2.3"


@pytest.mark.asyncio
async def test_relay_extension_call_and_result() -> None:
    bridge = ExtensionCdpRelayBridge()
    outbound: list[dict[str, object]] = []

    async def send(msg: dict[str, object]) -> None:
        outbound.append(msg)

    call_extension = build_extension_call_extension(bridge, send)
    bridge.set_extension_transport(call_extension)
    bridge.sync_tabs([RelayTabInfo(tab_id=7, url="https://x.com", title="X", active=True)])

    task = asyncio.create_task(call_extension({"type": "attach", "tabId": 7}))

    while not outbound:
        await asyncio.sleep(0.01)

    seq = outbound[0]["seq"]
    assert isinstance(seq, int)
    await bridge.handle_extension_result(seq, {"targetId": "tab-7"})
    result = await task
    assert result == {"targetId": "tab-7"}


@pytest.mark.asyncio
async def test_relay_automation_probe_ready() -> None:
    bridge = ExtensionCdpRelayBridge()
    bridge.set_identity(user_agent="UA", browser_version="Chrome/1.2.3")
    assert await bridge.probe_automation_ready() is False

    async def send(_msg: dict[str, object]) -> None:
        return None

    bridge.set_extension_transport(build_extension_call_extension(bridge, send))
    assert await bridge.probe_automation_ready() is True


@pytest.mark.asyncio
async def test_relay_target_create_target() -> None:
    bridge = ExtensionCdpRelayBridge()
    outbound: list[dict[str, object]] = []

    async def send(msg: dict[str, object]) -> None:
        outbound.append(msg)
        seq = msg.get("seq")
        command = msg.get("command")
        if isinstance(seq, int) and isinstance(command, dict):
            if command.get("type") == "createTab":
                await bridge.handle_extension_result(seq, {"tabId": 99})
            elif command.get("type") == "attach":
                await bridge.handle_extension_result(seq, {"targetId": "tab-99"})

    call_extension = build_extension_call_extension(bridge, send)
    bridge.set_extension_transport(call_extension)

    sent: list[str] = []
    _on_message, on_close = bridge.attach_cdp_client(lambda raw: sent.append(raw))
    await bridge._handle_cdp_client_message(
        bridge._clients[-1],
        json.dumps(
            {
                "id": 42,
                "method": "Target.createTarget",
                "params": {"url": "https://x.com/home"},
            }
        ),
    )

    payloads = [json.loads(raw) for raw in sent if '"id": 42' in raw or '"id":42' in raw.replace(" ", "")]
    assert payloads
    assert payloads[0]["result"]["targetId"] == "tab-99"
    on_close()


@pytest.mark.asyncio
async def test_cdp_relay_manager_lifecycle_and_probe_cache() -> None:
    from app.services.extension.cdp_relay.manager import CdpRelayManager

    manager = CdpRelayManager()
    assert await manager.relay_cdp_ready() is False

    outbound: list[dict[str, object]] = []

    async def send(msg: dict[str, object]) -> None:
        outbound.append(msg)

    await manager.bind_extension_transport(send)
    manager.set_identity(user_agent="MyrmTest", browser_version="Chrome/99.0")
    assert manager.http_endpoint is not None

    first = await manager.relay_cdp_ready()
    second = await manager.relay_cdp_ready()
    assert first is True
    assert second is True

    endpoint = await manager.ensure_http_endpoint()
    assert endpoint.startswith("http://127.0.0.1:")

    await manager.shutdown()
    assert manager.http_endpoint is None
    assert await manager.relay_cdp_ready() is False


@pytest.mark.asyncio
async def test_cdp_relay_manager_dispatch_extension_messages() -> None:
    from app.services.extension.cdp_relay.manager import CdpRelayManager

    manager = CdpRelayManager()
    bridge = manager.bridge
    outbound: list[dict[str, object]] = []

    async def send(msg: dict[str, object]) -> None:
        outbound.append(msg)

    await manager.bind_extension_transport(send)
    call_extension = build_extension_call_extension(bridge, send)
    task = asyncio.create_task(call_extension({"type": "attach", "tabId": 3}))
    while not outbound:
        await asyncio.sleep(0.01)
    seq = outbound[0]["seq"]
    assert isinstance(seq, int)

    await manager.dispatch_extension_message({"type": "relay_result", "seq": seq, "result": {"ok": True}})
    assert await task == {"ok": True}

    err_task = asyncio.create_task(call_extension({"type": "detach", "tabId": 3}))
    while len(outbound) < 2:
        await asyncio.sleep(0.01)
    err_seq = outbound[1]["seq"]
    await manager.dispatch_extension_message(
        {"type": "relay_error", "seq": err_seq, "message": "boom"},
    )
    with pytest.raises(RuntimeError, match="boom"):
        await err_task

    manager.sync_tabs_from_extension(
        [RelayTabInfo(tab_id=3, url="https://x.com", title="X", active=True)],
    )
    bridge.handle_cdp_event(3, "Page.loadEventFired", {"timestamp": 1.0})
    await manager.dispatch_extension_message(
        {
            "type": "cdp_event",
            "tabId": 3,
            "method": "Page.frameNavigated",
            "params": {"frame": {"id": "1"}},
        },
    )
    await manager.dispatch_extension_message({"type": "debugger_detached", "tabId": 3})

    await manager.bind_extension_transport(None)
    await manager.shutdown()


@pytest.mark.asyncio
async def test_loopback_server_json_endpoints_localhost_only() -> None:
    from aiohttp.test_utils import TestClient, TestServer

    from app.services.extension.cdp_relay.server import LoopbackCdpRelayServer

    bridge = ExtensionCdpRelayBridge()
    bridge.set_identity(user_agent="UA", browser_version="Chrome/9.9")
    server = LoopbackCdpRelayServer(bridge)
    endpoint = await server.start()
    assert endpoint.startswith("http://127.0.0.1:")

    app = server._runner.app  # noqa: SLF001 — test inspects bound routes
    async with TestClient(TestServer(app)) as client:
        version_resp = await client.get("/json/version")
        assert version_resp.status == 200
        version_payload = await version_resp.json()
        assert version_payload["Browser"] == "Chrome/9.9"

        list_resp = await client.get("/json/list")
        assert list_resp.status == 200
        listed = await list_resp.json()
        assert listed[0]["type"] == "page"

        forbidden = await client.get("/json/version", headers={"Host": "evil.example"})
        assert forbidden.status == 403

    await server.stop()


def test_pairing_rate_limit_blocks_burst() -> None:
    from app.services.extension.pairing import check_pairing_rate_limit

    client = "test-client-rate-limit"
    for _ in range(20):
        assert check_pairing_rate_limit(client) is True
    assert check_pairing_rate_limit(client) is False


def test_pairing_ticket_single_use() -> None:
    code, _ = create_pairing_ticket(ws_url="ws://127.0.0.1/ws", auth_token="secret")
    ticket = consume_pairing_ticket(code)
    assert ticket is not None
    assert ticket.ws_url.endswith("/ws")
    assert consume_pairing_ticket(code) is None
