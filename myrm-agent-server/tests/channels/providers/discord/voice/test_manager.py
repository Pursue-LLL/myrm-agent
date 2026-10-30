"""VoiceManager: construction, join and leave, lookups, follow-user delegation and player registration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import (
    VoiceManager,
    _GuildVoiceState,
)


class TestVoiceManagerInit:
    def test_defaults(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        assert mgr._voice_timeout == 300
        assert mgr._allowed_user_ids == set()
        assert mgr.active_guilds == []

    def test_custom_params(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(
            client,
            voice_timeout=60,
            allowed_user_ids={"100", "200"},
            on_voice_input=cb,
        )
        assert mgr._voice_timeout == 60
        assert mgr._allowed_user_ids == {"100", "200"}
        assert mgr._input._on_voice_input is cb

    def test_voice_input_options_reach_the_input_pipeline(self) -> None:
        mgr = VoiceManager(MagicMock(), voice_wake_words=["Hey Bot"], voice_barge_in_enabled=True)
        assert mgr._input._wake_words == ["hey bot"]
        assert mgr._input._barge_in_enabled is True

    def test_guild_lock_creates_on_demand(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        lock1 = mgr._guild_lock(1)
        lock2 = mgr._guild_lock(1)
        assert lock1 is lock2
        lock3 = mgr._guild_lock(2)
        assert lock3 is not lock1


class TestVoiceManagerJoinLeave:
    @pytest.mark.asyncio
    async def test_join_success(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        channel = MagicMock()
        channel.guild.id = 1
        channel.name = "test-vc"
        channel.id = 123

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel = channel
        mock_vc._connection = MagicMock()
        mock_vc._connection.secret_key = [0] * 32
        mock_vc._connection.ssrc = 999
        mock_vc._connection.hook = None
        mock_vc.user = MagicMock()
        mock_vc.user.id = 1

        channel.connect = AsyncMock(return_value=mock_vc)

        with patch("app.channels.providers.discord.voice.manager.VoiceReceiver") as MockReceiver:
            mock_receiver = MagicMock()
            mock_receiver.running = False
            MockReceiver.return_value = mock_receiver

            result = await mgr.join(channel)

        assert result is True
        assert mgr.is_connected(1)
        assert 1 in mgr.active_guilds

    @pytest.mark.asyncio
    async def test_join_with_text_channel_id(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        channel = MagicMock()
        channel.guild.id = 1
        channel.name = "test-vc"
        channel.id = 123
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel = channel
        mock_vc._connection = MagicMock()
        mock_vc._connection.secret_key = [0] * 32
        mock_vc._connection.ssrc = 999
        mock_vc._connection.hook = None
        mock_vc.user = MagicMock()
        mock_vc.user.id = 1
        channel.connect = AsyncMock(return_value=mock_vc)

        with patch("app.channels.providers.discord.voice.manager.VoiceReceiver") as MockReceiver:
            mock_receiver = MagicMock()
            mock_receiver.running = False
            MockReceiver.return_value = mock_receiver

            result = await mgr.join(channel, text_channel_id=456)

        assert result is True
        assert mgr._guilds[1].text_channel_id == 456

    @pytest.mark.asyncio
    async def test_rejoin_same_channel_updates_text_channel(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        channel = MagicMock()
        channel.guild.id = 1
        channel.id = 123

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel = channel

        mock_receiver = MagicMock()
        mock_receiver.running = False

        state = _GuildVoiceState(
            voice_client=mock_vc,
            receiver=mock_receiver,
            text_channel_id=100,
        )
        mgr._guilds[1] = state

        result = await mgr.join(channel, text_channel_id=200)
        assert result is True
        assert mgr._guilds[1].text_channel_id == 200

    @pytest.mark.asyncio
    async def test_rejoin_different_channel_moves(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        old_channel = MagicMock()
        old_channel.id = 111

        new_channel = MagicMock()
        new_channel.guild.id = 1
        new_channel.id = 222
        new_channel.name = "new-vc"

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel = old_channel
        mock_vc.move_to = AsyncMock()

        mock_receiver = MagicMock()
        mock_receiver.running = False

        state = _GuildVoiceState(
            voice_client=mock_vc,
            receiver=mock_receiver,
        )
        mgr._guilds[1] = state

        result = await mgr.join(new_channel, text_channel_id=333)
        assert result is True
        mock_vc.move_to.assert_awaited_once_with(new_channel)
        assert mgr._guilds[1].text_channel_id == 333

    @pytest.mark.asyncio
    async def test_join_failure(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)

        channel = MagicMock()
        channel.guild.id = 1
        channel.connect = AsyncMock(side_effect=Exception("timeout"))

        result = await mgr.join(channel)
        assert result is False
        assert not mgr.is_connected(1)

    @pytest.mark.asyncio
    async def test_leave(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()

        mock_receiver = MagicMock()
        mock_receiver.running = False

        state = _GuildVoiceState(
            voice_client=mock_vc,
            receiver=mock_receiver,
        )
        mgr._guilds[1] = state

        await mgr.leave(1)
        assert not mgr.is_connected(1)
        mock_receiver.stop.assert_called_once()
        mock_vc.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_leave_cancels_task(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()

        mock_receiver = MagicMock()
        mock_receiver.running = False

        cancelled = False

        async def dummy_task() -> None:
            nonlocal cancelled
            try:
                await asyncio.sleep(999)
            except asyncio.CancelledError:
                cancelled = True
                raise

        task = asyncio.get_running_loop().create_task(dummy_task())
        await asyncio.sleep(0)

        state = _GuildVoiceState(
            voice_client=mock_vc,
            receiver=mock_receiver,
        )
        state.listen_task = task
        mgr._guilds[1] = state

        await mgr.leave(1)
        assert cancelled

    @pytest.mark.asyncio
    async def test_leave_nonexistent_guild(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        await mgr.leave(999)

    @pytest.mark.asyncio
    async def test_leave_all(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        for gid in [1, 2]:
            mock_vc = MagicMock()
            mock_vc.is_connected.return_value = True
            mock_vc.disconnect = AsyncMock()
            mock_receiver = MagicMock()
            mock_receiver.running = False
            state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
            mgr._guilds[gid] = state

        await mgr.leave_all()
        assert len(mgr._guilds) == 0


class TestVoiceManagerGetters:
    def test_get_voice_client(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)

        assert mgr.get_voice_client(1) is None

        mock_vc = MagicMock()
        mock_receiver = MagicMock()
        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state
        assert mgr.get_voice_client(1) is mock_vc

    def test_get_receiver(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)

        assert mgr.get_receiver(1) is None

        mock_vc = MagicMock()
        mock_receiver = MagicMock()
        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state
        assert mgr.get_receiver(1) is mock_receiver

    def test_is_connected_false_when_disconnected(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = False
        mock_receiver = MagicMock()
        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state
        assert not mgr.is_connected(1)


class TestVoiceManagerFollowIntegration:
    def test_follow_enabled_when_configured(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, follow_user_ids={"100", "200"})
        assert mgr.follow_enabled is True

    def test_follow_disabled_when_not_configured(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        assert mgr.follow_enabled is False

    @pytest.mark.asyncio
    async def test_on_voice_state_update_dispatches_to_follow(self) -> None:
        client = MagicMock()
        client.user = MagicMock()
        client.user.id = 999
        mgr = VoiceManager(client, follow_user_ids={"100"})

        member = MagicMock()
        member.guild.id = 1
        member.id = 100
        before = MagicMock()
        before.channel = None
        after = MagicMock()
        after.channel = MagicMock()
        after.channel.id = 200
        after.channel.name = "test-vc"

        with patch.object(mgr._follow, "handle_followed_user_update", new_callable=AsyncMock) as mock_follow:
            await mgr.on_voice_state_update(member, before, after)
        mock_follow.assert_awaited_once_with(member, before, after)

    @pytest.mark.asyncio
    async def test_on_voice_state_update_bot_event(self) -> None:
        client = MagicMock()
        client.user = MagicMock()
        client.user.id = 999
        mgr = VoiceManager(client)

        member = MagicMock()
        member.guild.id = 1
        member.id = 999
        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        with patch.object(mgr, "_handle_bot_voice_update", new_callable=AsyncMock) as mock_bot:
            await mgr.on_voice_state_update(member, before, after)
        mock_bot.assert_awaited_once_with(member, before, after)


class TestStartReconciliation:
    @pytest.mark.asyncio
    async def test_start_reconciliation_delegates(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, follow_user_ids={"100"})
        with patch.object(mgr._follow, "start_reconciliation", new_callable=AsyncMock) as mock_start:
            await mgr.start_reconciliation()
        mock_start.assert_awaited_once()


class TestRegisterUnregisterPlayer:
    def test_register_player_reaches_the_input_pipeline(self) -> None:
        mgr = VoiceManager(MagicMock())
        player = MagicMock()
        mgr.register_player(1, player, "hello world")
        assert mgr._input._active_players[1] is player
        assert mgr._input._active_play_texts[1] == "hello world"

    def test_unregister_player_reaches_the_input_pipeline(self) -> None:
        mgr = VoiceManager(MagicMock())
        mgr.register_player(1, MagicMock(), "text")
        mgr.unregister_player(1)
        assert 1 not in mgr._input._active_players
        assert 1 not in mgr._input._active_play_texts
