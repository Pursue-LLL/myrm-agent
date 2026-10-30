"""Telegram channel factories shared by the channel test modules."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.api import TelegramClient
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


def make_channel() -> TelegramChannel:
    ch = TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)
    ch._bot_username = "testbot"
    ch._tg_bot_id = 123456789
    ch._rich_send_available = False
    ch._rich_draft_available = False
    return ch


def make_topic_channel(*, auto_topic: bool = False) -> tuple[TelegramChannel, MagicMock]:
    ch = TelegramChannel(
        bot_token=FAKE_TELEGRAM_BOT_TOKEN,
        auto_topic=auto_topic,
    )
    ch._bot_username = "testbot"
    ch._tg_bot_id = 123456789
    client = MagicMock(spec=TelegramClient)
    ch._client = client
    return ch, client
