"""Forum Topic management and auto-topic routing on TelegramChannel."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import (
    InboundMessage,
)
from tests.channels.providers.telegram.telegram_channel_factories import make_topic_channel


class TestForumTopicChannel:
    """High-level Forum Topic methods on TelegramChannel."""

    @pytest.mark.asyncio
    async def test_create_topic_success(self) -> None:
        ch, client = make_topic_channel()
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 99, "name": "Alice"})
        result = await ch.create_topic("-100123", "Alice")
        assert result == 99
        assert ch._topic_name_cache["-100123:99"] == "Alice"

    @pytest.mark.asyncio
    async def test_create_topic_failure(self) -> None:
        ch, client = make_topic_channel()
        client.create_forum_topic = AsyncMock(side_effect=TelegramApiError(403, "Forbidden: not enough rights"))
        result = await ch.create_topic("-100123", "Alice")
        assert result is None

    @pytest.mark.asyncio
    async def test_create_topic_no_thread_id(self) -> None:
        ch, client = make_topic_channel()
        client.create_forum_topic = AsyncMock(return_value={"name": "Alice"})
        result = await ch.create_topic("-100123", "Alice")
        assert result is None

    @pytest.mark.asyncio
    async def test_rename_topic_success(self) -> None:
        ch, client = make_topic_channel()
        client.edit_forum_topic = AsyncMock(return_value=True)
        assert await ch.rename_topic("-100123", 99, "Bob") is True
        assert ch._topic_name_cache["-100123:99"] == "Bob"

    @pytest.mark.asyncio
    async def test_rename_topic_failure(self) -> None:
        ch, client = make_topic_channel()
        client.edit_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: topic not found"))
        assert await ch.rename_topic("-100123", 99, "Bob") is False

    @pytest.mark.asyncio
    async def test_close_topic_success(self) -> None:
        ch, client = make_topic_channel()
        client.close_forum_topic = AsyncMock(return_value=True)
        assert await ch.close_topic("-100123", 99) is True

    @pytest.mark.asyncio
    async def test_close_topic_failure(self) -> None:
        ch, client = make_topic_channel()
        client.close_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "error"))
        assert await ch.close_topic("-100123", 99) is False

    @pytest.mark.asyncio
    async def test_reopen_topic_success(self) -> None:
        ch, client = make_topic_channel()
        client.reopen_forum_topic = AsyncMock(return_value=True)
        assert await ch.reopen_topic("-100123", 99) is True

    @pytest.mark.asyncio
    async def test_reopen_topic_failure(self) -> None:
        ch, client = make_topic_channel()
        client.reopen_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "error"))
        assert await ch.reopen_topic("-100123", 99) is False


class TestAutoTopicCreation:
    """Test auto_topic mode: auto-create, sync name, and _pre_emit_hook."""

    @pytest.mark.asyncio
    async def test_ensure_topic_disabled(self) -> None:
        ch, client = make_topic_channel(auto_topic=False)
        result = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert result is None

    @pytest.mark.asyncio
    async def test_ensure_topic_creates(self) -> None:
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 55, "name": "Alice"})
        result = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert result == 55
        assert ch._user_topic_map["-100123:42"] == 55

    @pytest.mark.asyncio
    async def test_ensure_topic_reuses_existing(self) -> None:
        """Second call for same user should reuse cached topic, not create new one."""
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 55, "name": "Alice"})
        first = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        second = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert first == second == 55
        assert client.create_forum_topic.call_count == 1

    @pytest.mark.asyncio
    async def test_ensure_topic_concurrent_lock(self) -> None:
        """Concurrent calls for the same user should serialize and only create once."""
        ch, client = make_topic_channel(auto_topic=True)

        async def mock_create(*_a: object, **_kw: object) -> dict[str, object]:
            await asyncio.sleep(0.01)
            return {"message_thread_id": 61, "name": "Alice"}

        client.create_forum_topic = AsyncMock(side_effect=mock_create)
        results = await asyncio.gather(
            ch.ensure_topic_for_user("-100123", "Alice", "42"),
            ch.ensure_topic_for_user("-100123", "Alice", "42"),
        )
        assert all(r == 61 for r in results)
        assert client.create_forum_topic.call_count == 1

    @pytest.mark.asyncio
    async def test_sync_topic_name_no_change(self) -> None:
        ch, client = make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Alice"
        client.edit_forum_topic = AsyncMock(return_value=True)
        await ch.sync_topic_name("-100123", 99, "Alice")
        client.edit_forum_topic.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_topic_name_changed(self) -> None:
        ch, client = make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Alice"
        client.edit_forum_topic = AsyncMock(return_value=True)
        await ch.sync_topic_name("-100123", 99, "Alice Smith")
        client.edit_forum_topic.assert_called_once_with("-100123", 99, name="Alice Smith")

    @pytest.mark.asyncio
    async def test_sync_topic_name_disabled(self) -> None:
        ch, client = make_topic_channel(auto_topic=False)
        client.edit_forum_topic = AsyncMock()
        await ch.sync_topic_name("-100123", 99, "Alice")
        client.edit_forum_topic.assert_not_called()

    @pytest.mark.asyncio
    async def test_pre_emit_hook_forum_no_thread(self) -> None:
        """Forum message without thread_id should trigger auto-create."""
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 77, "name": "Bob"})
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            sender_name="Bob",
            is_group=True,
            thread_id=None,
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is not None
        assert result.thread_id == "77"
        client.create_forum_topic.assert_called_once()

    @pytest.mark.asyncio
    async def test_pre_emit_hook_forum_with_thread(self) -> None:
        """Forum message with existing thread_id should populate user_topic_map and trigger name sync."""
        ch, client = make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Old Name"
        client.edit_forum_topic = AsyncMock(return_value=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            sender_name="New Name",
            is_group=True,
            thread_id="99",
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg
        assert ch._user_topic_map["-100123:42"] == 99
        await asyncio.sleep(0.05)
        client.edit_forum_topic.assert_called_once_with("-100123", 99, name="New Name")

    @pytest.mark.asyncio
    async def test_pre_emit_hook_non_forum(self) -> None:
        """Non-forum messages pass through unchanged."""
        ch, client = make_topic_channel(auto_topic=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            is_group=True,
            metadata={"is_forum": False},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_pre_emit_hook_disabled(self) -> None:
        """Auto-topic disabled passes through unchanged."""
        ch, client = make_topic_channel(auto_topic=False)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hello",
            chat_id="-100123",
            is_group=True,
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg


class TestFromCredentialsAutoTopic:
    """Test that from_credentials correctly parses auto_topic credential."""

    def test_auto_topic_false_by_default(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok"})
        assert ch._auto_topic is False

    def test_auto_topic_true(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok", "auto_topic": "true"})
        assert ch._auto_topic is True

    def test_auto_topic_yes(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok", "auto_topic": "yes"})
        assert ch._auto_topic is True

    def test_auto_topic_1(self) -> None:
        ch = TelegramChannel.from_credentials({"token": "test:tok", "auto_topic": "1"})
        assert ch._auto_topic is True


class TestAutoTopicEdgeCases:
    """Edge cases for auto-topic: failures, empty fields, DM, system messages."""

    @pytest.mark.asyncio
    async def test_ensure_topic_create_fails(self) -> None:
        """ensure_topic_for_user returns None when create_topic fails."""
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(side_effect=TelegramApiError(403, "Bot is not admin"))
        result = await ch.ensure_topic_for_user("-100123", "Alice", "42")
        assert result is None
        assert "-100123:42" not in ch._user_topic_map

    @pytest.mark.asyncio
    async def test_apply_auto_topic_dm_message(self) -> None:
        """DM (non-group) messages pass through even if auto_topic is on."""
        ch, client = make_topic_channel(auto_topic=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="hi",
            chat_id="42",
            is_group=False,
            metadata={"is_forum": False},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_apply_auto_topic_no_sender_id(self) -> None:
        """Forum message without sender_id passes through unchanged."""
        ch, client = make_topic_channel(auto_topic=True)
        msg = InboundMessage(
            channel="telegram",
            sender_id="",
            content="system event",
            chat_id="-100123",
            is_group=True,
            thread_id=None,
            metadata={"is_forum": True},
        )
        result = await ch._pre_emit_hook(msg)
        assert result is msg

    @pytest.mark.asyncio
    async def test_sync_topic_name_rename_fails(self) -> None:
        """sync_topic_name handles rename failure gracefully."""
        ch, client = make_topic_channel(auto_topic=True)
        ch._topic_name_cache["-100123:99"] = "Old"
        client.edit_forum_topic = AsyncMock(side_effect=TelegramApiError(400, "Topic not found"))
        await ch.sync_topic_name("-100123", 99, "New Name")
        assert ch._topic_name_cache["-100123:99"] == "Old"

    @pytest.mark.asyncio
    async def test_sync_topic_name_no_cache(self) -> None:
        """sync_topic_name calls rename when no cache entry exists."""
        ch, client = make_topic_channel(auto_topic=True)
        client.edit_forum_topic = AsyncMock(return_value=True)
        await ch.sync_topic_name("-100123", 99, "Alice")
        client.edit_forum_topic.assert_called_once_with("-100123", 99, name="Alice")
        assert ch._topic_name_cache["-100123:99"] == "Alice"

    @pytest.mark.asyncio
    async def test_create_topic_with_icon(self) -> None:
        """create_topic passes icon parameters to API."""
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 88, "name": "Test"})
        result = await ch.create_topic("-100123", "Test", icon_color=0x6FB9F0, icon_custom_emoji_id="5368324170671202286")
        assert result == 88
        client.create_forum_topic.assert_called_once_with(
            "-100123",
            "Test",
            icon_color=0x6FB9F0,
            icon_custom_emoji_id="5368324170671202286",
        )

    @pytest.mark.asyncio
    async def test_ensure_topic_empty_sender_name(self) -> None:
        """Fallback to 'User {id}' when sender_name is empty."""
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 66, "name": "User 42"})
        result = await ch.ensure_topic_for_user("-100123", "", "42")
        assert result == 66
        client.create_forum_topic.assert_called_once_with(
            "-100123",
            "User 42",
            icon_color=None,
            icon_custom_emoji_id=None,
        )

    @pytest.mark.asyncio
    async def test_pre_emit_hook_preserves_all_fields(self) -> None:
        """When auto-create triggers, all original message fields are preserved."""
        ch, client = make_topic_channel(auto_topic=True)
        client.create_forum_topic = AsyncMock(return_value={"message_thread_id": 99, "name": "Alice"})
        msg = InboundMessage(
            channel="telegram",
            sender_id="42",
            content="test content",
            chat_id="-100123",
            sender_name="Alice",
            is_group=True,
            is_bot=False,
            mentioned=True,
            reply_to_id="5",
            thread_id=None,
            metadata={"is_forum": True, "chat_type": "supergroup"},
            message_id="12345",
        )
        result = await ch._pre_emit_hook(msg)
        assert result is not None
        assert result.thread_id == "99"
        assert result.sender_id == "42"
        assert result.content == "test content"
        assert result.chat_id == "-100123"
        assert result.sender_name == "Alice"
        assert result.is_group is True
        assert result.is_bot is False
        assert result.mentioned is True
        assert result.reply_to_id == "5"
        assert result.metadata == {"is_forum": True, "chat_type": "supergroup"}
        assert result.message_id == "12345"
        assert result.channel == "telegram"

    @pytest.mark.asyncio
    async def test_user_topic_map_different_chats(self) -> None:
        """Different chat_ids create separate topics for the same user."""
        ch, client = make_topic_channel(auto_topic=True)
        call_count = 0

        async def mock_create(chat_id: str, name: str, **_kw: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {"message_thread_id": 100 + call_count, "name": name}

        client.create_forum_topic = AsyncMock(side_effect=mock_create)
        r1 = await ch.ensure_topic_for_user("-100A", "Alice", "42")
        r2 = await ch.ensure_topic_for_user("-100B", "Alice", "42")
        assert r1 != r2
        assert client.create_forum_topic.call_count == 2
