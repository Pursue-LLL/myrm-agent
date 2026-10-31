"""Voice Follow-User - tracks configured users across voice channels.

Provides follow-user logic, multi-user handoff, bounded reconciliation,
bot movement protection, and allowed-channel enforcement.

[INPUT]
- discord.Client (POS: Discord bot client)
- VoiceJoinLeave Protocol (POS: join/leave abstraction from manager)

[OUTPUT]
- VoiceFollowManager: class - follow-user orchestration

[POS]
Voice follow-user orchestration. Automatically tracks configured
Discord users across voice channels with handoff and reconciliation;
reconciliation heals a missed join, move or leave from the REST voice
state; a failed pass is logged and the next one runs, and a poll REST cannot answer in a guild with follow state is
warned about once per window, because the guild's stale records are not healed until it answers.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import random
import time
from collections.abc import Awaitable, Callable, Set
from typing import Protocol

import discord
from discord.http import Route

logger = logging.getLogger(__name__)

_RECONCILE_INTERVAL = 10.0
_RECONCILE_JITTER = 3.0
# A poll that stays unanswerable (a missing permission, an outage) fails every pass: one warning per window and (guild, user).
_WARN_INTERVAL = 600.0

# Both kinds of channel accept a voice connection, and a followed user can be in either.
VoiceTarget = discord.VoiceChannel | discord.StageChannel


class _Presence(enum.Enum):
    """What one REST poll says about a followed user when it names no channel to join."""

    # Discord confirmed the user is in no channel the bot follows into.
    ABSENT = "absent"
    # Nothing to act on: the poll failed, or the user is in a channel reconciliation cannot join (a stage channel, one not cached).
    UNKNOWN = "unknown"


class VoiceJoinLeave(Protocol):
    """Abstraction for join/leave operations used by follow logic."""

    async def join(self, channel: VoiceTarget, *, text_channel_id: int = 0) -> bool: ...

    async def leave(self, guild_id: int) -> None: ...


class VoiceFollowManager:
    """Manages voice follow-user logic with handoff and reconciliation.

    Tracks configured Discord users and automatically follows them
    across voice channels, respecting allowed-channel restrictions.
    """

    def __init__(
        self,
        client: discord.Client,
        voice_ops: VoiceJoinLeave,
        *,
        follow_user_ids: Set[str] | None = None,
        allowed_channels: list[tuple[str, str]] | None = None,
        on_guild_leave_check: Callable[[int], Awaitable[bool]] | None = None,
    ) -> None:
        self._client = client
        self._voice_ops = voice_ops
        self._follow_user_ids: set[str] = set(follow_user_ids) if follow_user_ids else set()
        self._allowed_channel_set: frozenset[tuple[str, str]] = frozenset(allowed_channels) if allowed_channels else frozenset()
        self._on_guild_leave_check = on_guild_leave_check

        self._followed_user_channels: dict[str, tuple[int, int]] = {}
        self._followed_voice_guilds: set[int] = set()
        # Channel changes the events have reported: a reconciliation pass compares it to tell its REST answers were overtaken.
        self._channel_change_count = 0
        self._warned_at: dict[tuple[int, str], float] = {}
        self._reconcile_task: asyncio.Task[None] | None = None
        self._destroyed = False

    @property
    def enabled(self) -> bool:
        return bool(self._follow_user_ids)

    @property
    def followed_guilds(self) -> frozenset[int]:
        return frozenset(self._followed_voice_guilds)

    def is_followed_user(self, user_id: str) -> bool:
        return user_id in self._follow_user_ids

    def is_channel_allowed(self, guild_id: int, channel_id: int) -> bool:
        """Check if a voice channel is in the allowed list (or no restriction)."""
        if not self._allowed_channel_set:
            return True
        return (str(guild_id), str(channel_id)) in self._allowed_channel_set

    async def start_reconciliation(self) -> None:
        """Start the periodic voice state reconciliation loop; one that has ended is started again."""
        task = self._reconcile_task
        if not self.enabled or (task is not None and not task.done()):
            return
        self._reconcile_task = asyncio.get_running_loop().create_task(self._reconcile_loop(), name="voice-reconcile")
        logger.info("Voice follow reconciliation started")

    async def stop_reconciliation(self) -> None:
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        self._reconcile_task = None

    async def destroy(self) -> None:
        """Mark as destroyed and stop reconciliation."""
        self._destroyed = True
        await self.stop_reconciliation()
        self._followed_voice_guilds.clear()
        self._followed_user_channels.clear()

    async def handle_followed_user_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Follow a configured user when they join/move/leave voice channels."""
        guild_id = member.guild.id
        user_id_str = str(member.id)

        if after.channel != before.channel:
            self._channel_change_count += 1

        if after.channel and after.channel != before.channel:
            if not self.is_channel_allowed(guild_id, after.channel.id):
                logger.info(
                    "Followed user %s moved to non-allowed channel %s, ignoring",
                    member.display_name,
                    after.channel.id,
                )
                self._followed_user_channels.pop(user_id_str, None)
                await self._try_handoff_or_leave(guild_id)
                return

            self._track(user_id_str, guild_id, after.channel.id)
            logger.info(
                "Following user %s to voice channel %s in guild %d",
                member.display_name,
                after.channel.name,
                guild_id,
            )
            await self._voice_ops.join(after.channel)

        elif not after.channel and before.channel:
            self._followed_user_channels.pop(user_id_str, None)
            logger.info(
                "Followed user %s left voice in guild %d",
                member.display_name,
                guild_id,
            )
            await self._try_handoff_or_leave(guild_id)

    async def handle_bot_voice_update(
        self,
        guild_id: int,
        before_channel: VoiceTarget | None,
        after_channel: VoiceTarget | None,
    ) -> bool:
        """Handle when the bot is moved by an admin. Returns True if handled."""
        if not after_channel and before_channel:
            self._followed_voice_guilds.discard(guild_id)
            return False

        if after_channel and after_channel != before_channel and self.enabled:
            if not self.is_channel_allowed(guild_id, after_channel.id):
                logger.warning(
                    "Bot was moved to non-allowed channel %s, leaving",
                    after_channel.id,
                )
                await self._voice_ops.leave(guild_id)
                return True

        return False

    def _track(self, user_id: str, guild_id: int, channel_id: int) -> None:
        """Record that a followed user is in a channel of the guild, so a later move, handoff or leave finds the record."""
        self._followed_user_channels[user_id] = (guild_id, channel_id)
        self._followed_voice_guilds.add(guild_id)

    def _has_records(self, guild_id: int) -> bool:
        return any(gid == guild_id for gid, _ in self._followed_user_channels.values())

    async def _try_handoff_or_leave(self, guild_id: int) -> None:
        """Try to handoff to another followed user in the same guild, or leave."""
        for uid, (gid, cid) in self._followed_user_channels.items():
            if gid != guild_id:
                continue
            channel = self._client.get_channel(cid)
            if isinstance(channel, discord.VoiceChannel):
                if self.is_channel_allowed(guild_id, cid):
                    logger.info(
                        "Handing off to followed user %s in channel %s",
                        uid,
                        channel.name,
                    )
                    await self._voice_ops.join(channel)
                    return

        if not self._has_records(guild_id):
            self._followed_voice_guilds.discard(guild_id)
            should_leave = True
            if self._on_guild_leave_check:
                should_leave = await self._on_guild_leave_check(guild_id)
            if should_leave:
                logger.info(
                    "No followed users remain in guild %d, leaving voice",
                    guild_id,
                )
                await self._voice_ops.leave(guild_id)

    async def _reconcile_loop(self) -> None:
        """Periodically reconcile voice state to handle missed WebSocket events."""
        try:
            while not self._destroyed:
                jitter = random.uniform(0, _RECONCILE_JITTER)
                await asyncio.sleep(_RECONCILE_INTERVAL + jitter)
                if self._destroyed:
                    break
                await self._reconcile_once()
        except asyncio.CancelledError:
            pass

    async def _reconcile_once(self) -> None:
        """Single reconciliation pass via REST API to bypass stale Gateway cache.

        A guild whose pass fails (a network error on the REST poll, a join that raises) is logged and retried by the next pass,
        so it neither ends the loop nor skips the guilds after it. A leave that raises is only logged: the guild is dropped first.
        """
        if not self._follow_user_ids:
            return

        for guild in self._client.guilds:
            try:
                await self._reconcile_guild(guild)
            except Exception as e:
                logger.warning("Voice reconciliation failed in guild %s: %r", guild.id, e)
            if self._destroyed:
                return

    async def _reconcile_guild(self, guild: discord.Guild) -> None:
        """Bring the guild's follow state in line with what REST says.

        Joins the channel a followed user is in. Once every followed user is confirmed absent, the records the missed events
        left behind are dropped and the bot hands off or leaves exactly as the leave event would have. An answer that is not
        a confirmation changes nothing, and neither do the answers of a pass during which a followed user changed channel:
        the event is newer than they are.
        """
        changes_seen = self._channel_change_count
        absent: list[str] = []
        confirmed = True
        for user_id in self._follow_user_ids:
            presence = await self._poll_presence(guild, user_id)
            if self._destroyed or self._channel_change_count != changes_seen:
                return
            if isinstance(presence, discord.VoiceChannel):
                self._track(user_id, guild.id, presence.id)
                await self._voice_ops.join(presence)
                return
            if presence is _Presence.ABSENT:
                absent.append(user_id)
            else:
                confirmed = False
        if not confirmed:
            return

        dropped: list[str] = []
        for user_id in absent:
            record = self._followed_user_channels.get(user_id)
            if record is not None and record[0] == guild.id:
                del self._followed_user_channels[user_id]
                dropped.append(user_id)
        if dropped:
            logger.info(
                "Reconciliation: followed users %s are in no channel the bot follows into in guild %d, dropping stale records",
                ", ".join(dropped),
                guild.id,
            )
        if dropped or guild.id in self._followed_voice_guilds:
            await self._try_handoff_or_leave(guild.id)

    async def _poll_presence(self, guild: discord.Guild, user_id: str) -> discord.VoiceChannel | _Presence:
        """Query the REST API for a followed user's voice state (bypasses the Gateway cache)."""
        try:
            data = await self._client.http.request(
                Route(
                    "GET",
                    "/guilds/{guild_id}/voice-states/{user_id}",
                    guild_id=guild.id,
                    user_id=user_id,
                )
            )
        except discord.NotFound:
            return _Presence.ABSENT
        except discord.HTTPException as e:
            self._report_unanswered(guild.id, user_id, e)
            return _Presence.UNKNOWN

        channel_id = data.get("channel_id")
        if not channel_id:
            return _Presence.ABSENT

        cid = int(channel_id)
        if not self.is_channel_allowed(guild.id, cid):
            return _Presence.ABSENT

        channel = guild.get_channel(cid)
        return channel if isinstance(channel, discord.VoiceChannel) else _Presence.UNKNOWN

    def _report_unanswered(self, guild_id: int, user_id: str, error: discord.HTTPException) -> None:
        """Log a poll REST could not answer: a WARNING once per window while the guild has follow state, else DEBUG.

        Until the poll is answered the guild's stale records are not healed. A guild with no follow state has nothing to heal,
        and every guild the bot is in is polled, so a failure there is not worth a warning.
        """
        key = (guild_id, user_id)
        now = time.monotonic()
        last_warned = self._warned_at.get(key)
        has_follow_state = guild_id in self._followed_voice_guilds or self._has_records(guild_id)
        if not has_follow_state or (last_warned is not None and now - last_warned < _WARN_INTERVAL):
            logger.debug("REST voice state query failed for %s: %s", user_id, error)
            return
        self._warned_at[key] = now
        logger.warning(
            "Voice reconciliation could not read the voice state of user %s in guild %d (%s): "
            "stale follow records there are not healed until the poll is answered",
            user_id,
            guild_id,
            error,
        )
