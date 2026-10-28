"""The status reaction of one turn: a mark when the message arrives, then one verdict, in the glyphs a platform accepts.

Each platform accepts its own reaction vocabulary (Telegram a fixed list, Teams and iMessage fixed reaction sets). A glyph
outside it is rejected or, worse, silently turned into another one, so each role (received, completed, failed) walks a
candidate chain and sends the first accepted glyph, or nothing.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.reactions import ReactionFunnel, StatusReaction, TurnOutcome
from app.channels.routing.router_models import ReactionPolicy
from app.channels.types import ChannelCapabilities, ReactionLevel

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
OFF = ""


def _status(
    glyphs: frozenset[str] | None = None,
    *,
    policy: ReactionPolicy | None = None,
    message_id: str | None = "m1",
) -> tuple[StatusReaction, AsyncMock]:
    ch = MagicMock()
    ch.capabilities = ChannelCapabilities(reactions=True, reaction_glyphs=glyphs)
    ch.react_to_message = AsyncMock()
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=ch)
    status = StatusReaction(ReactionFunnel(bus), policy or ReactionPolicy(), "c", "chat", message_id)
    return status, ch.react_to_message


def _sent(react: AsyncMock) -> list[str]:
    return [call.args[2] for call in react.await_args_list]


class TestReceived:
    @pytest.mark.asyncio
    async def test_the_configured_glyph_is_sent_when_the_platform_takes_everything(self) -> None:
        status, react = _status(policy=ReactionPolicy(processing_emoji=HOURGLASS))
        status.received()
        await status.marked()
        assert _sent(react) == [HOURGLASS]

    @pytest.mark.asyncio
    async def test_a_rejected_glyph_falls_back_to_the_next_processing_candidate(self) -> None:
        status, react = _status(frozenset({EYES, THUMBS_UP}), policy=ReactionPolicy(processing_emoji=HOURGLASS))
        status.received()
        await status.marked()
        assert _sent(react) == [EYES]

    @pytest.mark.asyncio
    async def test_the_second_candidate_is_used_when_the_first_is_missing(self) -> None:
        status, react = _status(frozenset({THINKING}), policy=ReactionPolicy(processing_emoji=HOURGLASS))
        status.received()
        await status.marked()
        assert _sent(react) == [THINKING]

    @pytest.mark.asyncio
    async def test_nothing_is_sent_when_no_candidate_is_accepted(self) -> None:
        status, react = _status(frozenset({THUMBS_UP, HEART}))
        status.received()
        await status.marked()
        react.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("vocabulary", [None, frozenset({EYES, THINKING})])
    async def test_an_empty_configured_glyph_sends_nothing(self, vocabulary: frozenset[str] | None) -> None:
        status, react = _status(vocabulary, policy=ReactionPolicy(processing_emoji=OFF))
        status.received()
        await status.marked()
        react.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("level", [ReactionLevel.OFF, ReactionLevel.SIMPLE])
    async def test_only_the_full_level_marks_the_message(self, level: ReactionLevel) -> None:
        status, react = _status(policy=ReactionPolicy(level=level))
        status.received()
        await status.marked()
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_message_without_a_platform_id_is_not_marked(self) -> None:
        status, react = _status(message_id=None)
        status.received()
        await status.marked()
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_message_is_marked_once(self) -> None:
        status, react = _status()
        status.received()
        await status.marked()
        status.received()
        await status.marked()
        assert _sent(react) == [EYES]


class TestFinish:
    @pytest.mark.asyncio
    async def test_the_mark_is_taken_off_before_the_verdict_is_shown(self) -> None:
        status, react = _status()
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.COMPLETED)
        assert _sent(react) == [EYES, OFF, CHECK]

    @pytest.mark.asyncio
    async def test_a_message_that_was_never_marked_has_nothing_taken_off(self) -> None:
        status, react = _status(frozenset({CHECK}))
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.COMPLETED)
        assert _sent(react) == [CHECK]

    @pytest.mark.asyncio
    async def test_a_stopped_turn_only_has_its_mark_taken_off(self) -> None:
        status, react = _status()
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.ABANDONED)
        assert _sent(react) == [EYES, OFF]

    @pytest.mark.asyncio
    async def test_the_verdict_is_shown_once(self) -> None:
        status, react = _status()
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.COMPLETED)
        await status.finish(TurnOutcome.FAILED)
        assert _sent(react) == [EYES, OFF, CHECK]

    @pytest.mark.asyncio
    async def test_a_finished_turn_is_not_marked_afterwards(self) -> None:
        status, react = _status()
        await status.finish(TurnOutcome.COMPLETED)
        status.received()
        await status.marked()
        assert _sent(react) == [CHECK]

    @pytest.mark.asyncio
    async def test_a_message_without_a_platform_id_shows_no_verdict(self) -> None:
        status, react = _status(message_id=None)
        await status.finish(TurnOutcome.COMPLETED)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("level", [ReactionLevel.OFF])
    async def test_a_policy_without_status_reactions_shows_nothing(self, level: ReactionLevel) -> None:
        status, react = _status(policy=ReactionPolicy(level=level))
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.COMPLETED)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_simple_level_shows_the_verdict_without_a_mark(self) -> None:
        status, react = _status(policy=ReactionPolicy(level=ReactionLevel.SIMPLE))
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.COMPLETED)
        assert _sent(react) == [CHECK]

    @pytest.mark.asyncio
    async def test_a_cut_short_request_still_has_its_mark_taken_off(self) -> None:
        """The platform may have taken a request the turn stopped waiting for."""
        status, react = _status()
        react.side_effect = [asyncio.CancelledError(), None]
        status.received()
        await status.marked()

        await status.finish(TurnOutcome.ABANDONED)

        assert _sent(react) == [EYES, OFF]


class TestVerdictGlyph:
    @pytest.mark.asyncio
    async def test_success_falls_back_to_a_thumbs_up_when_the_check_is_rejected(self) -> None:
        status, react = _status(frozenset({EYES, THUMBS_UP, THUMBS_DOWN}))
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.COMPLETED)
        assert _sent(react) == [EYES, OFF, THUMBS_UP]

    @pytest.mark.asyncio
    async def test_a_failure_is_never_sent_as_a_thumbs_down(self) -> None:
        status, react = _status(frozenset({THUMBS_UP, THUMBS_DOWN}))
        await status.finish(TurnOutcome.FAILED)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failure_is_never_sent_as_a_success_glyph(self) -> None:
        status, react = _status(frozenset({CHECK, THUMBS_UP, PARTY}))
        await status.finish(TurnOutcome.FAILED)
        react.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_mark_is_still_taken_off_when_no_verdict_glyph_is_accepted(self) -> None:
        status, react = _status(frozenset({EYES, HEART}))
        status.received()
        await status.marked()
        await status.finish(TurnOutcome.FAILED)
        assert _sent(react) == [EYES, OFF]

    @pytest.mark.asyncio
    async def test_the_configured_glyph_wins_when_the_platform_takes_it(self) -> None:
        status, react = _status(frozenset({PARTY, CHECK}), policy=ReactionPolicy(completion_emoji=PARTY))
        await status.finish(TurnOutcome.COMPLETED)
        assert _sent(react) == [PARTY]

    @pytest.mark.asyncio
    async def test_failure_falls_back_to_the_crying_face_when_the_cross_is_rejected(self) -> None:
        status, react = _status(frozenset({THUMBS_DOWN, CRYING}))
        await status.finish(TurnOutcome.FAILED)
        assert _sent(react) == [CRYING]

    @pytest.mark.asyncio
    async def test_a_cross_is_the_failure_glyph_when_the_platform_takes_it(self) -> None:
        status, react = _status(frozenset({CROSS, CRYING}))
        await status.finish(TurnOutcome.FAILED)
        assert _sent(react) == [CROSS]


class TestMarkRequestRunsBesideTheTurn:
    """The turn never waits for the platform to mark its message; ``finish`` does, so the order on the platform holds."""

    @staticmethod
    def _slow_platform(react: AsyncMock) -> tuple[list[str], asyncio.Event]:
        """Make every request take until ``release`` is set; the log tells when each one started and ended."""
        log: list[str] = []
        release = asyncio.Event()

        async def request(_chat_id: str, _message_id: str, emoji: str) -> None:
            log.append(f"start {emoji or 'clear'}")
            try:
                await release.wait()
            except asyncio.CancelledError:
                log.append(f"cancelled {emoji or 'clear'}")
                raise
            log.append(f"end {emoji or 'clear'}")

        react.side_effect = request
        return log, release

    @pytest.mark.asyncio
    async def test_the_turn_is_not_held_by_a_platform_that_has_not_answered(self) -> None:
        status, react = _status()
        log, release = self._slow_platform(react)

        status.received()
        await asyncio.sleep(0)

        assert log == [f"start {EYES}"]
        release.set()
        await status.marked()

    @pytest.mark.asyncio
    async def test_the_mark_is_never_taken_off_before_it_was_put_on(self) -> None:
        status, react = _status()
        log, release = self._slow_platform(react)
        status.received()
        finishing = asyncio.create_task(status.finish(TurnOutcome.COMPLETED))
        for _ in range(3):
            await asyncio.sleep(0)

        assert log == [f"start {EYES}"]
        assert not finishing.done()

        release.set()
        await finishing

        assert log == [f"start {EYES}", f"end {EYES}", "start clear", "end clear", f"start {CHECK}", f"end {CHECK}"]

    @pytest.mark.asyncio
    async def test_a_mark_the_platform_refused_does_not_cost_the_verdict(self) -> None:
        status, react = _status()
        react.side_effect = [RuntimeError("platform down"), None, None]
        status.received()

        await status.finish(TurnOutcome.COMPLETED)

        assert _sent(react) == [EYES, OFF, CHECK]

    @pytest.mark.asyncio
    async def test_cancel_stops_a_request_still_in_flight(self) -> None:
        status, react = _status()
        log, _ = self._slow_platform(react)
        status.received()
        await asyncio.sleep(0)

        status.cancel()
        await status.marked()

        assert log == [f"start {EYES}", f"cancelled {EYES}"]

    @pytest.mark.asyncio
    async def test_cancel_after_the_turn_finished_changes_nothing(self) -> None:
        status, react = _status()
        status.received()
        await status.finish(TurnOutcome.COMPLETED)

        status.cancel()

        assert _sent(react) == [EYES, OFF, CHECK]

    @pytest.mark.asyncio
    async def test_cancel_without_a_mark_is_harmless(self) -> None:
        status, react = _status(message_id=None)
        status.received()

        status.cancel()
        await status.marked()

        react.assert_not_awaited()
