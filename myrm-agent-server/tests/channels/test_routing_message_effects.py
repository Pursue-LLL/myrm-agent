"""MessageEffects tests — typing, reactions, placeholders, replies."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.message_effects import (
    MessageEffects,
    friendly_error_message,
)
from app.channels.types import InboundMessage, OutboundMessage


def _make_bus(channel_mock: MagicMock | None = None) -> MagicMock:
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=channel_mock)
    bus.publish_outbound = AsyncMock()
    return bus


def _make_channel_mock() -> MagicMock:
    ch = MagicMock()
    ch.start_typing = AsyncMock()
    ch.stop_typing = AsyncMock()
    ch.send_placeholder = AsyncMock(return_value="ph-1")
    ch.edit_placeholder_message = AsyncMock()
    ch.edit_message = AsyncMock()
    ch.delete_message = AsyncMock()
    ch.react_to_message = AsyncMock()
    ch.retry_config = None
    ch.should_retry = MagicMock(return_value=False)
    ch.extract_retry_after = MagicMock(return_value=None)
    ch.capabilities = MagicMock()
    ch.capabilities.max_text_length = 4096
    return ch


def _inbound(
    content: str = "hi",
    *,
    channel: str = "test",
    sender_id: str = "u1",
    chat_id: str = "",
    is_group: bool = False,
    user_id: str = "",
    metadata: dict[str, object] | None = None,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        user_id=user_id,
        metadata=metadata or {},
    )


class TestSetTyping:
    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_typing("test", "chat-1", composing=True)
        ch.start_typing.assert_called_once_with("chat-1")

    @pytest.mark.asyncio
    async def test_stop_typing(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_typing("test", "chat-1", composing=False)
        ch.stop_typing.assert_called_once_with("chat-1")

    @pytest.mark.asyncio
    async def test_no_channel_noop(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        await fx.set_typing("test", "chat-1", composing=True)

    @pytest.mark.asyncio
    async def test_error_silenced(self) -> None:
        ch = _make_channel_mock()
        ch.start_typing = AsyncMock(side_effect=Exception("fail"))
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_typing("test", "chat-1", composing=True)


class TestSendPlaceholder:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        with patch(
            "app.channels.routing.message_effects.send_with_retry",
            new_callable=AsyncMock,
            return_value="ph-1",
        ):
            result = await fx.send_placeholder("test", "chat-1")
        assert result == "ph-1"

    @pytest.mark.asyncio
    async def test_no_channel(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        result = await fx.send_placeholder("test", "chat-1")
        assert result is None

    @pytest.mark.asyncio
    async def test_uses_localized_thinking_text(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        msg = InboundMessage(
            channel="test",
            sender_id="u1",
            content="hi",
            metadata={"locale": "zh-CN"},
        )
        with patch(
            "app.channels.routing.message_effects.send_with_retry",
            new_callable=AsyncMock,
            return_value="ph-1",
        ) as send_mock:
            result = await fx.send_placeholder("test", "chat-1", msg=msg)
        assert result == "ph-1"
        assert "思考中" in send_mock.call_args[0][2]

    @pytest.mark.asyncio
    async def test_error_returns_none(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        with patch(
            "app.channels.routing.message_effects.send_with_retry",
            new_callable=AsyncMock,
            side_effect=Exception("fail"),
        ):
            result = await fx.send_placeholder("test", "chat-1")
        assert result is None


class TestEditPlaceholder:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        result = OutboundMessage(
            channel="test", recipient_id="r1", content="response", user_id="u1"
        )
        with (
            patch(
                "app.channels.routing.message_effects.send_with_retry",
                new_callable=AsyncMock,
            ),
            patch(
                "app.channels.routing.message_effects.downgrade_components",
                return_value=result,
            ),
        ):
            await fx.edit_placeholder("test", "chat-1", "ph-1", result)

    @pytest.mark.asyncio
    async def test_no_channel_publishes_normally(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        result = OutboundMessage(
            channel="test", recipient_id="r1", content="response", user_id="u1"
        )
        await fx.edit_placeholder("test", "chat-1", "ph-1", result)
        bus.publish_outbound.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_failure_publishes_normally(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        result = OutboundMessage(
            channel="test", recipient_id="r1", content="response", user_id="u1"
        )
        with (
            patch(
                "app.channels.routing.message_effects.send_with_retry",
                new_callable=AsyncMock,
                side_effect=Exception("edit fail"),
            ),
            patch(
                "app.channels.routing.message_effects.downgrade_components",
                return_value=result,
            ),
        ):
            await fx.edit_placeholder("test", "chat-1", "ph-1", result)
        bus.publish_outbound.assert_called()

    @pytest.mark.asyncio
    async def test_publishes_extra_chunks(self) -> None:
        ch = _make_channel_mock()
        ch.capabilities.max_text_length = 8
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        result = OutboundMessage(
            channel="test",
            recipient_id="r1",
            content="12345678901234567890",
            user_id="u1",
        )
        with (
            patch(
                "app.channels.routing.message_effects.send_with_retry",
                new_callable=AsyncMock,
            ),
            patch(
                "app.channels.routing.message_effects.downgrade_components",
                return_value=result,
            ),
        ):
            await fx.edit_placeholder("test", "chat-1", "ph-1", result)
        assert bus.publish_outbound.await_count >= 1


class TestCleanupPlaceholder:
    @pytest.mark.asyncio
    async def test_edit_success(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.cleanup_placeholder("test", "chat-1", "ph-1", "Error occurred")
        ch.edit_message.assert_called_once_with("chat-1", "ph-1", "Error occurred")

    @pytest.mark.asyncio
    async def test_edit_fails_deletes(self) -> None:
        ch = _make_channel_mock()
        ch.edit_message = AsyncMock(side_effect=Exception("edit fail"))
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.cleanup_placeholder("test", "chat-1", "ph-1", "Error")
        ch.delete_message.assert_called_once_with("chat-1", "ph-1")

    @pytest.mark.asyncio
    async def test_both_fail_silenced(self) -> None:
        ch = _make_channel_mock()
        ch.edit_message = AsyncMock(side_effect=Exception("edit fail"))
        ch.delete_message = AsyncMock(side_effect=Exception("delete fail"))
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.cleanup_placeholder("test", "chat-1", "ph-1", "Error")

    @pytest.mark.asyncio
    async def test_no_channel_noop(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        await fx.cleanup_placeholder("test", "chat-1", "ph-1", "Error")


class TestEditProgress:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        result = await fx.edit_progress("test", "chat-1", "ph-1", "Processing...")
        assert result is True

    @pytest.mark.asyncio
    async def test_no_placeholder_id(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        result = await fx.edit_progress("test", "chat-1", None, "Processing...")
        assert result is False

    @pytest.mark.asyncio
    async def test_no_channel(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        result = await fx.edit_progress("test", "chat-1", "ph-1", "Processing...")
        assert result is False

    @pytest.mark.asyncio
    async def test_error_returns_false(self) -> None:
        ch = _make_channel_mock()
        ch.edit_message = AsyncMock(side_effect=Exception("fail"))
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        result = await fx.edit_progress("test", "chat-1", "ph-1", "Processing...")
        assert result is False


class TestSetReaction:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_reaction("test", "chat-1", "msg-1", "\U0001f44d")
        ch.react_to_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_non_string_message_id(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_reaction("test", "chat-1", 12345, "\U0001f44d")
        ch.react_to_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_message_id(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_reaction("test", "chat-1", "", "\U0001f44d")
        ch.react_to_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_channel(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        await fx.set_reaction("test", "chat-1", "msg-1", "\U0001f44d")

    @pytest.mark.asyncio
    async def test_error_silenced(self) -> None:
        ch = _make_channel_mock()
        ch.react_to_message = AsyncMock(side_effect=Exception("fail"))
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.set_reaction("test", "chat-1", "msg-1", "\U0001f44d")


class TestTypingKeepalive:
    def test_no_channel_noop(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        fx.start_typing_keepalive("test", "chat-1")

    def test_zero_interval_noop(self) -> None:
        ch = _make_channel_mock()
        ch.capabilities.typing_keepalive_interval = 0
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        fx.start_typing_keepalive("test", "chat-1")

    @pytest.mark.asyncio
    async def test_duplicate_start_ignored(self) -> None:
        ch = _make_channel_mock()
        ch.capabilities.typing_keepalive_interval = 60
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        fx.start_typing_keepalive("test", "chat-1")
        fx.start_typing_keepalive("test", "chat-1")
        await fx.stop_typing_keepalive("test", "chat-1")

    @pytest.mark.asyncio
    async def test_start_stop_keepalive(self) -> None:
        ch = _make_channel_mock()
        ch.capabilities.typing_keepalive_interval = 0.02
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        fx.start_typing_keepalive("test", "chat-1")
        await asyncio.sleep(0.05)
        await fx.stop_typing_keepalive("test", "chat-1")

    @pytest.mark.asyncio
    async def test_stop_without_task_noop(self) -> None:
        bus = _make_bus(_make_channel_mock())
        fx = MessageEffects(bus)
        await fx.stop_typing_keepalive("test", "chat-1")

    @pytest.mark.asyncio
    async def test_keepalive_tick_error_silenced(self) -> None:
        ch = _make_channel_mock()
        ch.capabilities.typing_keepalive_interval = 0.02
        ch.start_typing = AsyncMock(side_effect=Exception("tick fail"))
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        fx.start_typing_keepalive("test", "chat-1")
        await asyncio.sleep(0.05)
        await fx.stop_typing_keepalive("test", "chat-1")


class TestAckAndCompletionReaction:
    @pytest.mark.asyncio
    async def test_ack_reaction(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.ack_reaction("test", "chat-1", "msg-1", "\U0001f44d")
        ch.react_to_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_ack_reaction_no_message_id(self) -> None:
        bus = _make_bus(_make_channel_mock())
        fx = MessageEffects(bus)
        await fx.ack_reaction("test", "chat-1", None, "\U0001f44d")

    @pytest.mark.asyncio
    async def test_completion_reaction_success_with_ack(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.completion_reaction(
            "test",
            "chat-1",
            "msg-1",
            success=True,
            success_emoji="\u2705",
            failure_emoji="\u274c",
            had_ack=True,
        )
        assert ch.react_to_message.await_count == 2

    @pytest.mark.asyncio
    async def test_completion_reaction_failure(self) -> None:
        ch = _make_channel_mock()
        bus = _make_bus(ch)
        fx = MessageEffects(bus)
        await fx.completion_reaction(
            "test",
            "chat-1",
            "msg-1",
            success=False,
            success_emoji="\u2705",
            failure_emoji="\u274c",
            had_ack=False,
        )
        ch.react_to_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_completion_reaction_no_message_id(self) -> None:
        bus = _make_bus(_make_channel_mock())
        fx = MessageEffects(bus)
        await fx.completion_reaction(
            "test", "chat-1", None, success=True, success_emoji="\u2705"
        )


class TestSendMuteReply:
    @pytest.mark.asyncio
    async def test_dm_mute_reply(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1", is_group=False)
        await fx.send_mute_reply(msg)
        out = bus.publish_outbound.call_args[0][0]
        assert "muted" in out.content.lower()
        assert out.recipient_id == "u1"

    @pytest.mark.asyncio
    async def test_group_mute_reply(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound(
            "hi",
            sender_id="u1",
            chat_id="grp-1",
            is_group=True,
            metadata={"message_id": "99"},
        )
        await fx.send_mute_reply(msg)
        out = bus.publish_outbound.call_args[0][0]
        assert out.recipient_id == "grp-1"
        assert out.reply_to_id == "99"


class TestSendErrorReply:
    @pytest.mark.asyncio
    async def test_dm_reply_with_preformatted_string(self) -> None:
        """Pre-formatted friendly strings are passed through directly."""
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1", is_group=False)
        friendly = " Something went wrong. [ref: abc12345]"
        await fx.send_error_reply(msg, friendly)
        bus.publish_outbound.assert_called_once()
        out = bus.publish_outbound.call_args[0][0]
        assert out.recipient_id == "u1"
        assert out.content == friendly

    @pytest.mark.asyncio
    async def test_dm_reply_with_exception(self) -> None:
        """Exception errors are classified and produce friendly message."""
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1", is_group=False)
        exc = RuntimeError("internal traceback details")
        await fx.send_error_reply(msg, exc)
        out = bus.publish_outbound.call_args[0][0]
        assert "internal traceback" not in out.content
        assert "[ref:" in out.content

    @pytest.mark.asyncio
    async def test_group_reply_with_exception(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound(
            "hi",
            sender_id="u1",
            chat_id="grp-1",
            is_group=True,
            metadata={"message_id": "123"},
        )
        await fx.send_error_reply(msg, RuntimeError("internal db error"))
        out = bus.publish_outbound.call_args[0][0]
        assert out.recipient_id == "grp-1"
        assert out.reply_to_id == "123"
        assert "internal db error" not in out.content
        assert "[ref:" in out.content

    @pytest.mark.asyncio
    async def test_rate_limit_classified(self) -> None:
        """Rate limit errors produce the specific friendly message."""
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        exc = Exception("Rate limit exceeded: 429 too many requests")
        await fx.send_error_reply(msg, exc)
        out = bus.publish_outbound.call_args[0][0]
        assert "rate limit" in out.content.lower()

    @pytest.mark.asyncio
    async def test_overloaded_classified(self) -> None:
        """Overloaded errors produce a distinct friendly message."""
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        exc = Exception("overloaded_error: server capacity exceeded")
        await fx.send_error_reply(msg, exc)
        out = bus.publish_outbound.call_args[0][0]
        assert "overloaded" in out.content.lower()

    @pytest.mark.asyncio
    async def test_timeout_classified(self) -> None:
        """Timeout errors produce the specific friendly message."""
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        exc = Exception("Connection timeout after 300s")
        await fx.send_error_reply(msg, exc)
        out = bus.publish_outbound.call_args[0][0]
        assert "timed out" in out.content.lower()


class TestSendPendingReply:
    @pytest.mark.asyncio
    async def test_sends_pending_message(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        await fx.send_pending_reply(msg)
        bus.publish_outbound.assert_called_once()
        out = bus.publish_outbound.call_args[0][0]
        assert "pending" in out.content.lower()


class TestSendPairingRequestReply:
    @pytest.mark.asyncio
    async def test_sends_pairing_request(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        await fx.send_pairing_request_reply(msg)
        bus.publish_outbound.assert_called_once()
        out = bus.publish_outbound.call_args[0][0]
        assert "request" in out.content.lower()


class TestWaitForEditGap:
    @pytest.mark.asyncio
    async def test_no_wait_when_zero(self) -> None:
        await MessageEffects.wait_for_edit_gap(0)

    @pytest.mark.asyncio
    async def test_no_wait_when_negative(self) -> None:
        await MessageEffects.wait_for_edit_gap(-1.0)

    @pytest.mark.asyncio
    async def test_waits_when_recent(self) -> None:
        import time

        now = time.monotonic()
        await MessageEffects.wait_for_edit_gap(now, min_interval=0.01)


class TestFriendlyErrorMessage:
    """Tests for the friendly_error_message() public function."""

    def test_timeout_zh(self) -> None:
        msg_in = InboundMessage(
            channel="test",
            sender_id="u1",
            content="hi",
            metadata={"locale": "zh-CN"},
        )
        msg, _ = friendly_error_message(Exception("connection timeout"), msg=msg_in)
        assert "超时" in msg

    def test_rate_limit(self) -> None:
        msg, ref_id = friendly_error_message(
            Exception("429 too many requests rate limit")
        )
        assert "rate limit" in msg.lower()
        assert ref_id in msg
        assert len(ref_id) == 8

    def test_overloaded(self) -> None:
        msg, ref_id = friendly_error_message(Exception("overloaded_error"))
        assert "overloaded" in msg.lower()
        assert ref_id in msg
        assert len(ref_id) == 8

    def test_billing(self) -> None:
        msg, _ = friendly_error_message(Exception("insufficient balance"))
        assert "configuration issue" in msg.lower()

    def test_auth(self) -> None:
        msg, _ = friendly_error_message(Exception("invalid api key"))
        assert "configuration issue" in msg.lower()

    def test_timeout(self) -> None:
        msg, _ = friendly_error_message(Exception("connection timeout"))
        assert "timed out" in msg.lower()

    def test_context_overflow(self) -> None:
        msg, _ = friendly_error_message(Exception("context_length_exceeded"))
        assert "too long" in msg.lower()

    def test_unknown(self) -> None:
        msg, ref_id = friendly_error_message(RuntimeError("some random error"))
        assert "Something went wrong" in msg
        assert f"[ref: {ref_id}]" in msg

    def test_ref_id_unique(self) -> None:
        _, r1 = friendly_error_message(Exception("err1"))
        _, r2 = friendly_error_message(Exception("err2"))
        assert r1 != r2

    def test_no_internal_leak(self) -> None:
        """Friendly messages never contain the raw exception text."""
        raw = "INTERNAL_SECRET_PATH=/opt/app/secrets.json"
        msg, _ = friendly_error_message(Exception(raw))
        assert raw not in msg
        assert "SECRET" not in msg


class TestSendErrorReplyLogging:
    """Verify that send_error_reply logs raw errors at ERROR level."""

    @pytest.mark.asyncio
    async def test_exception_logs_error_with_exc_info(self) -> None:
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        exc = RuntimeError("detailed internal failure")
        with patch(
            "app.channels.routing.message_effects.logger"
        ) as mock_logger:
            await fx.send_error_reply(msg, exc)
            mock_logger.error.assert_called_once()
            call_args = mock_logger.error.call_args
            assert "ref:" in call_args[0][0]  # format string contains ref
            assert call_args[1].get("exc_info") is exc  # full traceback logged

    @pytest.mark.asyncio
    async def test_string_path_does_not_log(self) -> None:
        """Pre-formatted strings skip logging (router already logged)."""
        bus = _make_bus(None)
        fx = MessageEffects(bus)
        msg = _inbound("hi", sender_id="u1")
        with patch(
            "app.channels.routing.message_effects.logger"
        ) as mock_logger:
            await fx.send_error_reply(msg, " Already friendly [ref: abc12345]")
            mock_logger.error.assert_not_called()
