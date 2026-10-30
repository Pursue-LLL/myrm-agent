"""TelegramChannel outbound: send, edit, placeholders, media, pin and their parse-error fallbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import (
    ChannelStatus,
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
)
from tests.channels.providers.telegram.telegram_channel_factories import make_channel


class TestTelegramChannelOutbound:
    @pytest.mark.asyncio
    async def test_send_text(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 100})

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Hello!")
        result = await ch.send(msg)
        assert result is not None
        ch._client.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_send_empty_recipient_raises_permanent_error(self) -> None:
        ch = make_channel()
        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="", content="Hello!")
        with pytest.raises(ChannelSendError) as exc_info:
            await ch.send(msg)
        assert exc_info.value.retriable is False

    @pytest.mark.asyncio
    async def test_start_typing(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_chat_action = AsyncMock()

        await ch.start_typing("42")
        ch._client.send_chat_action.assert_called_once_with("42", "typing")

    @pytest.mark.asyncio
    async def test_send_placeholder(self) -> None:
        ch = make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 200})

        result = await ch.send_placeholder("42", "Thinking...")
        assert result == "200"

    @pytest.mark.asyncio
    async def test_edit_message(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(return_value={"message_id": 100})

        await ch.edit_message("42", "100", "Updated text")
        ch._client.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_edit_message_not_modified(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message is not modified"))

        await ch.edit_message("42", "100", "Same text")

    @pytest.mark.asyncio
    async def test_edit_message_parse_error_fallback(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 100},
            ]
        )

        await ch.edit_message("42", "100", "**bold**")
        assert ch._client.edit_message_text.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_message(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.delete_message = AsyncMock(return_value=True)

        await ch.delete_message("42", "100")
        ch._client.delete_message.assert_called_once_with("42", 100)

    @pytest.mark.asyncio
    async def test_react_to_message(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.set_message_reaction = AsyncMock()

        await ch.react_to_message("42", "100", "")
        ch._client.set_message_reaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_webhook_update(self) -> None:
        ch = make_channel()
        received: list[InboundMessage] = []

        async def handler(msg: InboundMessage) -> None:
            received.append(msg)

        ch.set_inbound_handler(handler)
        ch._status = ChannelStatus.RUNNING

        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "from": {"id": 42},
                "chat": {"id": 42, "type": "private"},
                "text": "webhook hello",
            },
        }
        await ch.handle_webhook_update(update)
        assert len(received) == 1
        assert received[0].content == "webhook hello"

    @pytest.mark.asyncio
    async def test_edit_placeholder_message(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(return_value={"message_id": 100})

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final answer")
        await ch.edit_placeholder_message("42", "100", msg)
        ch._client.edit_message_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_pin_message(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.pin_chat_message = AsyncMock()

        await ch.pin_message("42", "100")
        ch._client.pin_chat_message.assert_called_once()


class TestTelegramSendMedia:
    @pytest.mark.asyncio
    async def test_send_with_media_attachment(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(return_value={"message_id": 100})

        with patch(
            "app.channels.providers.telegram.outbound.send_media_attachment",
            new_callable=AsyncMock,
        ) as mock_send_media:
            msg = OutboundMessage(
                channel="telegram",
                user_id="u1",
                recipient_id="42",
                content="Check this out",
                media=(MediaAttachment(media_type=MediaType.IMAGE, url="https://img.example.com/photo.jpg"),),
            )
            result = await ch.send(msg)
            mock_send_media.assert_called_once()
            assert result == "100"

    @pytest.mark.asyncio
    async def test_send_html_parse_error_fallback(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 200},
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="**bold**")
        result = await ch.send(msg)
        assert result == "200"
        assert ch._client.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_html_parse_error_raises_other(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: chat not found"))

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="hello")
        with pytest.raises(TelegramApiError, match="chat not found"):
            await ch.send(msg)


class TestTelegramSendPlaceholderParseError:
    @pytest.mark.asyncio
    async def test_placeholder_parse_error_fallback(self) -> None:
        ch = make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 300},
            ]
        )

        result = await ch.send_placeholder("42", "**bold placeholder**")
        assert result == "300"
        assert ch._client.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_placeholder_other_error_returns_none(self) -> None:
        ch = make_channel()
        ch._draft_available = False
        ch._client = MagicMock()
        ch._client.send_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: chat not found"))

        result = await ch.send_placeholder("42", "text")
        assert result is None


class TestTelegramEditPlaceholderParseError:
    @pytest.mark.asyncio
    async def test_edit_placeholder_parse_error_fallback(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                {"message_id": 100},
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final")
        await ch.edit_placeholder_message("42", "100", msg)
        assert ch._client.edit_message_text.call_count == 2

    @pytest.mark.asyncio
    async def test_edit_placeholder_not_modified(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message is not modified"))

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Same")
        await ch.edit_placeholder_message("42", "100", msg)

    @pytest.mark.asyncio
    async def test_edit_placeholder_parse_error_inner_not_modified(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message is not modified"),
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Same")
        await ch.edit_placeholder_message("42", "100", msg)

    @pytest.mark.asyncio
    async def test_edit_placeholder_parse_error_inner_other(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message to edit not found"),
            ]
        )

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="text")
        with pytest.raises(ChannelSendError, match="message to edit not found") as excinfo:
            await ch.edit_placeholder_message("42", "100", msg)
        assert excinfo.value.retriable is False

    @pytest.mark.asyncio
    async def test_edit_placeholder_other_error(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message to edit not found"))

        msg = OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="text")
        with pytest.raises(ChannelSendError, match="message to edit not found") as excinfo:
            await ch.edit_placeholder_message("42", "100", msg)
        assert excinfo.value.retriable is False


class TestTelegramEditMessageInner:
    @pytest.mark.asyncio
    async def test_edit_parse_error_inner_not_modified(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message is not modified"),
            ]
        )

        await ch.edit_message("42", "100", "text")

    @pytest.mark.asyncio
    async def test_edit_parse_error_inner_other_is_reported(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(
            side_effect=[
                TelegramApiError(400, "Bad Request: can't parse entities"),
                TelegramApiError(400, "Bad Request: message to edit not found"),
            ]
        )

        with pytest.raises(ChannelSendError, match="message to edit not found"):
            await ch.edit_message("42", "100", "text")

    @pytest.mark.asyncio
    async def test_edit_other_error_is_reported(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: message to edit not found"))

        with pytest.raises(ChannelSendError, match="message to edit not found") as excinfo:
            await ch.edit_message("42", "100", "text")
        assert excinfo.value.retriable is False

    @pytest.mark.asyncio
    async def test_edit_server_error_stays_retriable(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.edit_message_text = AsyncMock(side_effect=TelegramApiError(502, "Bad Gateway"))

        with pytest.raises(ChannelSendError) as excinfo:
            await ch.edit_message("42", "100", "text")
        assert excinfo.value.retriable is True


class TestTelegramPinError:
    @pytest.mark.asyncio
    async def test_pin_message_error_silenced(self) -> None:
        ch = make_channel()
        ch._client = MagicMock()
        ch._client.pin_chat_message = AsyncMock(side_effect=TelegramApiError(400, "Bad Request: not enough rights"))

        await ch.pin_message("42", "100")
