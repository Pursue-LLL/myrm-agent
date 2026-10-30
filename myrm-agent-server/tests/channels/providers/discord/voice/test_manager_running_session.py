"""A joined VoiceManager session: its listen loop and the ways it ends without a ``/voice leave``."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import (
    VoiceManager,
    _GuildVoiceState,
)


class TestVoiceManagerAutoDisconnect:
    @pytest.mark.asyncio
    async def test_auto_disconnect_when_alone(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_channel = MagicMock()
        bot_member = MagicMock()
        bot_member.bot = True
        mock_channel.members = [bot_member]
        mock_vc.channel = mock_channel
        mock_vc.disconnect = AsyncMock()

        mock_receiver = MagicMock()
        mock_receiver.running = False

        state = _GuildVoiceState(
            voice_client=mock_vc,
            receiver=mock_receiver,
        )
        mgr._guilds[1] = state

        member = MagicMock()
        member.guild.id = 1
        before = MagicMock()
        after = MagicMock()

        await mgr.on_voice_state_update(member, before, after)
        assert 1 not in mgr._guilds

    @pytest.mark.asyncio
    async def test_no_disconnect_with_users(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_channel = MagicMock()
        human = MagicMock()
        human.bot = False
        bot_member = MagicMock()
        bot_member.bot = True
        mock_channel.members = [bot_member, human]
        mock_vc.channel = mock_channel

        mock_receiver = MagicMock()
        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state

        member = MagicMock()
        member.guild.id = 1
        await mgr.on_voice_state_update(member, MagicMock(), MagicMock())
        assert 1 in mgr._guilds

    @pytest.mark.asyncio
    async def test_voice_state_update_not_connected(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)

        member = MagicMock()
        member.guild.id = 1
        await mgr.on_voice_state_update(member, MagicMock(), MagicMock())

    @pytest.mark.asyncio
    async def test_voice_state_update_no_channel(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel = None
        mock_receiver = MagicMock()
        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state

        member = MagicMock()
        member.guild.id = 1
        await mgr.on_voice_state_update(member, MagicMock(), MagicMock())
        assert 1 in mgr._guilds


class TestListenLoop:
    @pytest.mark.asyncio
    async def test_listen_loop_exits_when_no_state(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        await mgr._listen_loop(999)

    @pytest.mark.asyncio
    async def test_listen_loop_processes_speech(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(client, voice_timeout=0, on_voice_input=cb, speaker_gate=AsyncMock(return_value=True))

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.send_audio_packet = MagicMock()

        mock_receiver = MagicMock()
        call_count = 0
        min_bytes = 192100

        def check_silence_side_effect() -> list[tuple[int, bytes]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(42, b"\x00" * min_bytes)]
            mock_receiver.running = False
            return []

        mock_receiver.running = True
        mock_receiver.check_silence = check_silence_side_effect

        state = _GuildVoiceState(
            voice_client=mock_vc,
            receiver=mock_receiver,
            text_channel_id=789,
        )
        mgr._guilds[1] = state

        with patch.object(mgr._input, "process", new_callable=AsyncMock) as mock_pvi:
            await mgr._listen_loop(1)

        mock_pvi.assert_called_once_with(1, 42, b"\x00" * min_bytes, 789)

    @pytest.mark.asyncio
    async def test_listen_loop_filters_allowed_users(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0, allowed_user_ids={"42"}, speaker_gate=AsyncMock(return_value=True))

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True

        mock_receiver = MagicMock()
        call_count = 0

        def check_silence_side_effect() -> list[tuple[int, bytes]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [(99, b"\x00" * 192100)]
            mock_receiver.running = False
            return []

        mock_receiver.running = True
        mock_receiver.check_silence = check_silence_side_effect

        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state

        with patch.object(mgr._input, "process", new_callable=AsyncMock) as mock_pvi:
            await mgr._listen_loop(1)

        mock_pvi.assert_not_called()

    @pytest.mark.asyncio
    async def test_listen_loop_timeout(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=1)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()

        mock_receiver = MagicMock()
        mock_receiver.running = True
        mock_receiver.check_silence.return_value = []

        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        state.last_speech_at = time.monotonic() - 10
        mgr._guilds[1] = state

        await mgr._listen_loop(1)
        assert 1 not in mgr._guilds

    @pytest.mark.asyncio
    async def test_listen_loop_keepalive(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.send_audio_packet = MagicMock()

        mock_receiver = MagicMock()
        call_count = 0

        def check_silence_side_effect() -> list[tuple[int, bytes]]:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                mock_receiver.running = False
            return []

        mock_receiver.running = True
        mock_receiver.check_silence = check_silence_side_effect

        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state

        with patch(
            "app.channels.providers.discord.voice.manager._KEEPALIVE_INTERVAL",
            0,
        ):
            await mgr._listen_loop(1)

        mock_vc.send_audio_packet.assert_called()


class TestBotVoiceUpdateManager:
    @pytest.mark.asyncio
    async def test_bot_disconnected_cleans_state(self) -> None:
        client = MagicMock()
        client.user = MagicMock()
        client.user.id = 999
        mgr = VoiceManager(client, voice_timeout=0)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()
        mock_receiver = MagicMock()
        mock_receiver.running = False
        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        mgr._guilds[1] = state

        member = MagicMock()
        member.guild.id = 1
        member.id = 999
        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None
        await mgr._handle_bot_voice_update(member, before, after)
        assert 1 not in mgr._guilds

    @pytest.mark.asyncio
    async def test_bot_moved_delegates_to_follow(self) -> None:
        client = MagicMock()
        client.user = MagicMock()
        client.user.id = 999
        mgr = VoiceManager(client, follow_user_ids={"100"})

        member = MagicMock()
        member.guild.id = 1
        member.id = 999
        before = MagicMock()
        before.channel = None
        after = MagicMock()
        after.channel = MagicMock()
        after.channel.id = 200

        with patch.object(mgr._follow, "handle_bot_voice_update", new_callable=AsyncMock) as mock_follow_bot:
            await mgr._handle_bot_voice_update(member, before, after)
        mock_follow_bot.assert_awaited_once()


class TestShouldLeaveGuild:
    @pytest.mark.asyncio
    async def test_should_leave_when_empty(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        bot_member = MagicMock()
        bot_member.bot = True
        mock_channel = MagicMock()
        mock_channel.members = [bot_member]
        mock_vc.channel = mock_channel
        mock_receiver = MagicMock()
        mgr._guilds[1] = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        result = await mgr._should_leave_guild(1)
        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_leave_with_users(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        human = MagicMock()
        human.bot = False
        mock_channel = MagicMock()
        mock_channel.members = [human]
        mock_vc.channel = mock_channel
        mock_receiver = MagicMock()
        mgr._guilds[1] = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        result = await mgr._should_leave_guild(1)
        assert result is False

    @pytest.mark.asyncio
    async def test_should_leave_no_state(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        result = await mgr._should_leave_guild(999)
        assert result is False


class TestBotVoiceUpdateListenTask:
    @pytest.mark.asyncio
    async def test_bot_disconnect_cancels_listen_task(self) -> None:
        client = MagicMock()
        client.user = MagicMock()
        client.user.id = 999
        mgr = VoiceManager(client)

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.disconnect = AsyncMock()
        mock_receiver = MagicMock()
        mock_receiver.running = False

        listen_task = MagicMock()
        listen_task.done.return_value = False
        listen_task.cancel = MagicMock()

        state = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        state.listen_task = listen_task
        mgr._guilds[1] = state

        member = MagicMock()
        member.guild.id = 1
        member.id = 999
        before = MagicMock()
        before.channel = MagicMock()
        after = MagicMock()
        after.channel = None

        await mgr._handle_bot_voice_update(member, before, after)
        listen_task.cancel.assert_called_once()
        assert 1 not in mgr._guilds


class TestShouldLeaveGuildNoChannel:
    @pytest.mark.asyncio
    async def test_should_leave_when_no_bot_channel(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        mock_vc = MagicMock()
        mock_vc.channel = None
        mock_receiver = MagicMock()
        mgr._guilds[1] = _GuildVoiceState(voice_client=mock_vc, receiver=mock_receiver)
        result = await mgr._should_leave_guild(1)
        assert result is True
