"""Tests for MessageBus delivery contract: send_now / send_tracked / dispatch loop settle rules."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.infra.delivery.storage import load_pending_deliveries

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.core.exceptions import ChannelSendError, DeliveryUnconfirmedError
from app.channels.reliability.retry import RetryConfig
from app.channels.types import ChannelCapabilities, ChannelStatus, MediaAttachment, MediaType, OutboundMessage

_CP_MODULE = "app.services.channels.cp_egress_client"


class _ProbeChannel(BaseChannel):
    """Configurable provider: returns ``result`` or raises ``error`` and records every send."""

    name = "probe"
    retry_config = RetryConfig(max_retries=3, base_delay=0.0, jitter=0.0)

    def __init__(
        self,
        *,
        capabilities: ChannelCapabilities | None = None,
        result: str | None = "mid-1",
        error: Exception | None = None,
        error_only_with_media: bool = False,
    ) -> None:
        super().__init__()
        self.capabilities = capabilities or ChannelCapabilities(media=True, file_upload=True)
        self.result = result
        self.error = error
        self.error_only_with_media = error_only_with_media
        self.sent: list[OutboundMessage] = []
        self._status = ChannelStatus.RUNNING

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        if self.error is not None and (msg.media or not self.error_only_with_media):
            raise self.error
        return self.result


def _msg(content: str = "hello", *, media: tuple[MediaAttachment, ...] = ()) -> OutboundMessage:
    return OutboundMessage(channel="probe", recipient_id="chat-1", content=content, user_id="u1", media=media)


def _doc(name: str) -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=f"/tmp/{name}")


@asynccontextmanager
async def _running_bus(tmp_path: Path, channel: BaseChannel | None = None) -> AsyncIterator[MessageBus]:
    bus = MessageBus(dlq_dir=tmp_path)
    if channel is not None:
        bus.register_channel(channel)
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()


class TestSendNowOutcome:
    @pytest.mark.asyncio
    async def test_returns_platform_message_id(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(result="mid-42")
        async with _running_bus(tmp_path, channel) as bus:
            assert await bus.send_now(_msg()) == "mid-42"

            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []

    @pytest.mark.asyncio
    async def test_missing_id_on_id_reporting_channel_raises_and_moves_to_dlq(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(result=None)
        async with _running_bus(tmp_path, channel) as bus:
            with pytest.raises(DeliveryUnconfirmedError):
                await bus.send_now(_msg("needs proof"))

            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert [item.content["content"] for item in await bus.get_dlq_messages()] == ["needs proof"]
            assert channel.activity.total_errors == 1

    @pytest.mark.asyncio
    async def test_id_less_channel_counts_none_as_delivered(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(capabilities=ChannelCapabilities(message_ids=False), result=None)
        async with _running_bus(tmp_path, channel) as bus:
            assert await bus.send_now(_msg()) is None

            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []
            assert channel.activity.total_outbound == 1

    @pytest.mark.asyncio
    async def test_media_only_send_without_id_is_delivered(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(result=None)
        async with _running_bus(tmp_path, channel) as bus:
            assert await bus.send_now(_msg("", media=(_doc("a.pdf"),))) is None

            assert await bus.get_dlq_messages() == []

    @pytest.mark.asyncio
    async def test_provider_error_raises_after_recording(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(error=ChannelSendError("rejected", retriable=False))
        permanent = AsyncMock()
        bus = MessageBus(dlq_dir=tmp_path, on_permanent_failure=permanent)
        bus.register_channel(channel)
        await bus.start()
        try:
            with pytest.raises(ChannelSendError, match="rejected"):
                await bus.send_now(_msg())

            assert len(await bus.get_dlq_messages()) == 1
            permanent.assert_awaited_once()
        finally:
            await bus.stop()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("status", "expected"),
        [(ChannelStatus.DISABLED, "disabled"), (ChannelStatus.STOPPED, "stopped")],
    )
    async def test_unavailable_channel_raises_without_side_effects(
        self, tmp_path: Path, status: ChannelStatus, expected: str
    ) -> None:
        channel = _ProbeChannel()
        channel._status = status
        async with _running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError, match=expected):
                await bus.send_now(_msg())

            assert channel.sent == []
            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []

    @pytest.mark.asyncio
    async def test_unregistered_channel_raises(self, tmp_path: Path) -> None:
        async with _running_bus(tmp_path) as bus:
            with pytest.raises(ChannelSendError, match="No channel registered"):
                await bus.send_now(_msg())

    @pytest.mark.asyncio
    async def test_cancellation_propagates_and_is_not_recorded_as_failure(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(error=asyncio.CancelledError())
        async with _running_bus(tmp_path, channel) as bus:
            with pytest.raises(asyncio.CancelledError):
                await bus.send_now(_msg())

            assert await bus.get_dlq_messages() == []


class TestPartialDelivery:
    @staticmethod
    def _partial_error() -> ChannelSendError:
        return ChannelSendError("attachment rejected", accepted=True, failed_attachments=("b.pdf",))

    @pytest.mark.asyncio
    async def test_is_not_retried_and_only_failed_attachments_are_recorded(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(error=self._partial_error(), error_only_with_media=True)
        async with _running_bus(tmp_path, channel) as bus:
            msg = _msg("two files", media=(_doc("a.pdf"), _doc("b.pdf")))

            with pytest.raises(ChannelSendError) as excinfo:
                await bus.send_now(msg)

            assert excinfo.value.accepted is True
            assert len([m for m in channel.sent if m.media]) == 1  # never replayed
            (failed,) = await bus.get_dlq_messages()
            assert failed.content["content"] == ""
            assert [m["path"] for m in failed.content["media"]] == ["/tmp/b.pdf"]

    @pytest.mark.asyncio
    async def test_recipient_is_told_which_attachments_did_not_arrive(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(error=self._partial_error(), error_only_with_media=True)
        async with _running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError):
                await bus.send_now(_msg("two files", media=(_doc("a.pdf"), _doc("b.pdf"))))
            for _ in range(50):
                if any(not m.media for m in channel.sent):
                    break
                await asyncio.sleep(0.02)

            notes = [m for m in channel.sent if not m.media]
            assert len(notes) == 1
            assert "b.pdf" in notes[0].content

    @pytest.mark.asyncio
    async def test_does_not_count_against_channel_health(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(error=self._partial_error(), error_only_with_media=True)
        async with _running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(_msg("two files", media=(_doc("a.pdf"), _doc("b.pdf"))))
            for _ in range(50):
                if channel.sent:
                    break
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.1)

            assert channel.health.consecutive_failures == 0


class TestDispatchLoop:
    @pytest.mark.asyncio
    async def test_id_less_channel_send_is_acknowledged(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(capabilities=ChannelCapabilities(message_ids=False), result=None)
        async with _running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(_msg())
            for _ in range(50):
                if channel.sent:
                    break
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.1)

            assert len(channel.sent) == 1
            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []
            assert channel.health.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_unconfirmed_send_goes_to_dlq(self, tmp_path: Path) -> None:
        channel = _ProbeChannel(result=None)
        async with _running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(_msg("no proof"))
            for _ in range(50):
                if await bus.get_dlq_messages():
                    break
                await asyncio.sleep(0.02)

            assert [item.content["content"] for item in await bus.get_dlq_messages()] == ["no proof"]
            assert await load_pending_deliveries(base_dir=tmp_path) == []


class TestControlPlaneRoute:
    @pytest.mark.asyncio
    async def test_cloud_send_goes_through_egress_as_text_and_returns_real_id(self, tmp_path: Path) -> None:
        async with _running_bus(tmp_path) as bus:  # cloud sandbox: no local provider is registered
            with (
                patch(f"{_CP_MODULE}.should_route_via_control_plane", return_value=True),
                patch(f"{_CP_MODULE}.send_via_control_plane", new=AsyncMock(return_value="cp-mid-9")) as egress,
            ):
                message_id = await bus.send_now(_msg("see file", media=(_doc("report.pdf"),)))

            assert message_id == "cp-mid-9"
            sent = egress.await_args.kwargs
            assert sent["chat_id"] == "chat-1"
            assert sent["content"].startswith("see file")
            assert "report.pdf" in sent["content"]  # attachment degraded to a note, never dropped silently

    @pytest.mark.asyncio
    async def test_egress_failure_raises_and_is_recorded(self, tmp_path: Path) -> None:
        async with _running_bus(tmp_path) as bus:
            with (
                patch(f"{_CP_MODULE}.should_route_via_control_plane", return_value=True),
                patch(f"{_CP_MODULE}.send_via_control_plane", new=AsyncMock(return_value=None)),
                pytest.raises(ChannelSendError, match="control-plane egress failed"),
            ):
                await bus.send_now(_msg())

            assert len(await bus.get_dlq_messages()) == 1
