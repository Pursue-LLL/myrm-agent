"""Tests for outbound preparation helpers: delivery verdict and partial-delivery remainder."""

from __future__ import annotations

from app.channels.core.outbound_prepare import (
    delivery_unconfirmed,
    downgrade_components,
    partial_failure_note,
    prepare_outbound,
    undelivered_part,
)
from app.channels.types import ChannelCapabilities, MediaAttachment, MediaType, OutboundMessage


def _msg(content: str = "report ready", *media: MediaAttachment, locale: str | None = None) -> OutboundMessage:
    return OutboundMessage(
        channel="probe",
        recipient_id="chat-1",
        content=content,
        user_id="u1",
        media=media,
        reply_to_id="r-1",
        thread_id="th-1",
        metadata={"locale": locale, "_durable_delivery_id": "d-1"} if locale else None,
    )


def _doc(name: str) -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=f"/tmp/{name}")


class TestDeliveryUnconfirmed:
    def test_missing_id_with_text_on_id_reporting_channel_is_unconfirmed(self) -> None:
        assert delivery_unconfirmed(ChannelCapabilities(), _msg(), None) is True

    def test_returned_id_is_confirmed(self) -> None:
        assert delivery_unconfirmed(ChannelCapabilities(), _msg(), "mid-1") is False

    def test_id_less_channel_counts_none_as_delivered(self) -> None:
        assert delivery_unconfirmed(ChannelCapabilities(message_ids=False), _msg(), None) is False

    def test_media_only_send_without_id_is_delivered(self) -> None:
        assert delivery_unconfirmed(ChannelCapabilities(), _msg("", _doc("a.pdf")), None) is False


class TestUndeliveredPart:
    def test_keeps_only_failed_attachments_and_drops_text(self) -> None:
        msg = _msg("text", _doc("a.pdf"), _doc("b.pdf"), _doc("c.pdf"))

        remainder = undelivered_part(msg, ("b.pdf",))

        assert remainder.content == ""
        assert [m.display_name for m in remainder.media] == ["b.pdf"]
        assert remainder.components == ()
        assert remainder.recipient_id == msg.recipient_id

    def test_unknown_names_fall_back_to_all_attachments(self) -> None:
        msg = _msg("text", _doc("a.pdf"), _doc("b.pdf"))

        assert [m.display_name for m in undelivered_part(msg, ("other.bin",)).media] == ["a.pdf", "b.pdf"]


class TestPartialFailureNote:
    def test_note_is_localized_and_addressed_like_the_original(self) -> None:
        note = partial_failure_note(_msg("text", _doc("a.pdf"), locale="zh-CN"), ("a.pdf", "b.pdf"))

        assert "a.pdf, b.pdf" in note.content
        assert "附件" in note.content
        assert (note.channel, note.recipient_id, note.reply_to_id, note.thread_id) == ("probe", "chat-1", "r-1", "th-1")
        assert note.media == ()

    def test_note_does_not_inherit_durable_delivery_metadata(self) -> None:
        note = partial_failure_note(_msg("text", _doc("a.pdf"), locale="en"), ("a.pdf",))

        assert note.metadata == {"locale": "en"}


class TestPrepareOutbound:
    def test_text_only_route_turns_attachments_into_a_localized_note(self) -> None:
        msg = _msg("see attachment", _doc("report.pdf"), locale="en")

        prepared = prepare_outbound(msg, ChannelCapabilities(), channel_name="feishu")

        assert prepared.media == ()
        assert "Attachment not sent: report.pdf" in prepared.content

    def test_downgrade_keeps_media_the_route_supports(self) -> None:
        msg = _msg("see attachment", _doc("report.pdf"))

        kept = downgrade_components(msg, ChannelCapabilities(file_upload=True), channel_name="feishu")

        assert kept is msg
