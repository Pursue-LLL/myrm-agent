"""Tests for MessageBus delivery contract: send_now / send_tracked / dispatch loop settle rules."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.infra.delivery.storage import load_pending_deliveries

from app.channels.core.bus import MessageBus
from app.channels.core.exceptions import ChannelSendError, DeliveryUnconfirmedError
from app.channels.types import ChannelCapabilities, ChannelStatus
from tests.channels.core.outbound_testkit import CP_MODULE, ProbeChannel, make_doc, make_msg, running_bus


class TestSendNowOutcome:
    @pytest.mark.asyncio
    async def test_returns_platform_message_id(self, tmp_path: Path) -> None:
        channel = ProbeChannel(result="mid-42")
        async with running_bus(tmp_path, channel) as bus:
            assert await bus.send_now(make_msg()) == "mid-42"

            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []

    @pytest.mark.asyncio
    async def test_missing_id_on_id_reporting_channel_raises_and_moves_to_dlq(self, tmp_path: Path) -> None:
        channel = ProbeChannel(result=None)
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(DeliveryUnconfirmedError):
                await bus.send_now(make_msg("needs proof"))

            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert [item.content["content"] for item in await bus.get_dlq_messages()] == ["needs proof"]
            assert channel.activity.total_errors == 1

    @pytest.mark.asyncio
    async def test_id_less_channel_counts_none_as_delivered(self, tmp_path: Path) -> None:
        channel = ProbeChannel(capabilities=ChannelCapabilities(message_ids=False), result=None)
        async with running_bus(tmp_path, channel) as bus:
            assert await bus.send_now(make_msg()) is None

            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []
            assert channel.activity.total_outbound == 1

    @pytest.mark.asyncio
    async def test_media_only_send_without_id_is_delivered(self, tmp_path: Path) -> None:
        channel = ProbeChannel(result=None)
        async with running_bus(tmp_path, channel) as bus:
            assert await bus.send_now(make_msg("", media=(make_doc("a.pdf"),))) is None

            assert await bus.get_dlq_messages() == []

    @pytest.mark.asyncio
    async def test_provider_error_raises_after_recording(self, tmp_path: Path) -> None:
        channel = ProbeChannel(error=ChannelSendError("rejected", retriable=False))
        permanent = AsyncMock()
        bus = MessageBus(dlq_dir=tmp_path, on_permanent_failure=permanent)
        bus.register_channel(channel)
        await bus.start()
        try:
            with pytest.raises(ChannelSendError, match="rejected"):
                await bus.send_now(make_msg())

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
        channel = ProbeChannel()
        channel._status = status
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError, match=expected):
                await bus.send_now(make_msg())

            assert channel.sent == []
            assert await load_pending_deliveries(base_dir=tmp_path) == []
            assert await bus.get_dlq_messages() == []

    @pytest.mark.asyncio
    async def test_unregistered_channel_raises(self, tmp_path: Path) -> None:
        async with running_bus(tmp_path) as bus:
            with pytest.raises(ChannelSendError, match="No channel registered"):
                await bus.send_now(make_msg())

    @pytest.mark.asyncio
    async def test_cancellation_propagates_and_is_not_recorded_as_failure(self, tmp_path: Path) -> None:
        channel = ProbeChannel(error=asyncio.CancelledError())
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(asyncio.CancelledError):
                await bus.send_now(make_msg())

            assert await bus.get_dlq_messages() == []


class TestPartialDelivery:
    @staticmethod
    def _partial_error() -> ChannelSendError:
        return ChannelSendError("attachment rejected", accepted=True, failed_attachments=("b.pdf",))

    @pytest.mark.asyncio
    async def test_is_not_retried_and_only_failed_attachments_are_recorded(self, tmp_path: Path) -> None:
        channel = ProbeChannel(error=self._partial_error(), error_only_with_media=True)
        async with running_bus(tmp_path, channel) as bus:
            msg = make_msg("two files", media=(make_doc("a.pdf"), make_doc("b.pdf")))

            with pytest.raises(ChannelSendError) as excinfo:
                await bus.send_now(msg)

            assert excinfo.value.accepted is True
            assert len([m for m in channel.sent if m.media]) == 1  # never replayed
            (failed,) = await bus.get_dlq_messages()
            assert failed.content["content"] == ""
            assert [m["path"] for m in failed.content["media"]] == ["/tmp/b.pdf"]

    @pytest.mark.asyncio
    async def test_recipient_is_told_which_attachments_did_not_arrive(self, tmp_path: Path) -> None:
        channel = ProbeChannel(error=self._partial_error(), error_only_with_media=True)
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError):
                await bus.send_now(make_msg("two files", media=(make_doc("a.pdf"), make_doc("b.pdf"))))
            for _ in range(50):
                if any(not m.media for m in channel.sent):
                    break
                await asyncio.sleep(0.02)

            notes = [m for m in channel.sent if not m.media]
            assert len(notes) == 1
            assert "b.pdf" in notes[0].content

    @pytest.mark.asyncio
    async def test_missing_text_chunks_never_replay_attachments_that_arrived(self, tmp_path: Path) -> None:
        channel = ProbeChannel(error=ChannelSendError("chunk 2 rejected", accepted=True))
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError):
                await bus.send_now(make_msg("a very long answer", media=(make_doc("a.pdf"),)))

            assert [m.content for m in channel.sent] == ["a very long answer"]  # no retry, no attachment note
            (failed,) = await bus.get_dlq_messages()
            assert failed.content["content"] == "a very long answer"

    @pytest.mark.asyncio
    async def test_does_not_count_against_channel_health(self, tmp_path: Path) -> None:
        channel = ProbeChannel(error=self._partial_error(), error_only_with_media=True)
        async with running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(make_msg("two files", media=(make_doc("a.pdf"), make_doc("b.pdf"))))
            for _ in range(50):
                if channel.sent:
                    break
                await asyncio.sleep(0.02)
            await asyncio.sleep(0.1)

            assert channel.health.consecutive_failures == 0


class TestDispatchLoop:
    @pytest.mark.asyncio
    async def test_id_less_channel_send_is_acknowledged(self, tmp_path: Path) -> None:
        channel = ProbeChannel(capabilities=ChannelCapabilities(message_ids=False), result=None)
        async with running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(make_msg())
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
        channel = ProbeChannel(result=None)
        async with running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(make_msg("no proof"))
            for _ in range(50):
                if await bus.get_dlq_messages():
                    break
                await asyncio.sleep(0.02)

            assert [item.content["content"] for item in await bus.get_dlq_messages()] == ["no proof"]
            assert await load_pending_deliveries(base_dir=tmp_path) == []


class TestControlPlaneRoute:
    @pytest.mark.asyncio
    async def test_cloud_send_goes_through_egress_as_text_and_returns_real_id(self, tmp_path: Path) -> None:
        async with running_bus(tmp_path) as bus:  # cloud sandbox: no local provider is registered
            with (
                patch(f"{CP_MODULE}.should_route_via_control_plane", return_value=True),
                patch(f"{CP_MODULE}.send_via_control_plane", new=AsyncMock(return_value="cp-mid-9")) as egress,
            ):
                message_id = await bus.send_now(make_msg("see file", media=(make_doc("report.pdf"),)))

            assert message_id == "cp-mid-9"
            sent = egress.await_args.kwargs
            assert sent["chat_id"] == "chat-1"
            assert sent["content"].startswith("see file")
            assert "report.pdf" in sent["content"]  # attachment degraded to a note, never dropped silently

    @pytest.mark.asyncio
    async def test_egress_failure_raises_and_is_recorded(self, tmp_path: Path) -> None:
        async with running_bus(tmp_path) as bus:
            with (
                patch(f"{CP_MODULE}.should_route_via_control_plane", return_value=True),
                patch(f"{CP_MODULE}.send_via_control_plane", new=AsyncMock(return_value=None)),
                pytest.raises(ChannelSendError, match="control-plane egress failed"),
            ):
                await bus.send_now(make_msg())

            assert len(await bus.get_dlq_messages()) == 1
