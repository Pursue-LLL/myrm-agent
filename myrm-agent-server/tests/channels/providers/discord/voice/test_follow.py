"""Unit tests for VoiceFollowManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.voice.follow import (
    VoiceFollowManager,
)


def _make_follow_manager(
    follow_user_ids: set[str] | None = None,
    allowed_channels: list[tuple[str, str]] | None = None,
    on_guild_leave_check: AsyncMock | None = None,
) -> tuple[MagicMock, AsyncMock, AsyncMock, VoiceFollowManager]:
    client = MagicMock()
    client.user = MagicMock()
    client.user.id = 999

    voice_ops = MagicMock()
    voice_ops.join = AsyncMock(return_value=True)
    voice_ops.leave = AsyncMock()

    fm = VoiceFollowManager(
        client,
        voice_ops,
        follow_user_ids=follow_user_ids,
        allowed_channels=allowed_channels,
        on_guild_leave_check=on_guild_leave_check,
    )
    return client, voice_ops.join, voice_ops.leave, fm


class TestFollowManagerInit:
    def test_enabled_when_users_configured(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100", "200"})
        assert fm.enabled is True

    def test_disabled_when_no_users(self) -> None:
        _, _, _, fm = _make_follow_manager()
        assert fm.enabled is False

    def test_is_followed_user(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100", "200"})
        assert fm.is_followed_user("100") is True
        assert fm.is_followed_user("999") is False


class TestChannelAllowed:
    def test_all_allowed_when_no_restriction(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100"})
        assert fm.is_channel_allowed(1, 2) is True

    def test_allowed_when_in_list(self) -> None:
        _, _, _, fm = _make_follow_manager(
            follow_user_ids={"100"},
            allowed_channels=[("111", "222"), ("333", "444")],
        )
        assert fm.is_channel_allowed(111, 222) is True
        assert fm.is_channel_allowed(333, 444) is True
        assert fm.is_channel_allowed(111, 444) is False
        assert fm.is_channel_allowed(999, 999) is False


class TestFollowedUserUpdate:
    @pytest.mark.asyncio
    async def test_follow_user_join(self) -> None:
        _, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100"})

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"

        before = MagicMock()
        before.channel = None
        after = MagicMock()
        after.channel = MagicMock(spec=discord.VoiceChannel)
        after.channel.id = 200
        after.channel.name = "general-vc"

        await fm.handle_followed_user_update(member, before, after)

        join_mock.assert_awaited_once_with(after.channel)
        assert fm._followed_user_channels["100"] == (1, 200)
        assert 1 in fm._followed_voice_guilds

    @pytest.mark.asyncio
    async def test_follow_user_leave_triggers_leave(self) -> None:
        leave_check = AsyncMock(return_value=True)
        _, _, leave_mock, fm = _make_follow_manager(follow_user_ids={"100"}, on_guild_leave_check=leave_check)
        fm._followed_user_channels["100"] = (1, 200)
        fm._followed_voice_guilds.add(1)

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"

        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        await fm.handle_followed_user_update(member, before, after)

        leave_mock.assert_awaited_once_with(1)
        assert "100" not in fm._followed_user_channels

    @pytest.mark.asyncio
    async def test_follow_user_non_allowed_channel_ignored(self) -> None:
        _, join_mock, _, fm = _make_follow_manager(
            follow_user_ids={"100"},
            allowed_channels=[("1", "300")],
        )

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"

        before = MagicMock()
        before.channel = None
        after = MagicMock()
        after.channel = MagicMock(spec=discord.VoiceChannel)
        after.channel.id = 999
        after.channel.name = "private-vc"

        await fm.handle_followed_user_update(member, before, after)
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handoff_to_another_followed_user(self) -> None:
        client, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100", "200"})

        other_channel = MagicMock(spec=discord.VoiceChannel)
        other_channel.id = 500
        other_channel.name = "other-vc"
        client.get_channel.return_value = other_channel

        fm._followed_user_channels["200"] = (1, 500)
        fm._followed_user_channels["100"] = (1, 200)
        fm._followed_voice_guilds.add(1)

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"

        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        await fm.handle_followed_user_update(member, before, after)

        join_mock.assert_awaited_once_with(other_channel)


class TestBotVoiceUpdate:
    @pytest.mark.asyncio
    async def test_bot_moved_to_non_allowed_leaves(self) -> None:
        _, _, leave_mock, fm = _make_follow_manager(
            follow_user_ids={"100"},
            allowed_channels=[("1", "200")],
        )

        after_channel = MagicMock(spec=discord.VoiceChannel)
        after_channel.id = 999

        result = await fm.handle_bot_voice_update(1, None, after_channel)

        assert result is True
        leave_mock.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_bot_moved_to_allowed_stays(self) -> None:
        _, _, leave_mock, fm = _make_follow_manager(
            follow_user_ids={"100"},
            allowed_channels=[("1", "200")],
        )

        after_channel = MagicMock(spec=discord.VoiceChannel)
        after_channel.id = 200

        result = await fm.handle_bot_voice_update(1, None, after_channel)

        assert result is False
        leave_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bot_disconnected_clears_guild(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100"})
        fm._followed_voice_guilds.add(1)

        before_channel = MagicMock(spec=discord.VoiceChannel)
        result = await fm.handle_bot_voice_update(1, before_channel, None)

        assert result is False
        assert 1 not in fm._followed_voice_guilds


class TestReconciliation:
    @pytest.mark.asyncio
    async def test_start_stop_reconciliation(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100"})

        await fm.start_reconciliation()
        assert fm._reconcile_task is not None
        assert not fm._reconcile_task.done()

        await fm.stop_reconciliation()
        assert fm._reconcile_task is None

    @pytest.mark.asyncio
    async def test_start_reconciliation_noop_when_disabled(self) -> None:
        _, _, _, fm = _make_follow_manager()
        await fm.start_reconciliation()
        assert fm._reconcile_task is None

    @pytest.mark.asyncio
    async def test_destroy(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100"})
        fm._followed_voice_guilds.add(1)
        fm._followed_user_channels["100"] = (1, 200)

        await fm.start_reconciliation()
        await fm.destroy()

        assert fm._destroyed is True
        assert fm._reconcile_task is None
        assert len(fm._followed_voice_guilds) == 0
        assert len(fm._followed_user_channels) == 0

    @pytest.mark.asyncio
    async def test_reconcile_once_finds_user_via_rest(self) -> None:
        client, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100"})

        guild = MagicMock()
        guild.id = 1
        guild.name = "test-guild"
        client.guilds = [guild]

        target_channel = MagicMock(spec=discord.VoiceChannel)
        target_channel.id = 200
        guild.get_channel.return_value = target_channel

        client.http.request = AsyncMock(return_value={"channel_id": "200"})

        await fm._reconcile_once()

        join_mock.assert_awaited_once_with(target_channel)

    @pytest.mark.asyncio
    async def test_reconcile_once_user_not_in_voice(self) -> None:
        client, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100"})

        guild = MagicMock()
        guild.id = 1
        guild.name = "test-guild"
        client.guilds = [guild]

        client.http.request = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))

        await fm._reconcile_once()

        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_cleans_stale_guild(self) -> None:
        leave_check = AsyncMock(return_value=True)
        client, _, leave_mock, fm = _make_follow_manager(follow_user_ids={"100"}, on_guild_leave_check=leave_check)
        fm._followed_voice_guilds.add(1)

        guild = MagicMock()
        guild.id = 1
        guild.name = "test-guild"
        client.guilds = [guild]

        client.http.request = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))

        await fm._reconcile_once()

        leave_mock.assert_awaited_once_with(1)
        assert 1 not in fm._followed_voice_guilds


class TestHandoffEdgeCases:
    @pytest.mark.asyncio
    async def test_handoff_skips_different_guild(self) -> None:
        """Covers line 186: continue when gid != guild_id."""
        client, join_mock, leave_mock, fm = _make_follow_manager(
            follow_user_ids={"100", "200"},
            on_guild_leave_check=AsyncMock(return_value=True),
        )
        fm._followed_user_channels["200"] = (999, 500)
        fm._followed_voice_guilds.add(1)

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"
        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        await fm.handle_followed_user_update(member, before, after)
        join_mock.assert_not_awaited()
        leave_mock.assert_awaited_once_with(1)

    @pytest.mark.asyncio
    async def test_handoff_channel_not_voice(self) -> None:
        """Handoff skips when channel is not a VoiceChannel instance."""
        client, join_mock, leave_mock, fm = _make_follow_manager(
            follow_user_ids={"100", "200"},
            on_guild_leave_check=AsyncMock(return_value=True),
        )
        client.get_channel.return_value = MagicMock()
        fm._followed_user_channels["200"] = (1, 500)
        fm._followed_voice_guilds.add(1)

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"
        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        await fm.handle_followed_user_update(member, before, after)
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_leave_check_returns_false_prevents_leave(self) -> None:
        """on_guild_leave_check returning False prevents bot from leaving."""
        leave_check = AsyncMock(return_value=False)
        _, _, leave_mock, fm = _make_follow_manager(follow_user_ids={"100"}, on_guild_leave_check=leave_check)
        fm._followed_voice_guilds.add(1)
        fm._followed_user_channels["100"] = (1, 200)

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        member.display_name = "Alice"
        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        await fm.handle_followed_user_update(member, before, after)
        leave_mock.assert_not_awaited()


class TestReconcileOnceEdgeCases:
    @pytest.mark.asyncio
    async def test_reconcile_once_no_follow_users_returns_early(self) -> None:
        """Covers line 228: early return when no follow user IDs."""
        _, join_mock, _, fm = _make_follow_manager()
        await fm._reconcile_once()
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_once_destroyed_returns_early(self) -> None:
        """Covers line 233: early return when destroyed during iteration."""
        client, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100"})

        guild = MagicMock()
        guild.id = 1
        guild.name = "test"
        client.guilds = [guild]

        async def destroy_on_request(*args: object, **kwargs: object) -> dict[str, str]:
            fm._destroyed = True
            return {"channel_id": "200"}

        client.http.request = AsyncMock(side_effect=destroy_on_request)
        guild.get_channel.return_value = MagicMock(spec=discord.VoiceChannel)

        await fm._reconcile_once()
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_rest_http_exception(self) -> None:
        """Covers lines 269-271: HTTPException continues to next user."""
        client, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100"})

        guild = MagicMock()
        guild.id = 1
        guild.name = "test"
        client.guilds = [guild]

        response = MagicMock()
        response.status = 500
        client.http.request = AsyncMock(side_effect=discord.HTTPException(response, "server error"))

        await fm._reconcile_once()
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_rest_no_channel_id(self) -> None:
        """Covers line 275: channel_id is None in REST response."""
        client, join_mock, _, fm = _make_follow_manager(follow_user_ids={"100"})

        guild = MagicMock()
        guild.id = 1
        guild.name = "test"
        client.guilds = [guild]

        client.http.request = AsyncMock(return_value={"channel_id": None})

        await fm._reconcile_once()
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_rest_channel_not_allowed(self) -> None:
        """Covers line 279: channel found but not in allowed list."""
        client, join_mock, _, fm = _make_follow_manager(
            follow_user_ids={"100"},
            allowed_channels=[("1", "999")],
        )

        guild = MagicMock()
        guild.id = 1
        guild.name = "test"
        client.guilds = [guild]

        client.http.request = AsyncMock(return_value={"channel_id": "200"})

        await fm._reconcile_once()
        join_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reconcile_leave_check_false_prevents_leave(self) -> None:
        """Reconciliation respects on_guild_leave_check returning False."""
        leave_check = AsyncMock(return_value=False)
        client, _, leave_mock, fm = _make_follow_manager(follow_user_ids={"100"}, on_guild_leave_check=leave_check)
        fm._followed_voice_guilds.add(1)

        guild = MagicMock()
        guild.id = 1
        guild.name = "test"
        client.guilds = [guild]

        client.http.request = AsyncMock(side_effect=discord.NotFound(MagicMock(), "not found"))

        await fm._reconcile_once()
        leave_mock.assert_not_awaited()
        leave_check.assert_awaited_once_with(1)


class TestFollowedGuildsImmutable:
    def test_followed_guilds_returns_frozenset(self) -> None:
        _, _, _, fm = _make_follow_manager(follow_user_ids={"100"})
        fm._followed_voice_guilds.add(1)
        result = fm.followed_guilds
        assert isinstance(result, frozenset)
        assert 1 in result
