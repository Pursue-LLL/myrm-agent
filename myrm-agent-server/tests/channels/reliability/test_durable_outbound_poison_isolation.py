"""Durable outbox recovery: a record that cannot be decoded is dropped, never blocks the others.

Recovery runs inside ``MessageBus.start()`` (hence gateway startup) and on every channel enable, so a single
undecodable record that raised there would keep the whole gateway from starting on every restart.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest
from myrm_agent_harness.infra.delivery.storage import QueuedDelivery, load_pending_deliveries, save_delivery

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.reliability.durable_outbound import DurableOutboundGate
from app.channels.types import ActionButton, ChannelCapabilities, OutboundMessage

_HANDOFF_BUTTON = ActionButton(label="Continue in browser", action_id="web:continue_chat", url="https://example.test/chat/abc")


class _RecordingPublisher:
    """The queue front-end recovered deliveries are re-published into."""

    def __init__(self) -> None:
        self.published: list[OutboundMessage] = []

    async def publish_outbound(self, msg: OutboundMessage, *, _skip_durable_persist: bool = False) -> None:
        self.published.append(msg)


class _RecordingChannel(BaseChannel):
    name = "feishu"
    capabilities = ChannelCapabilities()

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "platform_msg_1"


def _message(content: str, *, with_button: bool = False) -> OutboundMessage:
    return OutboundMessage(
        channel="feishu",
        recipient_id="user_1",
        content=content,
        user_id="u1",
        components=((_HANDOFF_BUTTON,),) if with_button else (),
    )


def _record(delivery_id: str, content: dict[str, object], phase: str = "pending") -> QueuedDelivery:
    return QueuedDelivery(id=delivery_id, channel="feishu", recipient="user_1", content=content, enqueued_at=1.0, phase=phase)


def _untagged_wire(msg: OutboundMessage) -> dict[str, object]:
    """Wire form whose nested components carry no ``__type__`` tag, so ``from_dict`` cannot rebuild the button."""
    wire = msg.to_dict()
    for row in wire["components"]:  # type: ignore[attr-defined]
        for component in row:
            component.pop("__type__", None)
    return wire


@pytest.mark.parametrize("phase", ["pending", "attempting"])
async def test_message_with_button_is_recovered_after_restart(tmp_path: Path, phase: str) -> None:
    gate = DurableOutboundGate(tmp_path)
    await save_delivery(_record("feishu_user_1_btn", _message("answer", with_button=True).to_dict(), phase), base_dir=tmp_path)
    publisher = _RecordingPublisher()

    assert await gate.recover_into_bus(publisher) == 1

    assert publisher.published[0].components == ((_HANDOFF_BUTTON,),)
    assert "answer" in publisher.published[0].content


async def test_undecodable_record_is_dropped_without_blocking_healthy_records(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    gate = DurableOutboundGate(tmp_path)
    await save_delivery(_record("feishu_user_1_poison", _untagged_wire(_message("poison", with_button=True))), base_dir=tmp_path)
    await save_delivery(_record("feishu_user_1_healthy", _message("healthy").to_dict()), base_dir=tmp_path)
    publisher = _RecordingPublisher()

    with caplog.at_level(logging.ERROR, logger="app.channels.reliability.durable_outbound"):
        recovered = await gate.recover_into_bus(publisher)

    assert recovered == 1
    assert [m.content for m in publisher.published] == ["healthy"]
    assert [d.id for d in await load_pending_deliveries(base_dir=tmp_path)] == ["feishu_user_1_healthy"]
    assert any("feishu_user_1_poison" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)


async def test_gateway_start_survives_undecodable_record_and_delivers_the_rest(tmp_path: Path) -> None:
    await save_delivery(_record("feishu_user_1_poison", {"channel": "feishu"}), base_dir=tmp_path)
    await save_delivery(_record("feishu_user_1_healthy", _message("healthy").to_dict()), base_dir=tmp_path)
    bus = MessageBus(dlq_dir=tmp_path)
    channel = _RecordingChannel()
    bus.register_channel(channel)

    await bus.start()
    try:
        await asyncio.sleep(0.3)
        assert [m.content for m in channel.sent] == ["healthy"]
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        await bus.stop()
