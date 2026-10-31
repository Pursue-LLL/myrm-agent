"""A reconciliation pass heals what missed gateway events left behind, and acts only on what REST confirms.

A followed user the REST poll confirms absent has their record dropped and the bot hands off or leaves exactly as the
leave event would have; a session the poll joined is tracked like one the event joined; an answer that confirms nothing
(an HTTP error, a stage channel, a channel the cache does not hold) changes nothing; and a pass during which a followed
user changed channel is discarded, because the event is newer than the answers the pass polled.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.voice.follow import VoiceFollowManager

_USER = "100"
_OTHER_USER = "200"
_FOLLOW_LOGGER = VoiceFollowManager.__module__

# What the REST voice-state poll answers for a user: a channel id, no channel, or the error it raises.
_Answer = str | None | discord.HTTPException


def _not_found() -> discord.NotFound:
    return discord.NotFound(MagicMock(status=404, reason="Not Found"), "Unknown Voice State")


def _server_error() -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=500, reason="Server Error"), "Internal Server Error")


def _voice_state(channel: MagicMock | None) -> MagicMock:
    state = MagicMock()
    state.channel = channel
    return state


def _heals(caplog: pytest.LogCaptureFixture) -> list[str]:
    """The messages a reconciliation pass logs when it drops stale records."""
    return [message for message in (record.getMessage() for record in caplog.records) if message.startswith("Reconciliation:")]


class _Voice:
    """A follow manager over fake guilds, whose REST answers are the ones the test sets (no voice state by default).

    Guild `g` holds the voice channels `g * 10` and `g * 10 + 1`.
    """

    def __init__(
        self,
        *,
        guild_ids: tuple[int, ...] = (1,),
        users: tuple[str, ...] = (_USER,),
        allowed_channels: list[tuple[str, str]] | None = None,
        stay_in_guild: bool = False,
    ) -> None:
        self.answers: dict[tuple[int, str], _Answer] = {}
        self.gate: asyncio.Event | None = None
        self.polling = asyncio.Event()
        self.channels: dict[int, MagicMock] = {}
        self.join = AsyncMock(return_value=True)
        self.leave = AsyncMock()
        self.leave_check = AsyncMock(return_value=not stay_in_guild)

        self.guilds: dict[int, MagicMock] = {}
        for guild_id in guild_ids:
            guild = MagicMock()
            guild.id = guild_id
            guild.get_channel.side_effect = self.channels.get
            self.guilds[guild_id] = guild
            for channel_id in (guild_id * 10, guild_id * 10 + 1):
                self.add_channel(channel_id, discord.VoiceChannel)

        client = MagicMock()
        client.guilds = list(self.guilds.values())
        client.get_channel.side_effect = self.channels.get
        client.http.request = self._request
        voice_ops = MagicMock()
        voice_ops.join = self.join
        voice_ops.leave = self.leave
        self.manager = VoiceFollowManager(
            client,
            voice_ops,
            follow_user_ids=set(users),
            allowed_channels=allowed_channels,
            on_guild_leave_check=self.leave_check,
        )

    def add_channel(self, channel_id: int, spec: type[discord.abc.GuildChannel]) -> None:
        channel = MagicMock(spec=spec)
        channel.id = channel_id
        channel.name = f"channel-{channel_id}"
        self.channels[channel_id] = channel

    async def _request(self, route: discord.http.Route) -> dict[str, str | None]:
        self.polling.set()
        if self.gate is not None:
            await self.gate.wait()
        assert isinstance(route.guild_id, int)
        answer = self.answers.get((route.guild_id, route.url.rsplit("/", 1)[-1]), _not_found())
        if isinstance(answer, discord.HTTPException):
            raise answer
        return {"channel_id": answer}

    def _member(self, guild_id: int, user: str) -> MagicMock:
        member = MagicMock()
        member.id = int(user)
        member.display_name = f"user-{user}"
        member.guild = self.guilds[guild_id]
        return member

    async def user_joins(self, guild_id: int, channel_id: int, *, user: str = _USER) -> None:
        """The gateway event for a followed user entering a channel."""
        await self.manager.handle_followed_user_update(
            self._member(guild_id, user), _voice_state(None), _voice_state(self.channels[channel_id])
        )

    async def user_toggles_mute(self, guild_id: int, channel_id: int, *, user: str = _USER) -> None:
        """The gateway event for a followed user whose voice state changes while they stay in a channel."""
        state = _voice_state(self.channels[channel_id])
        await self.manager.handle_followed_user_update(self._member(guild_id, user), state, state)

    async def reconcile(self) -> None:
        await self.manager._reconcile_once()

    async def reconcile_during(self, event: Callable[[], Awaitable[None]]) -> None:
        """Run a pass whose polls are held in flight while the event happens, then let the answers land."""
        self.gate = asyncio.Event()
        reconcile = asyncio.create_task(self.reconcile())
        async with asyncio.timeout(2.0):
            await self.polling.wait()
        await event()
        self.gate.set()
        await reconcile

    @property
    def records(self) -> dict[str, tuple[int, int]]:
        return dict(self.manager._followed_user_channels)


@pytest.mark.parametrize("answer", [_not_found(), None], ids=["no-voice-state", "no-channel"])
async def test_a_leave_the_gateway_missed_is_healed_in_the_same_guild(answer: _Answer, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_FOLLOW_LOGGER)
    voice = _Voice()
    await voice.user_joins(1, 10)
    voice.answers[(1, _USER)] = answer

    await voice.reconcile()

    voice.leave.assert_awaited_once_with(1)
    assert voice.records == {}
    assert voice.manager.followed_guilds == frozenset()
    heals = _heals(caplog)
    assert len(heals) == 1
    assert _USER in heals[0]


@pytest.mark.parametrize("unconfirmed", ["server-error", "stage-channel", "uncached-channel"])
async def test_an_answer_that_confirms_nothing_changes_nothing(unconfirmed: str) -> None:
    voice = _Voice()
    voice.add_channel(12, discord.StageChannel)
    await voice.user_joins(1, 10)
    voice.join.reset_mock()
    answers: dict[str, _Answer] = {"server-error": _server_error(), "stage-channel": "12", "uncached-channel": "99"}
    voice.answers[(1, _USER)] = answers[unconfirmed]

    await voice.reconcile()

    voice.leave.assert_not_awaited()
    voice.leave_check.assert_not_awaited()
    voice.join.assert_not_awaited()
    assert voice.records == {_USER: (1, 10)}
    assert voice.manager.followed_guilds == {1}


async def test_a_session_the_poll_joined_is_tracked_so_a_later_missed_leave_heals_it() -> None:
    voice = _Voice()
    voice.answers[(1, _USER)] = "10"

    await voice.reconcile()

    voice.join.assert_awaited_once_with(voice.channels[10])
    assert voice.records == {_USER: (1, 10)}
    assert voice.manager.followed_guilds == {1}

    del voice.answers[(1, _USER)]
    await voice.reconcile()

    voice.leave.assert_awaited_once_with(1)
    assert voice.records == {}
    assert voice.manager.followed_guilds == frozenset()


async def test_a_move_the_gateway_missed_joins_the_new_channel_and_updates_the_record() -> None:
    voice = _Voice()
    await voice.user_joins(1, 10)
    voice.answers[(1, _USER)] = "11"

    await voice.reconcile()

    assert voice.join.await_args is not None
    assert voice.join.await_args.args[0] is voice.channels[11]
    assert voice.records == {_USER: (1, 11)}


async def test_a_move_into_a_channel_that_is_not_allowed_leaves_as_the_event_does() -> None:
    voice = _Voice(allowed_channels=[("1", "10")])
    await voice.user_joins(1, 10)
    voice.answers[(1, _USER)] = "11"

    await voice.reconcile()

    voice.leave.assert_awaited_once_with(1)
    assert voice.records == {}


async def test_the_leave_check_can_keep_the_bot_in_voice_and_is_not_asked_again() -> None:
    voice = _Voice(stay_in_guild=True)
    await voice.user_joins(1, 10)

    await voice.reconcile()
    await voice.reconcile()

    voice.leave_check.assert_awaited_once_with(1)
    voice.leave.assert_not_awaited()
    assert voice.records == {}
    assert voice.manager.followed_guilds == frozenset()


async def test_only_the_guild_the_user_left_is_left() -> None:
    voice = _Voice(guild_ids=(1, 2))
    await voice.user_joins(1, 10)
    await voice.user_joins(2, 20)
    voice.answers[(2, _USER)] = "20"

    await voice.reconcile()

    voice.leave.assert_awaited_once_with(1)
    assert voice.records == {_USER: (2, 20)}
    assert voice.manager.followed_guilds == {2}


async def test_the_poll_of_one_guild_never_drops_the_record_of_another() -> None:
    """The record is per user, so a poll of the guild the user left must not take the record of the guild they are in."""
    voice = _Voice(guild_ids=(1, 2))
    await voice.user_joins(1, 10)
    await voice.user_joins(2, 20)
    voice.answers[(2, _USER)] = _server_error()

    await voice.reconcile()

    voice.leave.assert_awaited_once_with(1)
    assert voice.records == {_USER: (2, 20)}
    assert voice.manager.followed_guilds == {2}


async def test_a_user_who_joins_while_the_poll_is_in_flight_is_not_left(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_FOLLOW_LOGGER)
    voice = _Voice()
    await voice.user_joins(1, 10)

    await voice.reconcile_during(lambda: voice.user_joins(1, 11))

    voice.leave.assert_not_awaited()
    assert voice.records == {_USER: (1, 11)}
    assert _heals(caplog) == []


async def test_a_rejoin_in_the_same_channel_while_the_poll_is_in_flight_keeps_the_bot() -> None:
    """The record is the same before and after the event, so only the event itself shows the answer is older."""
    voice = _Voice()
    await voice.user_joins(1, 10)
    voice.answers[(1, _USER)] = None

    await voice.reconcile_during(lambda: voice.user_joins(1, 10))

    voice.leave.assert_not_awaited()
    assert voice.records == {_USER: (1, 10)}


async def test_a_move_while_the_poll_is_in_flight_is_not_undone_by_the_older_answer() -> None:
    voice = _Voice()
    await voice.user_joins(1, 10)
    voice.answers[(1, _USER)] = "10"

    await voice.reconcile_during(lambda: voice.user_joins(1, 11))

    assert [call.args[0] for call in voice.join.await_args_list] == [voice.channels[10], voice.channels[11]]
    assert voice.records == {_USER: (1, 11)}


async def test_a_mute_toggle_while_the_poll_is_in_flight_does_not_discard_the_pass() -> None:
    voice = _Voice()
    voice.answers[(1, _USER)] = "10"

    await voice.reconcile_during(lambda: voice.user_toggles_mute(1, 10))

    voice.join.assert_awaited_once_with(voice.channels[10])
    assert voice.records == {_USER: (1, 10)}


async def test_a_guild_the_follow_never_touched_is_not_left(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_FOLLOW_LOGGER)
    voice = _Voice()

    await voice.reconcile()

    voice.leave_check.assert_not_awaited()
    voice.leave.assert_not_awaited()
    assert voice.records == {}
    assert _heals(caplog) == []


async def test_the_bot_leaves_once_when_every_followed_user_is_confirmed_absent() -> None:
    voice = _Voice(users=(_USER, _OTHER_USER))
    await voice.user_joins(1, 10)
    await voice.user_joins(1, 11, user=_OTHER_USER)

    await voice.reconcile()

    voice.leave.assert_awaited_once_with(1)
    assert voice.records == {}


async def test_one_unconfirmed_followed_user_keeps_every_record() -> None:
    voice = _Voice(users=(_USER, _OTHER_USER))
    await voice.user_joins(1, 10)
    await voice.user_joins(1, 11, user=_OTHER_USER)
    voice.answers[(1, _OTHER_USER)] = _server_error()

    await voice.reconcile()

    voice.leave.assert_not_awaited()
    assert voice.records == {_USER: (1, 10), _OTHER_USER: (1, 11)}
