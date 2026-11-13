"""TelegramChannel when Telegram refuses a draft or a Rich Message: what is remembered, what is retried, what is raised."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api_core import TelegramApiError
from app.channels.types import OutboundMessage
from tests.channels.providers.telegram.telegram_channel_factories import make_channel

_LONG_TEXT = "A" * 30  # Long enough to be shown as a draft update
_PARSE_ERROR = TelegramApiError(400, "Bad Request: can't parse entities: unexpected end tag")
_NOT_MODIFIED = TelegramApiError(400, "Bad Request: message is not modified")
_UNKNOWN_METHOD = TelegramApiError(404, "Not Found")
_SERVER_ERROR = TelegramApiError(500, "Internal Server Error")
_REFUSED = TelegramApiError(400, "Bad Request: refused for another reason")
_BLOCKED = TelegramApiError(403, "Forbidden: bot was blocked by the user")


def _channel(*, rich_send: bool | None = False, rich_draft: bool | None = False) -> TelegramChannel:
    channel = make_channel()
    channel._rich_send_available = rich_send
    channel._rich_draft_available = rich_draft
    channel._client = MagicMock()
    return channel


def _final_reply() -> OutboundMessage:
    return OutboundMessage(channel="telegram", user_id="u1", recipient_id="42", content="Final answer")


def _with_draft(channel: TelegramChannel, message_id: str = "draft:1", draft_id: int = 1) -> str:
    channel._active_drafts[channel._draft_key("42", message_id)] = draft_id
    return message_id


class TestRichDraftPreview:
    @pytest.mark.asyncio
    async def test_a_rich_draft_telegram_takes_is_remembered(self) -> None:
        channel = _channel(rich_draft=None)
        channel._client.send_rich_message_draft = AsyncMock()
        channel._client.send_message_draft = AsyncMock()

        draft_id = await channel._try_send_draft("42", "hello")

        assert draft_id == channel._draft_counter
        assert channel._rich_draft_available is True
        channel._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "remembered"),
        [
            (_UNKNOWN_METHOD, False),
            (_REFUSED, False),
            (TelegramApiError(400, "Bad Request: can't be used in groups"), None),
            (TelegramApiError(400, "Bad Request: can be used only in private chats"), None),
        ],
    )
    async def test_a_refused_rich_draft_falls_back_to_the_plain_draft(
        self, error: TelegramApiError, remembered: bool | None
    ) -> None:
        channel = _channel(rich_draft=None)
        channel._client.send_rich_message_draft = AsyncMock(side_effect=error)
        channel._client.send_message_draft = AsyncMock()

        draft_id = await channel._try_send_draft("42", "hello")

        assert draft_id is not None
        assert channel._rich_draft_available is remembered  # A restriction of this chat is not held against the bot
        channel._client.send_message_draft.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_telegram_server_error_on_the_rich_draft_is_raised(self) -> None:
        channel = _channel(rich_draft=None)
        channel._client.send_rich_message_draft = AsyncMock(side_effect=_SERVER_ERROR)
        channel._client.send_message_draft = AsyncMock()

        with pytest.raises(TelegramApiError):
            await channel._try_send_draft("42", "hello")

        channel._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_plain_draft_refused_for_an_unknown_reason_is_raised(self) -> None:
        channel = _channel()
        channel._client.send_message_draft = AsyncMock(side_effect=_SERVER_ERROR)

        with pytest.raises(TelegramApiError):
            await channel._try_send_draft("42", "hello")

    @pytest.mark.asyncio
    async def test_a_draft_update_goes_out_as_a_rich_draft_when_telegram_takes_them(self) -> None:
        channel = _channel(rich_draft=True)
        channel._client.send_rich_message_draft = AsyncMock()
        channel._client.send_message_draft = AsyncMock()
        message_id = _with_draft(channel, draft_id=7)

        await channel.edit_message("42", message_id, _LONG_TEXT)

        channel._client.send_rich_message_draft.assert_awaited_once_with("42", 7, _LONG_TEXT)
        channel._client.send_message_draft.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_refused_rich_draft_update_is_sent_as_a_plain_draft(self) -> None:
        channel = _channel(rich_draft=True)
        channel._client.send_rich_message_draft = AsyncMock(side_effect=_REFUSED)
        channel._client.send_message_draft = AsyncMock()
        message_id = _with_draft(channel)

        await channel.edit_message("42", message_id, _LONG_TEXT)

        channel._client.send_message_draft.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_draft_update_that_nothing_takes_is_dropped_and_never_becomes_an_edit(self) -> None:
        channel = _channel(rich_draft=True, rich_send=True)
        channel._client.send_rich_message_draft = AsyncMock(side_effect=_REFUSED)
        channel._client.send_message_draft = AsyncMock(side_effect=_REFUSED)
        channel._client.edit_message_text = AsyncMock()
        message_id = _with_draft(channel)

        await channel.edit_message("42", message_id, _LONG_TEXT)

        channel._client.edit_message_text.assert_not_called()


class TestRichEditOfAPlaceholder:
    @pytest.mark.asyncio
    async def test_a_progress_edit_is_sent_as_a_rich_message_when_telegram_takes_them(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock()

        await channel.edit_message("42", "100", "progress")

        channel._client.edit_message_text.assert_awaited_once()
        assert channel._client.edit_message_text.await_args.kwargs["rich_message"] == {"markdown": "progress"}

    @pytest.mark.asyncio
    async def test_a_rich_progress_edit_that_changes_nothing_is_not_repeated_as_html(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock(side_effect=_NOT_MODIFIED)

        await channel.edit_message("42", "100", "progress")

        channel._client.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [_REFUSED, _SERVER_ERROR])
    async def test_a_refused_rich_progress_edit_is_repeated_as_html(self, error: TelegramApiError) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock(side_effect=[error, None])

        await channel.edit_message("42", "100", "progress")

        assert channel._client.edit_message_text.await_count == 2
        assert "rich_message" not in channel._client.edit_message_text.await_args.kwargs


class TestMaterializingADraft:
    @pytest.mark.asyncio
    async def test_a_draft_that_cannot_be_cleared_does_not_stop_the_final_reply(self) -> None:
        channel = _channel()
        channel._client.send_message_draft = AsyncMock(side_effect=_REFUSED)
        channel._client.send_message = AsyncMock(return_value={"message_id": 500})
        message_id = _with_draft(channel)

        await channel.edit_placeholder_message("42", message_id, _final_reply())

        channel._client.send_message.assert_awaited_once()
        assert not channel._active_drafts

    @pytest.mark.asyncio
    async def test_the_final_reply_replaces_a_draft_as_a_rich_message_when_telegram_takes_them(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.send_message_draft = AsyncMock()
        channel._client.send_rich_message = AsyncMock()
        channel._client.send_message = AsyncMock()
        message_id = _with_draft(channel)

        await channel.edit_placeholder_message("42", message_id, _final_reply())

        channel._client.send_rich_message.assert_awaited_once()
        assert "Final answer" in channel._client.send_rich_message.await_args.args[1]
        channel._client.send_message.assert_not_called()
        assert channel._rich_send_available is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("error", "still_offered"), [(_UNKNOWN_METHOD, False), (_REFUSED, True)])
    async def test_a_refused_rich_final_reply_is_sent_as_html(self, error: TelegramApiError, still_offered: bool) -> None:
        channel = _channel(rich_send=None)
        channel._client.send_message_draft = AsyncMock()
        channel._client.send_rich_message = AsyncMock(side_effect=error)
        channel._client.send_message = AsyncMock()
        message_id = _with_draft(channel)

        await channel.edit_placeholder_message("42", message_id, _final_reply())

        channel._client.send_message.assert_awaited_once()
        assert (channel._rich_send_available is not False) is still_offered  # Only an unknown method rules Rich Messages out

    @pytest.mark.asyncio
    async def test_a_telegram_server_error_on_the_rich_final_reply_is_raised(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.send_message_draft = AsyncMock()
        channel._client.send_rich_message = AsyncMock(side_effect=_SERVER_ERROR)
        channel._client.send_message = AsyncMock()
        message_id = _with_draft(channel)

        with pytest.raises(TelegramApiError):
            await channel.edit_placeholder_message("42", message_id, _final_reply())

        channel._client.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_final_reply_telegram_cannot_parse_as_html_goes_out_as_plain_text(self) -> None:
        channel = _channel()
        channel._client.send_message_draft = AsyncMock()
        channel._client.send_message = AsyncMock(side_effect=[_PARSE_ERROR, {"message_id": 501}])
        message_id = _with_draft(channel)

        await channel.edit_placeholder_message("42", message_id, _final_reply())

        assert channel._client.send_message.await_count == 2
        assert channel._client.send_message.await_args.kwargs["parse_mode"] == ""

    @pytest.mark.asyncio
    async def test_a_final_reply_telegram_will_not_take_is_reported_as_a_send_failure(self) -> None:
        channel = _channel()
        channel._client.send_message_draft = AsyncMock()
        channel._client.send_message = AsyncMock(side_effect=_BLOCKED)
        message_id = _with_draft(channel)

        with pytest.raises(ChannelSendError):
            await channel.edit_placeholder_message("42", message_id, _final_reply())


class TestEditingAPlaceholderInPlace:
    @pytest.mark.asyncio
    async def test_the_final_reply_edits_the_placeholder_as_a_rich_message_when_telegram_takes_them(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock()

        await channel.edit_placeholder_message("42", "100", _final_reply())

        channel._client.edit_message_text.assert_awaited_once()
        call = channel._client.edit_message_text.await_args
        assert call.kwargs["rich_message"] == {"markdown": call.args[2]}

    @pytest.mark.asyncio
    async def test_a_rich_final_edit_that_changes_nothing_is_not_repeated_as_html(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock(side_effect=_NOT_MODIFIED)

        await channel.edit_placeholder_message("42", "100", _final_reply())

        channel._client.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_refused_rich_final_edit_is_repeated_as_html(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock(side_effect=[_REFUSED, None])

        await channel.edit_placeholder_message("42", "100", _final_reply())

        assert channel._client.edit_message_text.await_count == 2
        assert "rich_message" not in channel._client.edit_message_text.await_args.kwargs

    @pytest.mark.asyncio
    async def test_a_telegram_server_error_on_the_rich_final_edit_is_raised(self) -> None:
        channel = _channel(rich_send=True)
        channel._client.edit_message_text = AsyncMock(side_effect=_SERVER_ERROR)

        with pytest.raises(TelegramApiError):
            await channel.edit_placeholder_message("42", "100", _final_reply())

        channel._client.edit_message_text.assert_awaited_once()


class TestDeletingADraft:
    @pytest.mark.asyncio
    async def test_a_draft_that_cannot_be_cleared_is_still_forgotten(self) -> None:
        channel = _channel()
        channel._client.send_message_draft = AsyncMock(side_effect=_REFUSED)
        channel._client.delete_message = AsyncMock()
        message_id = _with_draft(channel)

        await channel.delete_message("42", message_id)

        assert not channel._active_drafts
        channel._client.delete_message.assert_not_called()
