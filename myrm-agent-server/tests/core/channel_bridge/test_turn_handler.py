"""Tests for core/channel_bridge/turn_handler.py — ChannelRetryHandler, ChannelUndoHandler, _revert_messages."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.turn_management import RetryResult, UndoResult
from app.channels.types import InboundMessage


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
# _revert_messages
# ---------------------------------------------------------------------------


class TestRevertMessages:
    @pytest.mark.asyncio
    async def test_empty_ids_returns_zero(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        result = await _revert_messages("session-1", [])
        assert result == 0

    @pytest.mark.asyncio
    async def test_counts_reverted_files(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result_1 = _FakeRevertResult(reverted_files=["a.py", "b.py"], warnings=[])
        mock_result_2 = _FakeRevertResult(reverted_files=["c.py"], warnings=[])

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            side_effect=[mock_result_1, mock_result_2],
        ), patch(
            "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
            new_callable=AsyncMock,
        ) as mock_cleanup:
            total = await _revert_messages("session-1", ["msg-1", "msg-2"])

        assert total == 3
        assert mock_cleanup.await_count == 2
        mock_cleanup.assert_any_await("session-1", "msg-1")
        mock_cleanup.assert_any_await("session-1", "msg-2")

    @pytest.mark.asyncio
    async def test_skips_cleanup_when_nothing_reverted(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(reverted_files=[], warnings=["no snapshots"])

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            return_value=mock_result,
        ), patch(
            "app.services.files.revert_hydrate.cleanup_persisted_snapshots",
            new_callable=AsyncMock,
        ) as mock_cleanup:
            total = await _revert_messages("session-1", ["msg-1"])

        assert total == 0
        mock_cleanup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_logs_warnings(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        mock_result = _FakeRevertResult(
            reverted_files=["a.py"],
            warnings=["snapshot missing for b.py"],
        )

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_revert:
            total = await _revert_messages("s1", ["m1"])

        assert total == 1
        mock_revert.assert_awaited_once_with("s1", "m1")

    @pytest.mark.asyncio
    async def test_exception_on_one_message_continues(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        @dataclass
        class _FakeRevertResult:
            reverted_files: list[str]
            warnings: list[str]

        ok_result = _FakeRevertResult(reverted_files=["a.py"], warnings=[])

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            side_effect=[RuntimeError("disk full"), ok_result],
        ):
            total = await _revert_messages("s1", ["m-bad", "m-ok"])

        assert total == 1

    @pytest.mark.asyncio
    async def test_all_fail_returns_zero(self) -> None:
        from app.core.channel_bridge.turn_handler import _revert_messages

        with patch(
            "app.core.channel_bridge.turn_handler.RevertService.revert_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("nope"),
        ):
            total = await _revert_messages("s1", ["m1", "m2"])

        assert total == 0


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
            success=True, query="hello", deleted_count=2,
            deleted_message_ids=["msg-a", "msg-b"],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("session-key", None),
            ),
            patch(
                "app.core.channel_bridge.turn_handler.get_session",
            ) as mock_get_session,
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
                return_value=3,
            ) as mock_revert,
        ):
            mock_ctx = AsyncMock()
            mock_get_session.return_value = mock_ctx

            result = await handler(msg, "user-1")

        assert isinstance(result, RetryResult)
        assert result.success is True
        assert result.query == "hello"
        assert result.deleted_count == 2
        assert result.reverted_count == 3
        mock_revert.assert_awaited_once_with("chat-123", ["msg-a", "msg-b"])

    @pytest.mark.asyncio
    async def test_retry_no_chat_returns_failure(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelRetryHandler

        handler = ChannelRetryHandler()
        msg = _make_msg()

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("key", None),
            ),
            patch("app.core.channel_bridge.turn_handler.get_session") as mock_gs,
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_gs.return_value = AsyncMock()
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
            success=True, query="hi", deleted_count=0,
            deleted_message_ids=[],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("key", None),
            ),
            patch("app.core.channel_bridge.turn_handler.get_session") as mock_gs,
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
            mock_gs.return_value = AsyncMock()
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
            success=True, query="", deleted_count=3,
            deleted_message_ids=["m1", "m2", "m3"],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("key", None),
            ),
            patch("app.core.channel_bridge.turn_handler.get_session") as mock_gs,
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
                return_value=5,
            ) as mock_revert,
        ):
            mock_gs.return_value = AsyncMock()
            result = await handler(msg, "user-1")

        assert isinstance(result, UndoResult)
        assert result.success is True
        assert result.deleted_count == 3
        assert result.reverted_count == 5
        mock_revert.assert_awaited_once_with("chat-456", ["m1", "m2", "m3"])

    @pytest.mark.asyncio
    async def test_undo_no_chat_returns_failure(self) -> None:
        from app.core.channel_bridge.turn_handler import ChannelUndoHandler

        handler = ChannelUndoHandler()
        msg = _make_msg(content="/undo")

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("key", None),
            ),
            patch("app.core.channel_bridge.turn_handler.get_session") as mock_gs,
            patch(
                "app.core.channel_bridge.turn_handler.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            mock_gs.return_value = AsyncMock()
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
            success=False, query="", deleted_count=0,
            deleted_message_ids=[],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("key", None),
            ),
            patch("app.core.channel_bridge.turn_handler.get_session") as mock_gs,
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
            mock_gs.return_value = AsyncMock()
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
            success=True, query="", deleted_count=2,
            deleted_message_ids=["m1", "m2"],
        )

        with (
            patch(
                "app.core.channel_bridge.turn_handler._resolve_session_with_agent",
                new_callable=AsyncMock,
                return_value=("key", None),
            ),
            patch("app.core.channel_bridge.turn_handler.get_session") as mock_gs,
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
                return_value=0,
            ),
        ):
            mock_gs.return_value = AsyncMock()
            result = await handler(msg, "user-1")

        assert result.success is True
        assert result.deleted_count == 2
        assert result.reverted_count == 0


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
