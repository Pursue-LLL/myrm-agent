"""The relay tells its CDP clients that targets are gone when the extension link is lost."""

from __future__ import annotations

import pytest

from app.services.extension.cdp_relay.bridge import ExtensionCdpRelayBridge
from app.services.extension.cdp_relay.extension_link import CallExtension
from app.services.extension.cdp_relay.protocol import RelayTabInfo


async def _call_extension(command: dict[str, object]) -> object:
    if command.get("type") == "attach":
        return {"targetId": f"target-{command.get('tabId')}"}
    return {}


async def _bridge_with_an_announced_tab(call_extension: CallExtension) -> tuple[ExtensionCdpRelayBridge, list[str]]:
    bridge = ExtensionCdpRelayBridge()
    sent: list[str] = []
    bridge.attach_cdp_client(sent.append)
    bridge.set_extension_transport(call_extension)
    bridge.sync_tabs([RelayTabInfo(tab_id=7, url="https://x.com", title="X", active=True)])
    attached = await bridge._ensure_tab_attached(7)
    bridge._announce_attached(bridge._clients[-1], 7, attached)
    return bridge, sent


@pytest.mark.asyncio
async def test_losing_the_extension_detaches_every_announced_target() -> None:
    bridge, sent = await _bridge_with_an_announced_tab(_call_extension)

    bridge.set_extension_transport(None)

    assert 7 not in bridge._tabs
    assert any("Target.detachedFromTarget" in raw for raw in sent)


@pytest.mark.asyncio
async def test_binding_the_same_transport_again_keeps_the_announced_targets() -> None:
    bridge, sent = await _bridge_with_an_announced_tab(_call_extension)
    announced = len(sent)

    bridge.set_extension_transport(_call_extension)

    assert bridge._tabs[7].attached is not None
    assert len(sent) == announced
