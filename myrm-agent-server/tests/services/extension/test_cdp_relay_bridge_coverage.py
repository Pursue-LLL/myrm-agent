"""Coverage-completion tests for ExtensionCdpRelayBridge CDP target synthesis.

These tests drive the Target.* semantics and transport-lifecycle branches of
app.services.extension.cdp_relay.bridge that the API tests do not reach.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import pytest

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.protocol import BROWSER_TARGET_ID, RelayTabInfo


def _mk_tab(tab_id: int = 7, url: str = "https://x.com") -> RelayTabInfo:
    return RelayTabInfo(tab_id=tab_id, url=url, title="X", active=True)


def _client(bridge: ExtensionCdpRelayBridge) -> list[str]:
    sent: list[str] = []
    _on_message, _on_close = bridge.attach_cdp_client(sent.append)
    return sent


def _attach_extension(
    bridge: ExtensionCdpRelayBridge, result: object | None = None
) -> None:
    async def fake_call(command: dict[str, object]) -> object:
        if command.get("type") == "attach":
            if result is not None:
                return result
            return {"targetId": f"tab-{command.get('tabId')}"}
        if command.get("type") == "detach":
            return {}
        if command.get("type") == "createTab":
            return {"tabId": 99}
        return {}

    bridge.set_extension_transport(fake_call)


@pytest.mark.asyncio
async def test_sync_tabs_removes_missing_and_emits_detached() -> None:
    bridge = ExtensionCdpRelayBridge()
    bridge.sync_tabs([_mk_tab(7)])
    assert 7 in bridge._tabs

    # Second sync with the same tab updates in place.
    bridge.sync_tabs([_mk_tab(7, url="https://x.com/new")])
    assert bridge._tabs[7].info.url == "https://x.com/new"

    # Removing a never-attached tab just drops it.
    bridge.sync_tabs([])
    assert 7 not in bridge._tabs


@pytest.mark.asyncio
async def test_sync_tabs_attached_tab_removal_emits_detached() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    attached = await bridge._ensure_tab_attached(7)
    assert attached.target_id == "tab-7"
    bridge._announce_attached(bridge._clients[-1], 7, attached)

    bridge.sync_tabs([])
    assert 7 not in bridge._tabs
    assert any("Target.detachedFromTarget" in raw for raw in sent)


@pytest.mark.asyncio
async def test_handle_cdp_event_session_scoped() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    attached = await bridge._ensure_tab_attached(7)
    bridge._announce_attached(bridge._clients[-1], 7, attached)

    # Event for the root session.
    bridge.handle_cdp_event(7, "Page.loadEventFired", {"ts": 1})
    # Event with an explicit child session id.
    bridge.handle_cdp_event(7, "Network.requestWillBeSent", {"x": 1}, session_id="child-1")
    # Event for an unknown tab is ignored.
    bridge.handle_cdp_event(99, "Page.loadEventFired", {"ts": 1})

    assert any("Page.loadEventFired" in raw for raw in sent)
    # The child session is registered for downstream routing.
    assert bridge._child_sessions.get("child-1") == 7


@pytest.mark.asyncio
async def test_handle_extension_detached_clears_attachment() -> None:
    bridge = ExtensionCdpRelayBridge()
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    await bridge._ensure_tab_attached(7)
    assert bridge._tabs[7].attached is not None

    bridge.handle_extension_detached(7)
    assert bridge._tabs[7].attached is None


@pytest.mark.asyncio
async def test_attach_cdp_client_on_close_detaches_all_when_idle() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    on_message, on_close = bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    attached = await bridge._ensure_tab_attached(7)
    assert bridge._tabs[7].attached is attached

    # A second client keeps the relay active after the first closes.
    sent2: list[str] = []
    bridge.attach_cdp_client(sent2.append)
    on_close()
    assert bridge._tabs[7].attached is attached
    assert on_message is not None  # noqa: S101 — sanity that transport still bound

    # With no clients left, detaching all when idle is a no-op guard already covered.
    bridge._clients.clear()
    bridge._detach_all_when_idle()
    assert bridge._tabs[7].attached is None
    await asyncio.sleep(0.01)  # let the scheduled detach task finish


@pytest.mark.asyncio
async def test_probe_automation_ready_timeout_returns_false() -> None:
    bridge = ExtensionCdpRelayBridge()

    async def fake_call(command: dict[str, object]) -> object:
        return {}

    bridge.set_extension_transport(fake_call)
    sent: list[str] = []
    on_message, on_close = bridge.attach_cdp_client(sent.append)
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        assert await bridge.probe_automation_ready() is False
    on_close()


@pytest.mark.asyncio
async def test_call_extension_cmd_without_transport_raises() -> None:
    bridge = ExtensionCdpRelayBridge()
    with pytest.raises(RuntimeError, match="not connected"):
        await bridge._call_extension_cmd({"type": "cdp", "tabId": 7})


@pytest.mark.asyncio
async def test_cdp_client_message_parse_errors() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    client = bridge._clients[0] if bridge._clients else None
    if client is None:
        _on_message, _on_close = bridge.attach_cdp_client(sent.append)
        client = bridge._clients[0]

    await bridge._handle_cdp_client_message(client, "not json")
    assert sent and json.loads(sent[-1])["error"]["message"] == "Parse error"

    await bridge._handle_cdp_client_message(client, json.dumps(["not", "a", "dict"]))
    assert json.loads(sent[-1])["error"]["message"] == "Invalid request"

    await bridge._handle_cdp_client_message(
        client, json.dumps({"id": "bad-id", "method": 123})
    )
    assert json.loads(sent[-1])["error"]["message"] == "Invalid request"

    await bridge._handle_cdp_client_message(client, json.dumps({"id": 1}))
    assert json.loads(sent[-1])["error"]["message"] == "Invalid request"


@pytest.mark.asyncio
async def test_session_scoped_unknown_session_errors() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    await bridge._handle_cdp_client_message(
        bridge._clients[-1],
        json.dumps({"id": 1, "method": "Page.navigate", "params": {}, "sessionId": "ghost"}),
    )
    assert json.loads(sent[-1])["error"]["code"] == -32001


@pytest.mark.asyncio
async def test_session_scoped_routes_to_tab() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    attached = await bridge._ensure_tab_attached(7)

    await bridge._handle_cdp_client_message(
        bridge._clients[-1],
        json.dumps(
            {
                "id": 5,
                "method": "Page.navigate",
                "params": {"url": "https://x.com/y"},
                "sessionId": attached.session_id,
            }
        ),
    )
    payload = json.loads(sent[-1])
    assert payload["id"] == 5
    assert payload["sessionId"] == attached.session_id


@pytest.mark.asyncio
async def test_browser_scoped_noop_methods() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    for method in (
        "Browser.close",
        "Browser.setDownloadBehavior",
        "Target.setDiscoverTargets",
    ):
        await bridge._handle_browser_scoped(
            bridge._clients[-1], 1, method, {}, None
        )
        assert json.loads(sent[-1])["id"] == 1


@pytest.mark.asyncio
async def test_target_get_target_info_branches() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    await bridge._ensure_tab_attached(7)

    # Browser target.
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.getTargetInfo", {"targetId": BROWSER_TARGET_ID}, None
    )
    assert json.loads(sent[-1])["result"]["targetInfo"]["type"] == "browser"

    # Unknown target -> error.
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 2, "Target.getTargetInfo", {"targetId": "tab-999"}, None
    )
    assert json.loads(sent[-1])["error"]["code"] == -32602

    # Attached tab target.
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 3, "Target.getTargetInfo", {"targetId": "tab-7"}, None
    )
    assert json.loads(sent[-1])["result"]["targetInfo"]["url"] == "https://x.com"

    # No targetId -> browser info.
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 4, "Target.getTargetInfo", {}, None
    )
    assert json.loads(sent[-1])["result"]["targetInfo"]["type"] == "browser"


@pytest.mark.asyncio
async def test_target_get_targets_only_attached() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7), _mk_tab(8, url="https://y.com")])
    await bridge._ensure_tab_attached(7)  # only 7 attached

    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.getTargets", {}, None
    )
    infos = json.loads(sent[-1])["result"]["targetInfos"]
    assert [i["targetId"] for i in infos] == ["tab-7"]


@pytest.mark.asyncio
async def test_target_attach_to_browser_target() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.attachToBrowserTarget", {}, None
    )
    session_id = json.loads(sent[-1])["result"]["sessionId"]
    assert session_id in bridge._browser_sessions


@pytest.mark.asyncio
async def test_target_set_auto_attach() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])

    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.setAutoAttach", {"autoAttach": True}, None
    )
    assert json.loads(sent[-1])["id"] == 1
    assert any("Target.attachedToTarget" in raw for raw in sent)

    # autoAttach=False skips announcement.
    before = len(sent)
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 2, "Target.setAutoAttach", {"autoAttach": False}, None
    )
    assert json.loads(sent[-1])["id"] == 2
    assert len(sent) == before + 1


@pytest.mark.asyncio
async def test_target_attach_to_target_auxiliary_session() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])

    # First create a browser session.
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.attachToBrowserTarget", {}, None
    )
    browser_session = json.loads(sent[-1])["result"]["sessionId"]

    await bridge._handle_browser_scoped(
        bridge._clients[-1],
        2,
        "Target.attachToTarget",
        {"targetId": "tab-7"},
        browser_session,
    )
    aux_session = json.loads(sent[-1])["result"]["sessionId"]
    assert aux_session in bridge._auxiliary_tab_sessions

    # Unknown target -> error.
    await bridge._handle_browser_scoped(
        bridge._clients[-1],
        3,
        "Target.attachToTarget",
        {"targetId": "tab-999"},
        browser_session,
    )
    assert json.loads(sent[-1])["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_target_attach_to_target_root_session() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])

    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.attachToTarget", {"targetId": "tab-7"}, None
    )
    assert json.loads(sent[-1])["result"]["sessionId"].startswith("myrm-tab-7-")


@pytest.mark.asyncio
async def test_target_detach_from_target() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])

    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Target.attachToBrowserTarget", {}, None
    )
    browser_session = json.loads(sent[-1])["result"]["sessionId"]
    assert browser_session in bridge._browser_sessions

    await bridge._handle_browser_scoped(
        bridge._clients[-1],
        2,
        "Target.detachFromTarget",
        {"sessionId": browser_session},
        None,
    )
    assert browser_session not in bridge._browser_sessions
    assert json.loads(sent[-1])["id"] == 2


@pytest.mark.asyncio
async def test_target_create_target_invalid_tab_id() -> None:
    bridge = ExtensionCdpRelayBridge()

    async def fake_call(command: dict[str, object]) -> object:
        return {"no": "tabId"}

    bridge.set_extension_transport(fake_call)
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    await bridge._handle_browser_scoped(
        bridge._clients[-1],
        1,
        "Target.createTarget",
        {"url": "https://x.com"},
        None,
    )
    assert json.loads(sent[-1])["error"]["code"] == -32000


@pytest.mark.asyncio
async def test_target_create_target_success() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    await bridge._handle_browser_scoped(
        bridge._clients[-1],
        1,
        "Target.createTarget",
        {"url": "https://x.com/new"},
        None,
    )
    payload = json.loads(sent[-1])
    assert payload["result"]["targetId"] == "tab-99"
    assert 99 in bridge._tabs


@pytest.mark.asyncio
async def test_unsupported_browser_method_errors() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    await bridge._handle_browser_scoped(
        bridge._clients[-1], 1, "Some.randomMethod", {}, None
    )
    assert json.loads(sent[-1])["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_ensure_tab_attached_missing_tab_raises() -> None:
    bridge = ExtensionCdpRelayBridge()
    with pytest.raises(RuntimeError, match="not available"):
        await bridge._ensure_tab_attached(99)


@pytest.mark.asyncio
async def test_ensure_tab_attached_dedupes_concurrent() -> None:
    bridge = ExtensionCdpRelayBridge()
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    first = await bridge._ensure_tab_attached(7)
    second = await bridge._ensure_tab_attached(7)
    assert first is second


@pytest.mark.asyncio
async def test_ensure_tab_attached_tab_replaced_during_attach() -> None:
    bridge = ExtensionCdpRelayBridge()
    detach_calls: list[dict[str, object]] = []

    async def fake_call(command: dict[str, object]) -> object:
        if command.get("type") == "attach":
            # Simulate the tab being replaced while attach is in flight.
            bridge._tabs[7] = type(bridge._tabs[7])(info=_mk_tab(7))
            return {"targetId": "tab-7"}
        if command.get("type") == "detach":
            detach_calls.append(command)
            return {}
        return {}

    bridge.set_extension_transport(fake_call)
    bridge.sync_tabs([_mk_tab(7)])
    with pytest.raises(RuntimeError, match="closed during attach"):
        await bridge._ensure_tab_attached(7)
    assert detach_calls and detach_calls[0]["type"] == "detach"


@pytest.mark.asyncio
async def test_announce_attached_skips_duplicates() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    _attach_extension(bridge)
    bridge.sync_tabs([_mk_tab(7)])
    attached = await bridge._ensure_tab_attached(7)

    bridge._announce_attached(bridge._clients[-1], 7, attached)
    count = len(sent)
    bridge._announce_attached(bridge._clients[-1], 7, attached)
    assert len(sent) == count

    # Announce for a missing tab is a no-op.
    bridge._announce_attached(bridge._clients[-1], 999, attached)
    assert len(sent) == count


@pytest.mark.asyncio
async def test_respond_helpers_include_session_id() -> None:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    client = bridge._clients[-1]
    bridge._respond_ok(client, 1, "sess-1", {"a": 1})
    assert json.loads(sent[-1]) == {"id": 1, "sessionId": "sess-1", "result": {"a": 1}}
    bridge._respond_error(client, 2, "sess-1", "boom", -32001)
    assert json.loads(sent[-1])["error"]["code"] == -32001
    assert json.loads(sent[-1])["sessionId"] == "sess-1"


@pytest.mark.asyncio
async def test_fail_pending_extension_commands() -> None:
    bridge = ExtensionCdpRelayBridge()
    loop = asyncio.get_running_loop()
    fut: asyncio.Future[object] = loop.create_future()
    done_fut: asyncio.Future[object] = loop.create_future()
    done_fut.set_result("done")
    bridge._pending_extension[1] = fut
    bridge._pending_extension[2] = done_fut

    bridge.set_extension_transport(None)  # triggers fail + clear
    assert bridge._pending_extension == {}
    with pytest.raises(RuntimeError, match="extension disconnected"):
        fut.result()
