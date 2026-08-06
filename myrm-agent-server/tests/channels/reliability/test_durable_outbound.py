"""Tests for DurableOutboundGate and MessageBus recovery integration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.core.gateway import ChannelGateway
from app.channels.reliability.durable_outbound import (
    METADATA_DELIVERY_ID,
    DurableOutboundGate,
)
from app.channels.types import ChannelCapabilities, ChannelStatus, OutboundMessage
from myrm_agent_harness.infra.delivery.storage import (
    QueuedDelivery,
    load_pending_deliveries,
    save_delivery,
)


class _RecordingChannel(BaseChannel):
    name = "feishu"
    capabilities = ChannelCapabilities()

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "platform_msg_1"


def _outbound(content: str = "hello", channel: str = "feishu") -> OutboundMessage:
    return OutboundMessage(
        channel=channel,
        recipient_id="user_1",
        content=content,
        user_id="u1",
    )


@pytest.mark.asyncio
async def test_prepare_enqueue_persists_im_channel(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = await gate.prepare_enqueue(_outbound())

    delivery_id = gate.get_delivery_id(msg)
    assert delivery_id is not None

    pending = await load_pending_deliveries(base_dir=tmp_path)
    assert len(pending) == 1
    assert pending[0].id == delivery_id
    assert pending[0].phase == "pending"


@pytest.mark.asyncio
async def test_prepare_enqueue_skips_web_channel(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = await gate.prepare_enqueue(_outbound(channel="web"))

    assert gate.get_delivery_id(msg) is None
    pending = await load_pending_deliveries(base_dir=tmp_path)
    assert pending == []


@pytest.mark.asyncio
async def test_ack_removes_pending_entry(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = await gate.prepare_enqueue(_outbound())
    await gate.ack(msg)

    pending = await load_pending_deliveries(base_dir=tmp_path)
    assert pending == []


@pytest.mark.asyncio
async def test_recover_into_bus_requeues_attempting_with_marker(tmp_path: Path) -> None:
    delivery = QueuedDelivery(
        id="feishu_user_1_abc",
        channel="feishu",
        recipient="user_1",
        content=_outbound("final answer").to_dict(),
        enqueued_at=1.0,
        phase="attempting",
    )
    await save_delivery(delivery, base_dir=tmp_path)

    bus = MessageBus(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    bus.register_channel(ch)
    await bus.start()

    try:
        await asyncio.sleep(0.2)
        assert len(ch.sent) == 1
        assert "final answer" in ch.sent[0].content
        assert ch.sent[0].metadata.get(METADATA_DELIVERY_ID) == delivery.id
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_publish_outbound_persists_and_acks_on_send(tmp_path: Path) -> None:
    bus = MessageBus(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    bus.register_channel(ch)
    await bus.start()

    try:
        await bus.publish_outbound(_outbound("persist me"))
        await asyncio.sleep(0.3)

        assert len(ch.sent) == 1
        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert pending == []
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_recover_skips_inflight_ids(tmp_path: Path) -> None:
    delivery = QueuedDelivery(
        id="feishu_user_1_dup",
        channel="feishu",
        recipient="user_1",
        content=_outbound("once").to_dict(),
        enqueued_at=1.0,
        phase="pending",
    )
    await save_delivery(delivery, base_dir=tmp_path)

    bus = MessageBus(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    bus.register_channel(ch)

    first = await bus.durable_outbound.recover_into_bus(bus)
    second = await bus.durable_outbound.recover_into_bus(bus)
    assert first == 1
    assert second == 0

    await bus.start()
    try:
        await asyncio.sleep(0.2)
        assert len(ch.sent) == 1
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_disabled_channel_retains_disk_obligation(tmp_path: Path) -> None:
    bus = MessageBus(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    ch._status = ChannelStatus.DISABLED
    bus.register_channel(ch)
    await bus.start()

    try:
        await bus.publish_outbound(_outbound("deferred"))
        await asyncio.sleep(0.3)

        assert len(ch.sent) == 0
        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert len(pending) == 1
        assert pending[0].phase == "pending"
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_recover_after_disabled_channel_sends_message(tmp_path: Path) -> None:
    bus = MessageBus(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    ch._status = ChannelStatus.DISABLED
    bus.register_channel(ch)
    await bus.start()

    try:
        await bus.publish_outbound(_outbound("after enable"))
        await asyncio.sleep(0.3)
        assert len(ch.sent) == 0

        ch._status = ChannelStatus.IDLE
        recovered = await bus.durable_outbound.recover_into_bus(bus)
        assert recovered == 1

        await asyncio.sleep(0.3)
        assert len(ch.sent) == 1
        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert pending == []
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_unregistered_channel_retains_disk_obligation(tmp_path: Path) -> None:
    bus = MessageBus(dlq_dir=tmp_path)
    await bus.start()

    try:
        await bus.publish_outbound(_outbound("orphan", channel="missing"))
        await asyncio.sleep(0.3)

        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert len(pending) == 1
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_enable_channel_recovers_pending_outbound(tmp_path: Path) -> None:
    gw = ChannelGateway(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    gw.register(ch)
    await gw.start()

    try:
        await gw.disable_channel("feishu")
        await gw.bus.publish_outbound(_outbound("gateway recover"))
        await asyncio.sleep(0.3)
        assert len(ch.sent) == 0

        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert len(pending) == 1

        result = await gw.enable_channel("feishu")
        assert result is True
        await asyncio.sleep(0.3)

        assert len(ch.sent) == 1
        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert pending == []
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_publish_outbound_queue_full_allows_recovery(tmp_path: Path) -> None:
    bus = MessageBus(max_queue_size=1, dlq_dir=tmp_path)
    ch = _RecordingChannel()
    bus.register_channel(ch)
    await bus.start()

    try:
        await bus.publish_outbound(_outbound("queued"))
        await bus.publish_outbound(_outbound("blocked"))
        await asyncio.sleep(1.5)
        assert len(ch.sent) == 2
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_gate_disabled_is_noop() -> None:
    gate = DurableOutboundGate(None)
    assert gate.base_dir is None
    assert gate.is_enabled() is False
    assert await gate.count_pending() == 0

    bus = MessageBus()
    assert await gate.recover_into_bus(bus) == 0

    msg = _outbound()
    await gate.ack(msg)
    await gate.mark_attempting(msg)
    assert await gate.persist_direct_send(msg) is msg


@pytest.mark.asyncio
async def test_prepare_enqueue_skips_recovered_message(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = OutboundMessage(
        channel="feishu",
        recipient_id="user_1",
        content="already recovered",
        user_id="u1",
        metadata={METADATA_DELIVERY_ID: "existing_id", "_durable_recovered": True},
    )
    result = await gate.prepare_enqueue(msg)
    assert gate.get_delivery_id(result) == "existing_id"
    assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.asyncio
async def test_mark_attempting_updates_phase(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = await gate.prepare_enqueue(_outbound("attempt me"))
    await gate.mark_attempting(msg)

    pending = await load_pending_deliveries(base_dir=tmp_path)
    assert len(pending) == 1
    assert pending[0].phase == "attempting"


@pytest.mark.asyncio
async def test_mark_attempting_skips_without_delivery_id(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    await gate.mark_attempting(_outbound())
    assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.asyncio
async def test_recover_skips_non_durable_channel_entries(tmp_path: Path) -> None:
    delivery = QueuedDelivery(
        id="web_user_1_skip",
        channel="web",
        recipient="user_1",
        content=_outbound("skip", channel="web").to_dict(),
        enqueued_at=1.0,
        phase="pending",
    )
    await save_delivery(delivery, base_dir=tmp_path)

    gate = DurableOutboundGate(tmp_path)
    bus = MessageBus(dlq_dir=tmp_path)
    recovered = await gate.recover_into_bus(bus)
    assert recovered == 0
    assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.asyncio
async def test_count_pending_returns_disk_total(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    await gate.prepare_enqueue(_outbound("one"))
    await gate.prepare_enqueue(_outbound("two"))

    assert await gate.count_pending() == 2


@pytest.mark.asyncio
async def test_ack_without_delivery_id_is_noop(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    await gate.ack(_outbound())
    assert await gate.count_pending() == 0


@pytest.mark.asyncio
async def test_prepare_enqueue_skips_silent_and_chat(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    for channel in ("silent", "chat"):
        msg = await gate.prepare_enqueue(_outbound(channel=channel))
        assert gate.get_delivery_id(msg) is None
    assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.asyncio
async def test_track_enqueued_and_release_inflight(tmp_path: Path) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = await gate.prepare_enqueue(_outbound("inflight"))
    delivery_id = gate.get_delivery_id(msg)
    assert delivery_id is not None

    gate.track_enqueued(msg)
    bus = MessageBus(dlq_dir=tmp_path)
    assert await gate.recover_into_bus(bus) == 0

    gate.release_inflight(msg)
    recovered = await gate.recover_into_bus(bus)
    assert recovered == 1


@pytest.mark.asyncio
async def test_maybe_recover_skips_when_queue_full(tmp_path: Path) -> None:
    bus = MessageBus(max_queue_size=1, dlq_dir=tmp_path)
    await bus.publish_outbound(_outbound("fills queue"))
    await bus.durable_outbound.prepare_enqueue(_outbound("on disk only"))
    await bus._maybe_recover_durable_outbound()
    pending = await load_pending_deliveries(base_dir=tmp_path)
    assert len(pending) >= 2


@pytest.mark.asyncio
async def test_maybe_recover_noop_when_gate_disabled() -> None:
    bus = MessageBus()
    await bus._maybe_recover_durable_outbound()
