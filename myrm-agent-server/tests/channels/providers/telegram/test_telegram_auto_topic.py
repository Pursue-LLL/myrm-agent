"""Auto-topic only acts on a message that names the chat it came from."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramClient
from app.channels.types import InboundMessage
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


def _forum_channel() -> tuple[TelegramChannel, MagicMock]:
    channel = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN, auto_topic=True)
    client = MagicMock(spec=TelegramClient)
    channel._client = client
    return channel, client


@pytest.mark.parametrize("thread_id", [None, "7"], ids=["no_topic_yet", "inside_a_topic"])
@pytest.mark.asyncio
async def test_a_forum_message_without_a_chat_id_is_passed_through_untouched(thread_id: str | None) -> None:
    channel, client = _forum_channel()
    msg = InboundMessage(
        channel="telegram",
        sender_id="42",
        sender_name="Alice",
        content="hello",
        chat_id=None,
        is_group=True,
        thread_id=thread_id,
        metadata={"is_forum": True},
    )

    result = await channel._pre_emit_hook(msg)

    assert result is msg
    client.create_forum_topic.assert_not_called()
    client.edit_forum_topic.assert_not_called()
    assert not channel._background_tasks
