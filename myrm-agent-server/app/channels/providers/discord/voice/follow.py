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
Discord users across voice channels with handoff and reconciliation.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Set
from typing import Protocol

import discord

logger = logging.getLogger(__name__)

_RECONCILE_INTERVAL = 10.0
_RECONCILE_JITTER = 3.0


class VoiceJoinLeave(Protocol):
    """Abstraction for join/leave operations used by follow logic."""

    async def join(
        self, channel: discord.VoiceChannel, *, text_channel_id: int = 0
    ) -> bool: ...

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
        self._follow_user_ids: set[str] = (
            set(follow_user_ids) if follow_user_ids else set()
        )
        self._allowed_channel_set: frozenset[tuple[str, str]] = (
            frozenset(allowed_channels) if allowed_channels else frozenset()
        )
        self._on_guild_leave_check = on_guild_leave_check

        self._followed_user_channels: dict[str, tuple[int, int]] = {}
        self._followed_voice_guilds: set[int] = set()
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
        """Start the periodic voice state reconciliation loop."""
        if not self.enabled or self._reconcile_task is not None:
            return
        self._reconcile_task = asyncio.get_running_loop().create_task(
            self._reconcile_loop(), name="voice-reconcile"
        )
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

            self._followed_user_channels[user_id_str] = (
                guild_id,
                after.channel.id,
            )
            self._followed_voice_guilds.add(guild_id)
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
        before_channel: discord.VoiceChannel | None,
        after_channel: discord.VoiceChannel | None,
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

        any_followed_in_guild = any(
            gid == guild_id for gid, _ in self._followed_user_channels.values()
        )
        if not any_followed_in_guild:
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
        """Single reconciliation pass via REST API to bypass stale Gateway cache."""
        if not self._follow_user_ids:
            return

        for guild in self._client.guilds:
            target_channel = await self._find_followed_user_channel_rest(guild)
            if self._destroyed:
                return
            if target_channel:
                await self._voice_ops.join(target_channel)
            elif guild.id in self._followed_voice_guilds:
                has_any = any(
                    gid == guild.id
                    for gid, _ in self._followed_user_channels.values()
                )
                if not has_any:
                    self._followed_voice_guilds.discard(guild.id)
                    should_leave = True
                    if self._on_guild_leave_check:
                        should_leave = await self._on_guild_leave_check(guild.id)
                    if should_leave:
                        logger.info(
                            "Reconciliation: no followed users in guild %s, leaving",
                            guild.name,
                        )
                        await self._voice_ops.leave(guild.id)

    async def _find_followed_user_channel_rest(
        self, guild: discord.Guild
    ) -> discord.VoiceChannel | None:
        """Query REST API for followed users' voice state (bypasses Gateway cache)."""
        for user_id in self._follow_user_ids:
            try:
                data = await self._client.http.request(
                    discord.http.Route(
                        "GET",
                        "/guilds/{guild_id}/voice-states/{user_id}",
                        guild_id=guild.id,
                        user_id=user_id,
                    )
                )
            except discord.NotFound:
                continue
            except discord.HTTPException as e:
                logger.debug("REST voice state query failed for %s: %s", user_id, e)
                continue

            channel_id = data.get("channel_id")
            if not channel_id:
                continue

            cid = int(channel_id)
            if not self.is_channel_allowed(guild.id, cid):
                continue

            ch = guild.get_channel(cid)
            if isinstance(ch, discord.VoiceChannel):
                return ch
        return None
