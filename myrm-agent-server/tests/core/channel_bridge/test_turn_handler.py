"""Tests for core/channel_bridge/turn_handler.py — ChannelRetryHandler, ChannelUndoHandler, RetryResult / UndoResult."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.turn_management import RetryResult, UndoResult
from app.channels.types import InboundMessage
from app.core.channel_bridge.turn_handler import ChannelRetryHandler, ChannelUndoHandler, RevertMessagesOutcome


def _make_msg(
    channel: str = "test",
    sender_id: str = "u1",
    content: str = "/retry",
    chat_id: str | None = None,
    is_group: bool = False,
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
    )


# ---------------------------------------------------------------------------
# ChannelRetryHandler
# ---------------------------------------------------------------------------


class _FakeSvcResult:
    """Simulates ChatService.retry_last_turn / undo_last_turn result."""

    def __init__(
        self,
        success: bool = True,
        query: str = "hello",
        deleted_count: int = 2,
        deleted_message_ids: list[str] | None = None,
    ) -> None:
        self.success = success
        self.query = query
        self.deleted_count = deleted_count
        self.deleted_message_ids = deleted_message_ids or []


class TestChannelRetryHandler:
    @pytest.mark.asyncio
    async def test_retry_success_with_revert(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelRetryHandler

        handler = ChannelRetryHandler()
        msg = _make_msg()

        mock_chat = MagicMock()
        mock_chat.id = "chat-123"
        svc_result = _FakeSvcResult(
            success=True,
            query="hello",
            deleted_count=2,
            deleted_message_ids=["msg-a", "msg-b"],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="session-key",
            ) as mock_resolve,
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=mock_chat,
            ) as mock_lookup,
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.retry_last_turn",
                new_callable=AsyncMock,
                return_value=svc_result,
            ),
            patch(
                "app.core.channel_bridge.turn_handler._revert_messages",
                new_callable=AsyncMock,
                return_value=RevertMessagesOutcome(reverted_count=3, not_revertible_count=0),
            ) as mock_revert,
        ):
            result = await handler(msg, "user-1")

        assert isinstance(result, RetryResult)
        assert result.success is True
        assert result.query == "hello"
        assert result.deleted_count == 2
        assert result.reverted_count == 3
        mock_resolve.assert_awaited_once_with(msg)
        mock_lookup.assert_awaited_once_with("session-key")
        mock_revert.assert_awaited_once_with("chat-123", ["msg-a", "msg-b"])

    @pytest.mark.asyncio
    async def test_retry_no_chat_returns_failure(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelRetryHandler

        handler = ChannelRetryHandler()
        msg = _make_msg()

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="key",
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await handler(msg, "user-1")

        assert result.success is False
        assert result.reverted_count == 0

    @pytest.mark.asyncio
    async def test_retry_no_deleted_ids_skips_revert(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelRetryHandler

        handler = ChannelRetryHandler()
        msg = _make_msg()

        mock_chat = MagicMock()
        mock_chat.id = "chat-1"
        svc_result = _FakeSvcResult(
            success=True,
            query="hi",
            deleted_count=0,
            deleted_message_ids=[],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="key",
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=mock_chat,
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.retry_last_turn",
                new_callable=AsyncMock,
                return_value=svc_result,
            ),
            patch(
                "app.core.channel_bridge.turn_handler._revert_messages",
                new_callable=AsyncMock,
            ) as mock_revert,
        ):
            result = await handler(msg, "user-1")

        assert result.reverted_count == 0
        mock_revert.assert_not_awaited()


# ---------------------------------------------------------------------------
# ChannelUndoHandler
# ---------------------------------------------------------------------------


class TestChannelUndoHandler:
    @pytest.mark.asyncio
    async def test_undo_success_with_revert(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelUndoHandler

        handler = ChannelUndoHandler()
        msg = _make_msg(content="/undo")

        mock_chat = MagicMock()
        mock_chat.id = "chat-456"
        svc_result = _FakeSvcResult(
            success=True,
            query="",
            deleted_count=3,
            deleted_message_ids=["m1", "m2", "m3"],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="key",
            ) as mock_resolve,
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=mock_chat,
            ) as mock_lookup,
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.undo_last_turn",
                new_callable=AsyncMock,
                return_value=svc_result,
            ) as mock_undo,
            patch(
                "app.core.channel_bridge.turn_handler._revert_messages",
                new_callable=AsyncMock,
                return_value=RevertMessagesOutcome(reverted_count=5, not_revertible_count=0),
            ) as mock_revert,
        ):
            result = await handler(msg, "user-1")

        assert isinstance(result, UndoResult)
        assert result.success is True
        assert result.deleted_count == 3
        assert result.reverted_count == 5
        mock_resolve.assert_awaited_once_with(msg)
        mock_lookup.assert_awaited_once_with("key")
        mock_undo.assert_awaited_once_with("chat-456")
        mock_revert.assert_awaited_once_with("chat-456", ["m1", "m2", "m3"])

    @pytest.mark.asyncio
    async def test_undo_no_chat_returns_failure(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelUndoHandler

        handler = ChannelUndoHandler()
        msg = _make_msg(content="/undo")

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="key",
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            result = await handler(msg, "user-1")

        assert result.success is False
        assert result.reverted_count == 0

    @pytest.mark.asyncio
    async def test_undo_failure_skips_revert(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelUndoHandler

        handler = ChannelUndoHandler()
        msg = _make_msg(content="/undo")

        mock_chat = MagicMock()
        mock_chat.id = "chat-1"
        svc_result = _FakeSvcResult(
            success=False,
            query="",
            deleted_count=0,
            deleted_message_ids=[],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="key",
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=mock_chat,
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.undo_last_turn",
                new_callable=AsyncMock,
                return_value=svc_result,
            ),
            patch(
                "app.core.channel_bridge.turn_handler._revert_messages",
                new_callable=AsyncMock,
            ) as mock_revert,
        ):
            result = await handler(msg, "user-1")

        assert result.success is False
        assert result.reverted_count == 0
        mock_revert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_undo_success_no_files_reverted(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelUndoHandler

        handler = ChannelUndoHandler()
        msg = _make_msg(content="/undo")

        mock_chat = MagicMock()
        mock_chat.id = "chat-1"
        svc_result = _FakeSvcResult(
            success=True,
            query="",
            deleted_count=2,
            deleted_message_ids=["m1", "m2"],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler.resolve_command_session_key",
                new_callable=AsyncMock,
                return_value="key",
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=mock_chat,
            ),
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.undo_last_turn",
                new_callable=AsyncMock,
                return_value=svc_result,
            ),
            patch(
                "app.core.channel_bridge.turn_handler._revert_messages",
                new_callable=AsyncMock,
                return_value=RevertMessagesOutcome(reverted_count=0, not_revertible_count=0),
            ),
        ):
            result = await handler(msg, "user-1")

        assert result.success is True
        assert result.deleted_count == 2
        assert result.reverted_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "service_method"),
    [
        pytest.param(ChannelRetryHandler(), "retry_last_turn", id="retry"),
        pytest.param(ChannelUndoHandler(), "undo_last_turn", id="undo"),
    ],
)
async def test_files_that_could_not_be_reverted_are_reported_to_the_sender(
    handler: ChannelRetryHandler | ChannelUndoHandler, service_method: str
) -> None:
    svc_result = _FakeSvcResult(deleted_message_ids=["m1"])

    with (
        patch("app.core.channel_bridge.turn_handler.resolve_command_session_key", new_callable=AsyncMock, return_value="key"),
        patch(
            "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
            new_callable=AsyncMock,
            return_value=MagicMock(id="chat-1"),
        ),
        patch(
            f"app.core.channel_bridge.turn_handler.ChatService.{service_method}", new_callable=AsyncMock, return_value=svc_result
        ),
        patch(
            "app.core.channel_bridge.turn_handler._revert_messages",
            new_callable=AsyncMock,
            return_value=RevertMessagesOutcome(reverted_count=1, not_revertible_count=2),
        ),
    ):
        result = await handler(_make_msg(), "user-1")

    assert (result.reverted_count, result.files_not_revertible) == (1, 2)


# ---------------------------------------------------------------------------
# RetryResult / UndoResult DTO
# ---------------------------------------------------------------------------


class TestResultDataclasses:
    def test_retry_result_defaults(self) -> None:
        r = RetryResult(success=True)
        assert r.reverted_count == 0
        assert r.deleted_count == 0
        assert r.query == ""

    def test_retry_result_with_reverted(self) -> None:
        r = RetryResult(success=True, query="hi", deleted_count=3, reverted_count=2)
        assert r.reverted_count == 2

    def test_undo_result_defaults(self) -> None:
        r = UndoResult(success=True)
        assert r.reverted_count == 0
        assert r.deleted_count == 0

    def test_undo_result_with_reverted(self) -> None:
        r = UndoResult(success=True, deleted_count=5, reverted_count=3)
        assert r.reverted_count == 3

    def test_result_is_frozen(self) -> None:
        r = RetryResult(success=True)
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]
