"""Unit tests for ChannelResultDelivery durable gate wiring."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.types import ChannelCapabilities, ChannelStatus, OutboundMessage
from app.core.cron.adapters.channel_delivery import ChannelResultDelivery
from myrm_agent_harness.infra.delivery.storage import load_pending_deliveries
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobType,
    Schedule,
)


@pytest.mark.asyncio
async def test_deliver_channel_null_send_retains_disk(tmp_path) -> None:
    class _NullChannel(BaseChannel):
        name = "feishu"
        capabilities = ChannelCapabilities()

        async def send(self, msg: OutboundMessage) -> str | None:
            return None

    job = CronJob(
        id="cron-unit-null",
        user_id="u1",
        name="report",
        job_type=JobType.AGENT,
        prompt="p",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="feishu", target="chat-1"),
    )

    from app.channels.core.gateway import ChannelGateway

    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(_NullChannel())
    await gateway.start()

    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        with pytest.raises(RuntimeError, match="no message_id"):
            await ChannelResultDelivery().deliver(
                job, JobResult(success=True, output="body")
            )

        pending = await load_pending_deliveries(base_dir=tmp_path)
        assert len(pending) == 1
        assert pending[0].channel == "feishu"
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()


@pytest.mark.asyncio
async def test_deliver_disabled_channel_raises() -> None:
    from app.channels.core.gateway import ChannelGateway
    from app.channels.types import ChannelStatus

    class _FeishuChannel(BaseChannel):
        name = "feishu"
        capabilities = ChannelCapabilities()

        async def send(self, msg: OutboundMessage) -> str | None:
            return "id"

    job = CronJob(
        id="cron-disabled",
        user_id="u1",
        name="report",
        job_type=JobType.AGENT,
        prompt="p",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="feishu", target="chat-1"),
    )

    gateway = ChannelGateway()
    ch = _FeishuChannel()
    ch._status = ChannelStatus.DISABLED
    gateway.register(ch)
    await gateway.start()

    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        with pytest.raises(RuntimeError, match="disabled"):
            await ChannelResultDelivery().deliver(
                job, JobResult(success=True, output="body")
            )
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()


@pytest.mark.asyncio
async def test_deliver_missing_channel_raises() -> None:
    job = CronJob(
        id="cron-missing",
        user_id="u1",
        name="report",
        job_type=JobType.AGENT,
        prompt="p",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="missing", target="chat-1"),
    )

    import app.core.channel_bridge as channel_bridge

    gateway = channel_bridge.channel_gateway
    with pytest.raises(RuntimeError, match="No channel registered"):
        await ChannelResultDelivery().deliver(
            job, JobResult(success=True, output="body")
        )


def test_resolve_recipient_requires_target() -> None:
    job = CronJob(
        id="cron-no-target",
        user_id="u1",
        name="report",
        job_type=JobType.AGENT,
        prompt="p",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="feishu", target=""),
    )
    with pytest.raises(ValueError, match="target is required"):
        ChannelResultDelivery._resolve_recipient(job)


@pytest.mark.asyncio
async def test_deliver_silent_channel_is_noop() -> None:
    job = CronJob(
        id="cron-silent",
        user_id="u1",
        name="report",
        job_type=JobType.AGENT,
        prompt="p",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="silent", target="chat-1"),
    )
    await ChannelResultDelivery().deliver(job, JobResult(success=True, output="silent"))


@pytest.mark.asyncio
async def test_deliver_appends_error_to_content(tmp_path) -> None:
    class _OkChannel(BaseChannel):
        name = "feishu"
        capabilities = ChannelCapabilities()

        async def send(self, msg: OutboundMessage) -> str | None:
            assert "Error:" in msg.content
            return "ok-id"

    from app.channels.core.gateway import ChannelGateway

    job = CronJob(
        id="cron-error-body",
        user_id="u1",
        name="report",
        job_type=JobType.AGENT,
        prompt="p",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="feishu", target="chat-1"),
    )
    gateway = ChannelGateway(dlq_dir=tmp_path)
    gateway.register(_OkChannel())
    await gateway.start()

    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        await ChannelResultDelivery().deliver(
            job,
            JobResult(success=False, output="partial", error="boom"),
        )
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()
