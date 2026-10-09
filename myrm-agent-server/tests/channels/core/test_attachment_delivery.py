"""Tests for per-attachment delivery: every attachment is attempted, failures are reported together."""

from __future__ import annotations

import asyncio

import pytest

from app.channels.core.attachment_delivery import deliver_attachments
from app.channels.core.exceptions import ChannelSendError
from app.channels.types import MediaAttachment, MediaType


def _doc(name: str) -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.DOCUMENT, filename=name)


class _Recorder:
    """send_one stand-in that records attempts, fails for the named attachments and reports ``<name>-id`` otherwise."""

    def __init__(self, *failing: str) -> None:
        self.attempted: list[str] = []
        self._failing = set(failing)

    async def __call__(self, attachment: MediaAttachment) -> str | None:
        self.attempted.append(attachment.display_name)
        if attachment.display_name in self._failing:
            raise OSError("upload rejected")
        return f"{attachment.display_name}-id"


async def _permanent(_: MediaAttachment) -> None:
    raise ChannelSendError("unsupported attachment", channel="chan", retriable=False)


class TestDeliverAttachments:
    @pytest.mark.asyncio
    async def test_all_delivered_raises_nothing(self) -> None:
        send = _Recorder()

        await deliver_attachments("chan", (_doc("a.pdf"), _doc("b.pdf")), send, text_delivered=True)

        assert send.attempted == ["a.pdf", "b.pdf"]

    @pytest.mark.asyncio
    async def test_returns_the_id_of_the_last_attachment_that_reported_one(self) -> None:
        assert await deliver_attachments("chan", (_doc("a.pdf"), _doc("b.pdf")), _Recorder(), text_delivered=False) == "b.pdf-id"
        assert await deliver_attachments("chan", (), _Recorder(), text_delivered=True) is None

    @pytest.mark.asyncio
    async def test_one_failure_does_not_stop_the_others(self) -> None:
        send = _Recorder("a.pdf")

        with pytest.raises(ChannelSendError) as excinfo:
            await deliver_attachments("chan", (_doc("a.pdf"), _doc("b.pdf")), send, text_delivered=False)

        assert send.attempted == ["a.pdf", "b.pdf"]
        assert excinfo.value.failed_attachments == ("a.pdf",)

    @pytest.mark.asyncio
    async def test_failure_after_delivered_text_is_a_partial_delivery(self) -> None:
        with pytest.raises(ChannelSendError) as excinfo:
            await deliver_attachments("chan", (_doc("a.pdf"),), _Recorder("a.pdf"), text_delivered=True)

        assert (excinfo.value.accepted, excinfo.value.retriable) == (True, False)

    @pytest.mark.asyncio
    async def test_failure_after_another_attachment_arrived_is_a_partial_delivery(self) -> None:
        with pytest.raises(ChannelSendError) as excinfo:
            await deliver_attachments("chan", (_doc("a.pdf"), _doc("b.pdf")), _Recorder("b.pdf"), text_delivered=False)

        assert excinfo.value.accepted is True
        assert excinfo.value.failed_attachments == ("b.pdf",)

    @pytest.mark.asyncio
    async def test_nothing_delivered_yet_stays_retriable(self) -> None:
        with pytest.raises(ChannelSendError) as excinfo:
            await deliver_attachments("chan", (_doc("a.pdf"), _doc("b.pdf")), _Recorder("a.pdf", "b.pdf"), text_delivered=False)

        assert (excinfo.value.accepted, excinfo.value.retriable) == (False, True)
        assert excinfo.value.channel == "chan"

    @pytest.mark.asyncio
    async def test_only_permanent_failures_are_not_retriable(self) -> None:
        with pytest.raises(ChannelSendError) as excinfo:
            await deliver_attachments("chan", (_doc("a.pdf"),), _permanent, text_delivered=False)

        assert (excinfo.value.accepted, excinfo.value.retriable) == (False, False)

    @pytest.mark.asyncio
    async def test_one_transient_failure_keeps_the_error_retriable(self) -> None:
        async def mixed(attachment: MediaAttachment) -> None:
            if attachment.display_name == "a.pdf":
                await _permanent(attachment)
            raise OSError("upload timed out")

        with pytest.raises(ChannelSendError) as excinfo:
            await deliver_attachments("chan", (_doc("a.pdf"), _doc("b.pdf")), mixed, text_delivered=False)

        assert excinfo.value.retriable is True

    @pytest.mark.asyncio
    async def test_cancellation_is_never_swallowed(self) -> None:
        async def cancelled(_: MediaAttachment) -> None:
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await deliver_attachments("chan", (_doc("a.pdf"),), cancelled, text_delivered=False)
