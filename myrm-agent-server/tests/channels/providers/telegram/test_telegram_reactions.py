"""Telegram only accepts the fixed ``ReactionTypeEmoji`` list for a bot's message reaction.

Anything else is answered with ``REACTION_INVALID``, so the default success and failure glyphs
(check mark, cross) never show up unless the funnel picks a glyph from this list.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.constants import TELEGRAM_REACTION_EMOJI
from tests.channels.channel_test_base import FAKE_TELEGRAM_BOT_TOKEN


def _channel() -> TelegramChannel:
    return TelegramChannel(bot_token=FAKE_TELEGRAM_BOT_TOKEN)


class TestDeclaredVocabulary:
    def test_the_official_list_has_seventy_three_entries(self) -> None:
        assert len(TELEGRAM_REACTION_EMOJI) == 73

    @pytest.mark.parametrize("glyph", ["\U0001f440", "\U0001f44d", "\U0001f44e", "\U0001f914", "\U0001f389", "\u2764\ufe0f"])
    def test_accepts_the_status_glyphs_the_list_contains(self, glyph: str) -> None:
        assert TelegramChannel.capabilities.accepts_reaction(glyph)

    @pytest.mark.parametrize("glyph", ["\u2705", "\u274c", "\u23f3", "\U0001f4ad", "\u26a0\ufe0f", "\U0001f6ab"])
    def test_rejects_the_glyphs_the_list_lacks(self, glyph: str) -> None:
        assert not TelegramChannel.capabilities.accepts_reaction(glyph)

    def test_zero_width_joiner_sequences_stay_whole(self) -> None:
        assert TelegramChannel.capabilities.accepts_reaction("\u2764\u200d\U0001f525")


class TestReactionPayload:
    @pytest.mark.asyncio
    async def test_the_glyph_is_sent_in_the_listed_spelling(self) -> None:
        ch = _channel()
        ch._client.set_message_reaction = AsyncMock()
        await ch.react_to_message("42", "100", "\u2764\ufe0f")
        ch._client.set_message_reaction.assert_awaited_once_with("42", 100, [{"type": "emoji", "emoji": "\u2764"}])

    @pytest.mark.asyncio
    async def test_an_empty_glyph_clears_the_reaction(self) -> None:
        ch = _channel()
        ch._client.set_message_reaction = AsyncMock()
        await ch.react_to_message("42", "100", "")
        ch._client.set_message_reaction.assert_awaited_once_with("42", 100, [])
