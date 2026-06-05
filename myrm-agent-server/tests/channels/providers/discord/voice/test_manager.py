"""Unit tests for VoiceManager."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.providers.discord.voice.manager import (
    VoiceManager,
    _GuildVoiceState,
    _is_whisper_hallucination,
)


class TestWhisperHallucination:
    def test_common_hallucinations(self) -> None:
        assert _is_whisper_hallucination("Thanks for watching")
        assert _is_whisper_hallucination("thank you")
        assert _is_whisper_hallucination("...")
        assert _is_whisper_hallucination("bye")
        assert _is_whisper_hallucination("")
        assert _is_whisper_hallucination("  The end.  ")

    def test_real_speech(self) -> None:
        assert not _is_whisper_hallucination("Hello, how are you?")
        assert not _is_whisper_hallucination("What is the weather like?")
        assert not _is_whisper_hallucination("Thank you for helping me with this project")


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
        assert mgr._on_voice_input is cb

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


class TestResolveDisplayName:
    def test_resolve_success(self) -> None:
        client = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.display_name = "TestUser"
        guild.get_member.return_value = member
        client.get_guild.return_value = guild

        mgr = VoiceManager(client)
        name = mgr._resolve_display_name(1, 42)
        assert name == "TestUser"

    def test_resolve_no_guild(self) -> None:
        client = MagicMock()
        client.get_guild.return_value = None

        mgr = VoiceManager(client)
        name = mgr._resolve_display_name(1, 42)
        assert name == "42"

    def test_resolve_no_member(self) -> None:
        client = MagicMock()
        guild = MagicMock()
        guild.get_member.return_value = None
        client.get_guild.return_value = guild

        mgr = VoiceManager(client)
        name = mgr._resolve_display_name(1, 42)
        assert name == "42"

    def test_resolve_exception(self) -> None:
        client = MagicMock()
        client.get_guild.side_effect = RuntimeError("fail")

        mgr = VoiceManager(client)
        name = mgr._resolve_display_name(1, 42)
        assert name == "42"


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
        mgr = VoiceManager(client, voice_timeout=0, on_voice_input=cb)

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

        with patch.object(mgr, "_process_voice_input", new_callable=AsyncMock) as mock_pvi:
            await mgr._listen_loop(1)

        mock_pvi.assert_called_once_with(1, 42, b"\x00" * min_bytes, 789)

    @pytest.mark.asyncio
    async def test_listen_loop_filters_allowed_users(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_timeout=0, allowed_user_ids={"42"})

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

        with patch.object(mgr, "_process_voice_input", new_callable=AsyncMock) as mock_pvi:
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


class TestProcessVoiceInput:
    @pytest.mark.asyncio
    async def test_process_voice_input_full_pipeline(self) -> None:
        client = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.display_name = "Alice"
        guild.get_member.return_value = member
        client.get_guild.return_value = guild

        cb = AsyncMock()
        mgr = VoiceManager(client, on_voice_input=cb)

        pcm = b"\x00" * 3200

        mock_result = MagicMock()
        mock_result.text = "Hello world"

        with (
            patch.object(
                VoiceManager,
                "_resolve_display_name",
                return_value="Alice",
            ),
            patch("app.channels.providers.discord.voice.manager.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "app.channels.types.VoiceConfig",
            ),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, pcm, 789)

        cb.assert_awaited_once()
        call_args = cb.call_args[0]
        assert call_args[0] == 789
        assert call_args[1] == 42
        assert call_args[2] == "Hello world"
        assert call_args[3] == "Alice"

    @pytest.mark.asyncio
    async def test_process_voice_input_uses_guild_id_when_no_text_channel(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(client, on_voice_input=cb)

        mock_result = MagicMock()
        mock_result.text = "Test"

        with (
            patch.object(VoiceManager, "_resolve_display_name", return_value="Bob"),
            patch("app.channels.providers.discord.voice.manager.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, b"\x00" * 3200, 0)

        cb.assert_awaited_once()
        assert cb.call_args[0][0] == 1

    @pytest.mark.asyncio
    async def test_process_voice_input_hallucination_filtered(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(client, on_voice_input=cb)

        mock_result = MagicMock()
        mock_result.text = "Thanks for watching"

        with (
            patch.object(VoiceManager, "_resolve_display_name", return_value="X"),
            patch("app.channels.providers.discord.voice.manager.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_voice_input_empty_result(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(client, on_voice_input=cb)

        mock_result = MagicMock()
        mock_result.text = ""

        with (
            patch("app.channels.providers.discord.voice.manager.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_voice_input_no_result(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(client, on_voice_input=cb)

        with (
            patch("app.channels.providers.discord.voice.manager.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_voice_input_exception(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        mgr = VoiceManager(client, on_voice_input=cb)

        with patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = AsyncMock(side_effect=RuntimeError("ffmpeg fail"))
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_voice_input_no_callback(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, on_voice_input=None)

        mock_result = MagicMock()
        mock_result.text = "Hello"

        with (
            patch.object(VoiceManager, "_resolve_display_name", return_value="X"),
            patch("app.channels.providers.discord.voice.manager.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.manager.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await mgr._process_voice_input(1, 42, b"\x00" * 3200, 0)


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


class TestBargeIn:
    def test_barge_in_echo_detected(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        mgr._active_players[1] = player
        mgr._active_play_texts[1] = "Hello world how are you today"
        result = mgr._handle_barge_in(1, "Hello world how are you today", "hello world how are you today")
        assert result is True

    def test_barge_in_real_interruption(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        player.stop = MagicMock()
        mgr._active_players[1] = player
        mgr._active_play_texts[1] = "Hello world"
        result = mgr._handle_barge_in(1, "Stop please", "stop please")
        assert result is False
        player.stop.assert_called_once()

    def test_barge_in_no_player(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_barge_in_enabled=True)
        result = mgr._handle_barge_in(1, "Test", "test")
        assert result is False


class TestWakeWord:
    def test_wake_word_activates(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_wake_words=["hey bot"])
        result = mgr._check_wake_word(1, "hey bot what is the time")
        assert result is True
        assert mgr._wake_until.get(1, 0) > 0

    def test_wake_word_asleep_no_match(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_wake_words=["hey bot"])
        result = mgr._check_wake_word(1, "what is the time")
        assert result is False

    def test_wake_word_stays_awake_within_ttl(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_wake_words=["hey bot"])
        mgr._wake_until[1] = time.time() + 30
        result = mgr._check_wake_word(1, "what is the time")
        assert result is True

    def test_wake_word_non_ascii(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_wake_words=["\u5c0f\u52a9\u624b"])
        result = mgr._check_wake_word(1, "\u5c0f\u52a9\u624b\u5e2e\u6211\u67e5\u5929\u6c14")
        assert result is True

    def test_wake_word_ascii_boundary(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_wake_words=["bot"])
        assert mgr._check_wake_word(1, "hey bot how are you") is True
        mgr._wake_until.clear()
        assert mgr._check_wake_word(1, "robot is here") is False


class TestRegisterUnregisterPlayer:
    def test_register_player(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        player = MagicMock()
        mgr.register_player(1, player, "hello world")
        assert mgr._active_players[1] is player
        assert mgr._active_play_texts[1] == "hello world"

    def test_unregister_player(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        mgr._active_players[1] = MagicMock()
        mgr._active_play_texts[1] = "text"
        mgr.unregister_player(1)
        assert 1 not in mgr._active_players
        assert 1 not in mgr._active_play_texts

    def test_unregister_nonexistent(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client)
        mgr.unregister_player(999)


class TestStartReconciliation:
    @pytest.mark.asyncio
    async def test_start_reconciliation_delegates(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, follow_user_ids={"100"})
        with patch.object(mgr._follow, "start_reconciliation", new_callable=AsyncMock) as mock_start:
            await mgr.start_reconciliation()
        mock_start.assert_awaited_once()


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


class TestBargeInStopException:
    def test_barge_in_stop_exception_handled(self) -> None:
        client = MagicMock()
        mgr = VoiceManager(client, voice_barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        player.stop = MagicMock(side_effect=RuntimeError("stop failed"))
        mgr._active_players[1] = player
        mgr._active_play_texts[1] = "Hello world"
        result = mgr._handle_barge_in(1, "Stop please", "stop please")
        assert result is False
