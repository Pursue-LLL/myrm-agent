"""What happens to a held channel reply once someone has decided on it.

Approving sends it, rejecting or letting it expire releases it, and either way the "awaiting review" message the
sender was left with is closed. An approved reply that could not go out is reported to the owner, since approving
it promised the sender an answer.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.i18n import channel_t
from app.channels.types import MediaAttachment, MediaType
from app.database.models.approval import ApprovalRecord
from app.services.approvals.outbound_draft import finalize_outbound_draft, send_outbound_draft_payload
from app.services.event.app_event_bus import AppEventType
from tests.channels.core.outbound_testkit import make_ephemeral_doc
from tests.services.approvals.draft_testkit import draft_payload, held_reply

_CLOSED = "\u200b"


class TestSendOutboundDraftPayload:
    async def test_blank_draft_without_attachments_is_skipped(self) -> None:
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(draft_payload(held_reply(), draft_content="  "), "agent-1", "rec-1")

        assert sent is False
        gateway.publish.assert_not_awaited()

    async def test_sends_the_held_reply_with_the_reviewed_text(self, tmp_path: Path) -> None:
        report = MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "report.pdf"), filename="report.pdf")
        reply = held_reply(report)
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(draft_payload(reply, draft_content="edited by reviewer"), "agent-1", "rec-2")

        assert sent is True
        gateway.publish.assert_awaited_once()
        assert gateway.publish.await_args.args[0] == dataclasses.replace(reply, content="edited by reviewer")

    async def test_attachment_only_draft_is_sent(self, tmp_path: Path) -> None:
        reply = held_reply(MediaAttachment(media_type=MediaType.DOCUMENT, path=str(tmp_path / "a.pdf")), content="")
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway):
            sent = await send_outbound_draft_payload(draft_payload(reply), "agent-1", "rec-3")

        assert sent is True
        assert gateway.publish.await_args.args[0] == reply

    async def test_payload_without_a_snapshot_is_not_sent(self, caplog: pytest.LogCaptureFixture) -> None:
        pre_snapshot = {
            "draft_content": "hello",
            "channel": "telegram",
            "recipient_id": "peer-1",
            "draft_media": [{"url": "https://x/a.png", "type": "image"}],
        }
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway), caplog.at_level(logging.WARNING):
            sent = await send_outbound_draft_payload(pre_snapshot, "agent-1", "rec-4")

        assert sent is False
        gateway.publish.assert_not_awaited()
        assert any(r.levelno == logging.WARNING and "rec-4" in r.getMessage() for r in caplog.records)

    async def test_undecodable_snapshot_is_not_sent(self, caplog: pytest.LogCaptureFixture) -> None:
        gateway = AsyncMock()
        with patch("app.core.channel_bridge.get_channel_gateway", return_value=gateway), caplog.at_level(logging.WARNING):
            sent = await send_outbound_draft_payload(
                {"draft_content": "hello", "outbound": {"channel": "telegram"}}, "agent-1", "rec-5"
            )

        assert sent is False
        gateway.publish.assert_not_awaited()
        assert any("rec-5" in r.getMessage() for r in caplog.records)


class _Platform:
    """The channel the sender talks through, as the gateway exposes it."""

    def __init__(self) -> None:
        self.channel = MagicMock()
        self.channel.edit_message = AsyncMock()
        self.channel.delete_message = AsyncMock()
        self.gateway = MagicMock()
        self.gateway.publish = AsyncMock()
        self.gateway.bus.get_channel.return_value = self.channel


@pytest.fixture
def platform() -> Iterator[_Platform]:
    platform = _Platform()
    with patch("app.core.channel_bridge.get_channel_gateway", return_value=platform.gateway):
        yield platform


@pytest.fixture
def owner_notice() -> Iterator[AsyncMock]:
    """The step that tells the owner a reply did not go out (its own behavior is covered below)."""
    with patch("app.services.approvals.outbound_draft._notify_owner_not_sent", new_callable=AsyncMock) as notice:
        yield notice


def _record(status: str, payload: dict[str, object]) -> ApprovalRecord:
    return ApprovalRecord(
        id="rec-1",
        agent_id="agent-1",
        chat_id="chat-1",
        thread_id=None,
        action_type="outbound_draft",
        reason="test",
        severity="info",
        payload=payload,
        status=status,
    )


def _held_in_chat(**extra: object) -> dict[str, object]:
    """A held reply as the router stores it, including the message the sender sees while waiting."""
    return draft_payload(held_reply(), channel="telegram", recipient_id="peer-1", placeholder_id="ph-1", **extra)


class TestFinalizeApprovedDraft:
    async def test_the_reply_is_sent_and_the_waiting_message_closed(self, platform: _Platform, owner_notice: AsyncMock) -> None:
        await finalize_outbound_draft(_record("APPROVED", _held_in_chat()))

        platform.gateway.publish.assert_awaited_once()
        platform.channel.edit_message.assert_awaited_once_with("peer-1", "ph-1", _CLOSED)
        owner_notice.assert_not_awaited()

    async def test_a_reply_with_nothing_to_send_is_reported_to_the_owner(
        self, platform: _Platform, owner_notice: AsyncMock
    ) -> None:
        payload = _held_in_chat(draft_content="  ")

        await finalize_outbound_draft(_record("APPROVED", payload))

        platform.gateway.publish.assert_not_awaited()
        owner_notice.assert_awaited_once_with(payload, "rec-1")
        platform.channel.edit_message.assert_awaited_once_with("peer-1", "ph-1", _CLOSED)

    async def test_a_send_that_fails_is_reported_and_never_raised(
        self, platform: _Platform, owner_notice: AsyncMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        platform.gateway.publish.side_effect = RuntimeError("bus is down")

        with caplog.at_level(logging.ERROR):
            await finalize_outbound_draft(_record("APPROVED", _held_in_chat()))

        owner_notice.assert_awaited_once()
        platform.channel.edit_message.assert_awaited_once_with("peer-1", "ph-1", _CLOSED)
        assert any(r.levelno == logging.ERROR and "rec-1" in r.getMessage() for r in caplog.records)


class TestFinalizeUnsentDraft:
    @pytest.mark.parametrize("status", ["REJECTED", "TIMEOUT"])
    async def test_nothing_is_sent_and_the_temp_attachments_are_released(
        self, status: str, platform: _Platform, owner_notice: AsyncMock
    ) -> None:
        shot = make_ephemeral_doc("shot.png")
        payload = draft_payload(held_reply(shot), channel="telegram", recipient_id="peer-1", placeholder_id="ph-1")

        await finalize_outbound_draft(_record(status, payload))

        platform.gateway.publish.assert_not_awaited()
        assert not Path(shot.path).exists()
        platform.channel.edit_message.assert_awaited_once_with("peer-1", "ph-1", _CLOSED)
        owner_notice.assert_not_awaited()


class TestWaitingMessage:
    @pytest.mark.parametrize("held", [{"placeholder_id": None}, {}], ids=["null", "absent"])
    async def test_a_chat_without_a_waiting_message_is_left_alone(self, held: dict[str, object], platform: _Platform) -> None:
        payload = draft_payload(held_reply(), channel="telegram", recipient_id="peer-1", **held)

        await finalize_outbound_draft(_record("REJECTED", payload))

        platform.gateway.bus.get_channel.assert_not_called()

    async def test_a_message_the_platform_will_not_edit_is_deleted(self, platform: _Platform) -> None:
        platform.channel.edit_message.side_effect = RuntimeError("message can't be edited")

        await finalize_outbound_draft(_record("REJECTED", _held_in_chat()))

        platform.channel.delete_message.assert_awaited_once_with("peer-1", "ph-1")

    async def test_a_platform_that_hangs_cannot_stall_the_decision(
        self, platform: _Platform, caplog: pytest.LogCaptureFixture
    ) -> None:
        async def hang(*_args: object) -> None:
            await asyncio.sleep(30)

        platform.channel.edit_message.side_effect = hang

        with (
            patch("app.services.approvals.outbound_draft._PLACEHOLDER_CLOSE_TIMEOUT_S", 0.05),
            caplog.at_level(logging.WARNING),
        ):
            await asyncio.wait_for(finalize_outbound_draft(_record("REJECTED", _held_in_chat())), timeout=5)

        assert any(r.levelno == logging.WARNING and "rec-1" in r.getMessage() for r in caplog.records)

    async def test_an_unreachable_gateway_does_not_undo_the_decision(self, caplog: pytest.LogCaptureFixture) -> None:
        with (
            patch("app.core.channel_bridge.get_channel_gateway", side_effect=RuntimeError("gateway is not running")),
            caplog.at_level(logging.WARNING),
        ):
            await finalize_outbound_draft(_record("REJECTED", _held_in_chat()))

        assert any(r.levelno == logging.WARNING and "rec-1" in r.getMessage() for r in caplog.records)


class TestOwnerNotice:
    """The report of an approved reply that did not go out reaches the owner as an error toast, an IM notice and an inbox entry."""

    @pytest.fixture
    def channels(self) -> Iterator[tuple[MagicMock, AsyncMock]]:
        bus, store = MagicMock(), AsyncMock()
        with (
            patch("app.services.approvals.outbound_draft.get_event_bus", return_value=bus),
            patch("app.services.infra.system_notification.SystemNotificationService.create_notification", store),
        ):
            yield bus, store

    @pytest.mark.parametrize("locale", ["en", "zh-CN", "ja"])
    async def test_the_owner_is_told_in_their_own_language(self, locale: str, channels: tuple[MagicMock, AsyncMock]) -> None:
        bus, store = channels
        unsendable = {"draft_content": "hello", "channel": "telegram"}

        with patch("app.core.channel_bridge.locale_provider.resolve_user_locale", AsyncMock(return_value=locale)):
            await finalize_outbound_draft(_record("APPROVED", unsendable))

        body = str(channel_t(locale, "draft_not_sent_body"))
        event = bus.publish.call_args.args[0]
        assert event.event_type is AppEventType.MESSAGE_DEAD_LETTERED
        assert event.data == {"channel": "telegram", "error_reason": body, "delivery_id": ""}
        store.assert_awaited_once_with(
            title=str(channel_t(locale, "draft_not_sent_title")),
            message=body,
            type="error",
            source="outbound_draft",
            meta_data={"approval_id": "rec-1"},
        )
        assert body != "draft_not_sent_body", "the catalog must carry the text in every language"

    async def test_failing_to_notify_never_breaks_the_decision(
        self, channels: tuple[MagicMock, AsyncMock], caplog: pytest.LogCaptureFixture
    ) -> None:
        with (
            patch(
                "app.core.channel_bridge.locale_provider.resolve_user_locale",
                AsyncMock(side_effect=RuntimeError("settings unavailable")),
            ),
            caplog.at_level(logging.WARNING),
        ):
            await finalize_outbound_draft(_record("APPROVED", {"draft_content": "hello", "channel": "telegram"}))

        assert any(r.levelno == logging.WARNING and "rec-1" in r.getMessage() for r in caplog.records)
