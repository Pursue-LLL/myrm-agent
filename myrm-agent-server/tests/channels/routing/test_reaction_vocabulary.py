"""Status reactions are sent in the glyph a platform accepts, or not at all.

Each platform accepts its own reaction vocabulary (Telegram a fixed list, Teams six types,
iMessage six tapbacks). A glyph outside it is rejected or, worse, silently turned into another
one, so the funnel walks a per-role candidate chain and sends the first accepted glyph.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.types import ChannelCapabilities

EYES = "\U0001f440"
THINKING = "\U0001f914"
HOURGLASS = "\u23f3"
CHECK = "\u2705"
PARTY = "\U0001f389"
THUMBS_UP = "\U0001f44d"
THUMBS_DOWN = "\U0001f44e"
CROSS = "\u274c"
CRYING = "\U0001f622"
HEART = "\u2764"
HEART_VS16 = "\u2764\ufe0f"


def _effects(glyphs: frozenset[str] | None) -> tuple[MessageEffects, AsyncMock]:
    ch = MagicMock()
    ch.capabilities = ChannelCapabilities(reactions=True, reaction_glyphs=glyphs)
    ch.react_to_message = AsyncMock()
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=ch)
    return MessageEffects(bus), ch.react_to_message


def _sent(react: AsyncMock) -> list[str]:
    return [call.args[2] for call in react.await_args_list]


class TestAcceptsReaction:
    def test_a_channel_without_a_declared_vocabulary_accepts_everything(self) -> None:
        assert ChannelCapabilities(reactions=True).accepts_reaction(HOURGLASS)

    def test_a_declared_vocabulary_is_the_only_thing_accepted(self) -> None:
        caps = ChannelCapabilities(reactions=True, reaction_glyphs=frozenset({THUMBS_UP}))
        assert caps.accepts_reaction(THUMBS_UP)
        assert not caps.accepts_reaction(CHECK)

    def test_variation_selectors_do_not_change_the_glyph(self) -> None:
        caps = ChannelCapabilities(reactions=True, reaction_glyphs=frozenset({HEART}))
        assert caps.accepts_reaction(HEART_VS16)


class TestAckReaction:
    @pytest.mark.asyncio
    async def test_the_configured_glyph_is_sent_when_the_platform_takes_everything(self) -> None:
        fx, react = _effects(None)
        await fx.ack_reaction("c", "chat", "m1", HOURGLASS)
        assert _sent(react) == [HOURGLASS]

    @pytest.mark.asyncio
    async def test_a_rejected_glyph_falls_back_to_the_next_processing_candidate(self) -> None:
        fx, react = _effects(frozenset({EYES, THUMBS_UP}))
        await fx.ack_reaction("c", "chat", "m1", HOURGLASS)
        assert _sent(react) == [EYES]

    @pytest.mark.asyncio
    async def test_the_second_candidate_is_used_when_the_first_is_missing(self) -> None:
        fx, react = _effects(frozenset({THINKING}))
        await fx.ack_reaction("c", "chat", "m1", HOURGLASS)
        assert _sent(react) == [THINKING]

    @pytest.mark.asyncio
    async def test_nothing_is_sent_when_no_candidate_is_accepted(self) -> None:
        fx, react = _effects(frozenset({THUMBS_UP, HEART}))
        await fx.ack_reaction("c", "chat", "m1", EYES)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vocabulary", [None, frozenset({EYES, THINKING})])
    async def test_an_empty_configured_glyph_sends_nothing(self, vocabulary: frozenset[str] | None) -> None:
        fx, react = _effects(vocabulary)
        await fx.ack_reaction("c", "chat", "m1", "")
        react.assert_not_awaited()


class TestCompletionReaction:
    @pytest.mark.asyncio
    async def test_success_falls_back_to_a_thumbs_up_when_the_check_is_rejected(self) -> None:
        fx, react = _effects(frozenset({EYES, THUMBS_UP, THUMBS_DOWN}))
        await fx.completion_reaction("c", "chat", "m1", success=True, success_emoji=CHECK, failure_emoji=CROSS, had_ack=True)
        assert _sent(react) == ["", THUMBS_UP]

    @pytest.mark.asyncio
    async def test_failure_falls_back_to_a_thumbs_down_when_the_cross_is_rejected(self) -> None:
        fx, react = _effects(frozenset({THUMBS_UP, THUMBS_DOWN}))
        await fx.completion_reaction("c", "chat", "m1", success=False, success_emoji=CHECK, failure_emoji=CROSS)
        assert _sent(react) == [THUMBS_DOWN]

    @pytest.mark.asyncio
    async def test_a_failure_is_never_sent_as_a_success_glyph(self) -> None:
        fx, react = _effects(frozenset({CHECK, THUMBS_UP, PARTY}))
        await fx.completion_reaction("c", "chat", "m1", success=False, success_emoji=CHECK, failure_emoji=CROSS)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_ack_is_still_cleared_when_no_completion_glyph_is_accepted(self) -> None:
        fx, react = _effects(frozenset({HEART}))
        await fx.completion_reaction("c", "chat", "m1", success=False, success_emoji=CHECK, failure_emoji=CROSS, had_ack=True)
        assert _sent(react) == [""]

    @pytest.mark.asyncio
    async def test_the_configured_glyph_wins_when_the_platform_takes_it(self) -> None:
        fx, react = _effects(frozenset({PARTY, CHECK}))
        await fx.completion_reaction("c", "chat", "m1", success=True, success_emoji=PARTY, failure_emoji=CROSS)
        assert _sent(react) == [PARTY]

    @pytest.mark.asyncio
    async def test_crying_face_is_the_last_failure_candidate(self) -> None:
        fx, react = _effects(frozenset({CRYING}))
        await fx.completion_reaction("c", "chat", "m1", success=False, success_emoji=CHECK, failure_emoji=CROSS)
        assert _sent(react) == [CRYING]
