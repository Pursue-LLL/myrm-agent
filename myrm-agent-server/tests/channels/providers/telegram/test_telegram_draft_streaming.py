"""TelegramChannel draft preview streaming."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import (
    ChannelStatus,
    OutboundMessage,
)
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestTelegramDraftStreaming:
    """Tests for sendMessageDraft streaming feature."""

    @pytest.mark.asyncio
    async def test_send_placeholder_draft_success(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result is not None
        assert result.startswith("draft:")
        assert ch._draft_available is True
        assert len(ch._active_drafts) == 1

    @pytest.mark.asyncio
    async def test_send_placeholder_draft_unavailable_falls_back(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: unknown method"))
        ch._client.send_message = AsyncMock(return_value={"message_id": 200})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result == "200"
        assert ch._draft_available is False

    @pytest.mark.asyncio
    async def test_send_placeholder_draft_cached_unavailable(self) -> None:
        ch = make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 300})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result == "300"
        ch._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_message_draft_update(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        await ch.edit_message("42", placeholder_id, "A" * 30)
        ch._client.send_message_draft.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_draft_min_chars_suppressed(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock()

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        await ch.edit_message("42", placeholder_id, "Short")
        ch._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_message_draft_id_protection(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock()

        await ch.edit_message("42", "draft:999", "A" * 30)
        ch._client.edit_message_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_edit_placeholder_materializes_draft(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})
        ch._client.send_message = AsyncMock(return_value={"message_id": 500})

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final answer")
        await ch.edit_placeholder_message("42", placeholder_id, msg)

        ch._client.send_message_draft.assert_called_once_with("42", 1, "", disable_notification=True)
        ch._client.send_message.assert_called_once()
        assert draft_key not in ch._active_drafts

    @pytest.mark.asyncio
    async def test_delete_message_clears_draft(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(return_value={"ok": True})

        placeholder_id = "draft:1"
        draft_key = ch._draft_key("42", placeholder_id)
        ch._active_drafts[draft_key] = 1

        await ch.delete_message("42", placeholder_id)
        ch._client.send_message_draft.assert_called_once_with("42", 1, "", disable_notification=True)
        assert draft_key not in ch._active_drafts

    @pytest.mark.asyncio
    async def test_delete_regular_message_not_affected(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.delete_message = AsyncMock(return_value=True)

        await ch.delete_message("42", "100")
        ch._client.delete_message.assert_called_once_with("42", 100)

    @pytest.mark.asyncio
    async def test_stop_clears_active_drafts(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.send_message_draft = AsyncMock()
        ch._poll_task = None

        ch._active_drafts[ch._draft_key("42", "draft:1")] = 1
        ch._active_drafts[ch._draft_key("99", "draft:2")] = 2

        await ch.stop()
        assert len(ch._active_drafts) == 0
        assert ch._client.send_message_draft.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_draft_cleanup_error_tolerated(self) -> None:
        ch = make_channel()
        ch._status = ChannelStatus.RUNNING
        ch._client = MagicMock()
        ch._client.close = AsyncMock()
        ch._client.delete_my_commands = AsyncMock()
        ch._client.send_message_draft = AsyncMock(side_effect=Exception("network"))
        ch._poll_task = None

        ch._active_drafts[ch._draft_key("42", "draft:1")] = 1
        await ch.stop()
        assert len(ch._active_drafts) == 0
        assert ch._status == ChannelStatus.STOPPED

    def test_allocate_draft_id_wraps(self) -> None:
        ch = make_channel()
        ch._draft_counter = 2_147_483_647
        new_id = ch._allocate_draft_id()
        assert new_id == 1

    def test_is_draft_id(self) -> None:
        ch = make_channel()
        assert ch._is_draft_id("draft:123") is True
        assert ch._is_draft_id("100") is False

    @pytest.mark.asyncio
    async def test_try_send_draft_chat_restriction_not_global(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message_draft = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: can't be used in groups"))

        result = await ch._try_send_draft("42", "text")
        assert result is None
        assert ch._draft_available is not False
