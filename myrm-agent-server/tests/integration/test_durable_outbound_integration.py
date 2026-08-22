"""Integration tests for durable outbound gate (real bus/gateway/channel wiring)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from myrm_agent_harness.infra.delivery.storage import (
    QueuedDelivery,
    load_pending_deliveries,
    save_delivery,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobType,
    Schedule,
)

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.routing.message_effects import MessageEffects
from app.channels.types import ChannelStatus, OutboundMessage, RenderStyle
from app.channels.types.status import ChannelCapabilities
from app.core.cron.adapters.channel_delivery import ChannelResultDelivery


class _FeishuStubChannel(BaseChannel):
    name = "feishu"
    capabilities = ChannelCapabilities(max_text_length=4000)
    render_style = RenderStyle(format="text", max_text_length=4000)

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "platform-msg-id"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


class _FailingFeishuChannel(_FeishuStubChannel):
    async def send(self, msg: OutboundMessage) -> str | None:
        raise RuntimeError("platform unavailable")


class _NullSendFeishuChannel(_FeishuStubChannel):
    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return None


class _EditPlaceholderChannel(_FeishuStubChannel):
    edited: list[OutboundMessage]

    def __init__(self) -> None:
        super().__init__()
        self.edited = []

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        self.edited.append(msg)


def _outbound(
    content: str = "integration reply", *, channel: str = "feishu"
) -> OutboundMessage:
    return OutboundMessage(
        channel=channel,
        recipient_id="user_integration",
        content=content,
        user_id="u-integration",
    )


@asynccontextmanager
async def _gateway_with_channel(
    tmp_path,
    *,
    channel: _FeishuStubChannel,
) -> AsyncIterator[ChannelGateway]:
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()
    try:
        yield gateway
    finally:
        await gateway.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_publish_send_ack_clears_disk(tmp_path) -> None:
    """Happy path: persist → channel.send → ack removes disk obligation."""
    channel = _FeishuStubChannel()

    async with _gateway_with_channel(tmp_path, channel=channel) as gw:
        await gw.bus.publish_outbound(_outbound("delivered end to end"))
        await asyncio.sleep(0.4)

        assert len(channel.sent) == 1
        assert channel.sent[0].content == "delivered end to end"
        assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crash_recovery_after_disabled_retains_disk(tmp_path) -> None:
    """Crash simulation: disabled retains disk; gateway restart recovers delivery."""
    channel = _FeishuStubChannel()

    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()
    await gateway.disable_channel("feishu")
    await gateway.bus.publish_outbound(_outbound("held while disabled"))
    await asyncio.sleep(0.4)
    assert len(channel.sent) == 0
    assert len(await load_pending_deliveries(base_dir=tmp_path)) == 1
    await gateway.stop()

    channel.sent.clear()
    channel._status = ChannelStatus.IDLE

    async with _gateway_with_channel(tmp_path, channel=channel):
        await asyncio.sleep(0.4)
        assert len(channel.sent) == 1
        assert "held while disabled" in channel.sent[0].content
        assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_enable_channel_delivers_without_full_restart(tmp_path) -> None:
    """Runtime enable triggers recover without tearing down the gateway."""
    channel = _FeishuStubChannel()

    async with _gateway_with_channel(tmp_path, channel=channel) as gw:
        await gw.disable_channel("feishu")
        await gw.bus.publish_outbound(_outbound("enable path"))
        await asyncio.sleep(0.4)
        assert len(channel.sent) == 0

        await gw.enable_channel("feishu")
        await asyncio.sleep(0.4)
        assert len(channel.sent) == 1
        assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_failure_clears_obligation_and_records_dlq(tmp_path) -> None:
    """Permanent send failure acks disk obligation and moves payload to DLQ."""
    channel = _FailingFeishuChannel()

    async with _gateway_with_channel(tmp_path, channel=channel) as gw:
        await gw.bus.publish_outbound(_outbound("will fail"))
        await asyncio.sleep(2.0)

        assert channel.sent == []
        assert await load_pending_deliveries(base_dir=tmp_path) == []
        dlq = await gw.bus.get_dlq_messages()
        assert len(dlq) == 1
        assert dlq[0].channel == "feishu"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_attempting_recovery_prepends_honest_marker(tmp_path) -> None:
    """Attempting-phase crash recovery prefixes the recovered-reply marker."""
    delivery = QueuedDelivery(
        id="feishu_user_integration_marker",
        channel="feishu",
        recipient="user_integration",
        content=_outbound("body after marker").to_dict(),
        enqueued_at=1.0,
        phase="attempting",
    )
    await save_delivery(delivery, base_dir=tmp_path)

    channel = _FeishuStubChannel()
    async with _gateway_with_channel(tmp_path, channel=channel) as _gw:
        await asyncio.sleep(0.4)
        assert len(channel.sent) == 1
        assert "body after marker" in channel.sent[0].content
        assert (
            "duplicate" in channel.sent[0].content.lower()
            or "重复" in channel.sent[0].content
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cron_im_delivery_clears_disk_obligation(tmp_path) -> None:
    """Cron IM delivery uses the same durable gate as bus outbound."""
    channel = _FeishuStubChannel()
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()

    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        job = CronJob(
            id="cron-durable-1",
            user_id="u-integration",
            name="daily-report",
            job_type=JobType.AGENT,
            prompt="report",
            schedule=Schedule(kind="cron", expr="0 9 * * *"),
            delivery=DeliveryConfig(channel="feishu", target="user_integration"),
        )
        await ChannelResultDelivery().deliver(
            job, JobResult(success=True, output="Cron IM body")
        )
        await asyncio.sleep(0.2)

        assert len(channel.sent) == 1
        assert channel.sent[0].content.startswith("Cron IM body")
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recover_purges_stale_web_pending_entries(tmp_path) -> None:
    """Non-durable channel entries are acked during recovery instead of being sent."""
    web_delivery = QueuedDelivery(
        id="web_user_1_stale",
        channel="web",
        recipient="user_integration",
        content=_outbound("web stale", channel="web").to_dict(),
        enqueued_at=1.0,
        phase="pending",
    )
    await save_delivery(web_delivery, base_dir=tmp_path)

    channel = _FeishuStubChannel()
    async with _gateway_with_channel(tmp_path, channel=channel) as _gw:
        await asyncio.sleep(0.2)
        assert channel.sent == []
        assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_returns_none_moves_to_dlq_not_false_ack(tmp_path) -> None:
    """Platform send returning None must not ack disk obligation (silent drop guard)."""
    channel = _NullSendFeishuChannel()

    async with _gateway_with_channel(tmp_path, channel=channel) as gw:
        await gw.bus.publish_outbound(_outbound("null send guard"))
        await asyncio.sleep(2.0)

        assert len(channel.sent) == 1
        assert await load_pending_deliveries(base_dir=tmp_path) == []
        dlq = await gw.bus.get_dlq_messages()
        assert len(dlq) == 1
        assert dlq[0].channel == "feishu"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_stopped_channel_retains_disk_obligation(tmp_path) -> None:
    """STOPPED channel retains pending disk entries until channel becomes active."""
    channel = _FeishuStubChannel()

    async with _gateway_with_channel(tmp_path, channel=channel) as gw:
        channel._status = ChannelStatus.STOPPED
        await gw.bus.publish_outbound(_outbound("held while stopped"))
        await asyncio.sleep(0.4)
        assert len(channel.sent) == 0
        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert len(pending) == 1
        assert pending[0].phase == "pending"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cron_send_returns_none_retains_disk(tmp_path) -> None:
    """Cron IM delivery must not ack when channel.send returns None."""
    channel = _NullSendFeishuChannel()
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()

    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        job = CronJob(
            id="cron-null-send",
            user_id="u-integration",
            name="null-send-report",
            job_type=JobType.AGENT,
            prompt="report",
            schedule=Schedule(kind="cron", expr="0 9 * * *"),
            delivery=DeliveryConfig(channel="feishu", target="user_integration"),
        )
        with pytest.raises(RuntimeError, match="no message_id"):
            await ChannelResultDelivery().deliver(
                job, JobResult(success=True, output="Cron fail body")
            )

        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert len(pending) == 1
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_pending_recover_in_order(tmp_path) -> None:
    """Multiple disk-pending entries are all recovered on gateway start."""
    for idx, body in enumerate(("first pending", "second pending")):
        delivery = QueuedDelivery(
            id=f"feishu_user_integration_multi_{idx}",
            channel="feishu",
            recipient="user_integration",
            content=_outbound(body).to_dict(),
            enqueued_at=float(idx),
            phase="pending",
        )
        await save_delivery(delivery, base_dir=tmp_path)

    channel = _FeishuStubChannel()
    async with _gateway_with_channel(tmp_path, channel=channel) as _gw:
        await asyncio.sleep(0.6)
        assert len(channel.sent) == 2
        bodies = [msg.content for msg in channel.sent]
        assert "first pending" in bodies[0] or "first pending" in bodies[1]
        assert "second pending" in bodies[0] or "second pending" in bodies[1]
        assert await load_pending_deliveries(base_dir=tmp_path) == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_queue_full_auto_recovers_when_dispatch_slot_frees(tmp_path) -> None:
    """Disk-pending entries recover automatically when the outbound queue drains."""
    channel = _FeishuStubChannel()
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.bus._max_queue_size = 1
    gateway.register(channel)
    await gateway.start()
    try:
        await gateway.bus.publish_outbound(_outbound("queue slot one"))
        await gateway.bus.publish_outbound(_outbound("queue slot two"))
        await asyncio.sleep(1.5)
        assert len(channel.sent) == 2
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        await gateway.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_send_tracked_clears_disk_obligation(tmp_path) -> None:
    """send_tracked (approval/notify path) uses the same durable persist/ack gate."""
    channel = _FeishuStubChannel()
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()
    try:
        msg = _outbound("tracked direct send")
        message_id = await gateway.bus.send_tracked(msg)
        assert message_id == "platform-msg-id"
        assert len(channel.sent) == 1
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        await gateway.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_edit_placeholder_failure_falls_back_to_publish(tmp_path) -> None:
    """When edit fails, fallback publish_outbound still clears disk obligation."""

    class _FailingEditChannel(_EditPlaceholderChannel):
        async def edit_placeholder_message(
            self,
            chat_id: str,
            message_id: str,
            msg: OutboundMessage,
        ) -> None:
            raise RuntimeError("edit failed")

    channel = _FailingEditChannel()
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()
    try:
        result = _outbound("fallback body")
        await MessageEffects(gateway.bus).edit_placeholder(
            "feishu",
            "user_integration",
            "placeholder-fail",
            result,
        )
        await asyncio.sleep(0.5)
        assert len(channel.sent) == 1
        assert channel.sent[0].content == "fallback body"
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        await gateway.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_edit_placeholder_clears_disk_obligation(tmp_path) -> None:
    """Placeholder edit path persists/acks via the same durable gate as dispatch."""
    channel = _EditPlaceholderChannel()
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(channel)
    await gateway.start()
    try:
        result = _outbound("final via edit")
        await MessageEffects(gateway.bus).edit_placeholder(
            "feishu",
            "user_integration",
            "placeholder-1",
            result,
        )
        await asyncio.sleep(0.2)
        assert len(channel.edited) == 1
        assert channel.edited[0].content == "final via edit"
        assert await load_pending_deliveries(base_dir=tmp_path) == []
    finally:
        await gateway.stop()
