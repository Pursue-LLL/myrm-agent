"""Bus-owned temp attachments: removed once delivery is final, kept while a record can still replay them."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest
from myrm_agent_harness.infra.delivery.storage import load_pending_deliveries

from app.channels.core.bus import MessageBus
from app.channels.core.exceptions import ChannelSendError
from app.channels.types import ChannelCapabilities, ChannelStatus, MediaAttachment, OutboundMessage
from tests.channels.core.outbound_testkit import ProbeChannel, make_ephemeral_doc, make_msg, running_bus


async def _eventually(condition: Callable[[], bool], *, timeout: float = 3.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if condition():
            return True
        await asyncio.sleep(0.02)
    return condition()


def _gone(attachment: MediaAttachment) -> bool:
    return attachment.path is not None and not Path(attachment.path).exists()


def _kept(attachment: MediaAttachment) -> bool:
    return attachment.path is not None and Path(attachment.path).exists()


def _cleanup(*attachments: MediaAttachment) -> None:
    for attachment in attachments:
        if attachment.path:
            Path(attachment.path).unlink(missing_ok=True)


class TestDirectSend:
    @pytest.mark.asyncio
    async def test_delivered_files_are_removed(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        async with running_bus(tmp_path, ProbeChannel()) as bus:
            await bus.send_now(make_msg("here", media=(doc,)))

        assert _gone(doc)

    @pytest.mark.asyncio
    async def test_files_survive_a_failed_send_for_manual_retry(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = ProbeChannel(error=ChannelSendError("rejected", retriable=False))
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError):
                await bus.send_now(make_msg("here", media=(doc,)))
            (failed,) = await bus.get_dlq_messages()

            assert [m["path"] for m in failed.content["media"]] == [doc.path]
            assert _kept(doc)
        _cleanup(doc)

    @pytest.mark.asyncio
    async def test_partial_delivery_removes_delivered_files_and_keeps_the_failed_one(self, tmp_path: Path) -> None:
        delivered, failed_doc = make_ephemeral_doc("a.pdf"), make_ephemeral_doc("b.pdf")
        error = ChannelSendError("attachment rejected", accepted=True, failed_attachments=("b.pdf",))
        channel = ProbeChannel(error=error, error_only_with_media=True)
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError):
                await bus.send_now(make_msg("two files", media=(delivered, failed_doc)))
            (record,) = await bus.get_dlq_messages()

            assert [m["path"] for m in record.content["media"]] == [failed_doc.path]
            assert _gone(delivered)
            assert _kept(failed_doc)
        _cleanup(failed_doc)

    @pytest.mark.asyncio
    async def test_files_are_removed_when_the_channel_is_unavailable(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = ProbeChannel()
        channel._status = ChannelStatus.DISABLED
        async with running_bus(tmp_path, channel) as bus:
            with pytest.raises(ChannelSendError, match="disabled"):
                await bus.send_now(make_msg("here", media=(doc,)))

        assert _gone(doc)

    @pytest.mark.asyncio
    async def test_attachments_the_channel_cannot_carry_are_removed_after_the_text_goes_out(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = ProbeChannel(capabilities=ChannelCapabilities(media=False, file_upload=False))
        async with running_bus(tmp_path, channel) as bus:
            await bus.send_now(make_msg("here", media=(doc,)))

        assert channel.sent[0].media == ()
        assert "report.pdf" in channel.sent[0].content
        assert _gone(doc)


class _UploadingChannel(ProbeChannel):
    """Reads every attachment at send time, as a real provider uploading the file would."""

    def __init__(self) -> None:
        super().__init__()
        self.uploaded: list[bytes] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.uploaded.extend(Path(m.path).read_bytes() for m in msg.media if m.path)
        return await super().send(msg)


class TestDispatchLoop:
    @pytest.mark.asyncio
    async def test_files_are_still_on_disk_when_the_provider_uploads_them(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = _UploadingChannel()
        async with running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(make_msg("here", media=(doc,)))

            assert await _eventually(lambda: _gone(doc))
        assert channel.uploaded == [b"payload"]

    @pytest.mark.asyncio
    async def test_files_are_removed_once_the_send_is_acknowledged(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        async with running_bus(tmp_path, ProbeChannel()) as bus:
            await bus.publish_outbound(make_msg("here", media=(doc,)))

            assert await _eventually(lambda: _gone(doc))

    @pytest.mark.asyncio
    async def test_files_of_a_message_that_can_never_be_replayed_are_removed(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = ProbeChannel()
        channel._status = ChannelStatus.DISABLED
        async with running_bus(None, channel) as bus:  # no durable outbox: dropping the message loses it for good
            await bus.publish_outbound(make_msg("here", media=(doc,)))

            assert await _eventually(lambda: _gone(doc))

    @pytest.mark.asyncio
    async def test_files_stay_while_a_durable_record_can_still_replay_the_message(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        channel = ProbeChannel()
        channel._status = ChannelStatus.DISABLED
        async with running_bus(tmp_path, channel) as bus:
            await bus.publish_outbound(make_msg("here", media=(doc,)))
            await asyncio.sleep(0.3)  # the dispatch loop has long since reached the unavailable branch

            assert len(await load_pending_deliveries(base_dir=tmp_path)) == 1
            assert _kept(doc)
        _cleanup(doc)

    @pytest.mark.asyncio
    async def test_queue_overflow_removes_files_of_the_dropped_message(self) -> None:
        doc = make_ephemeral_doc("report.pdf")
        bus = MessageBus(max_queue_size=1)  # never started: nothing drains the queue

        await bus.publish_outbound(make_msg("filler"))
        await bus.publish_outbound(make_msg("dropped", media=(doc,)))

        assert _gone(doc)

    @pytest.mark.asyncio
    async def test_queue_overflow_keeps_files_when_a_durable_record_remains(self, tmp_path: Path) -> None:
        doc = make_ephemeral_doc("report.pdf")
        bus = MessageBus(max_queue_size=1, dlq_dir=tmp_path)

        await bus.publish_outbound(make_msg("filler"))
        await bus.publish_outbound(make_msg("dropped", media=(doc,)))

        assert _kept(doc)
        _cleanup(doc)
